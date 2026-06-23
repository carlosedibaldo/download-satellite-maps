"""Earth Engine access for GEE-only canopy-height products (ECHOSAT, GLAD).

Some products aren't /vsicurl-able and can't go through the gdal_translate clip
path used for the HTTP products (eth/gpw). For those we filter the GEE collection
to the tile footprint, mosaic, select a band, and download a windowed GeoTIFF via
getDownloadURL — see `clip_gee_band`. Two products use this path:
  * ECHOSAT (`projects/ai4forest/assets/echosat`) — temporal, 10 m, int16 cm, 7
    bands b1..b7 = years 2018..2024; `clip_echosat_year` resolves year -> band.
  * GLAD/Potapov 2019 (`users/potapovpeter/GEDI_V27`) — single-epoch, 30 m, metres,
    7 regional tiles mosaicked, single band b1, sentinels 101/102/103.

The clip is written in the ALS tile's UTM at the product's native resolution
(effectively native, directly comparable to the ALS grid), as float32 **metres**
(source * scale_factor) with NaN nodata — consistent with the HTTP products.

Auth: needs an Earth Engine-enabled GCP project (default `forest-als`) and local
credentials (gcloud ADC or `earthengine authenticate`). earthengine-api is an
optional dependency: `pip install download-satellite-maps[echosat]`.
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

from .products import NODATA, Product

_INITED: set[str] = set()
_GEE_FILL = -9999.0   # numeric sentinel for ee.unmask (NaN isn't accepted); -> NaN on disk


def ee_init(project: str = "forest-als"):
    """Lazily import + initialize Earth Engine for `project` (once per project)."""
    try:
        import ee
    except ImportError as e:  # pragma: no cover - optional dep
        raise RuntimeError(
            "earthengine-api not installed — `pip install "
            "download-satellite-maps[echosat]`"
        ) from e
    if project not in _INITED:
        ee.Initialize(project=project)
        _INITED.add(project)
    return ee


def echosat_band(product: Product, year: int) -> str:
    """Band id for a year: b1..b7 follow product.temporal_years (2018..2024)."""
    if year not in product.temporal_years:
        raise ValueError(
            f"{product.id}: year {year} not available {product.temporal_years}"
        )
    return f"b{product.temporal_years.index(year) + 1}"


def _export_image(product: Product, img, region, epsg: int,
                  out_path: Path) -> Path:
    """Mask source sentinels, scale to metres, and download `img` (a single-band
    ee.Image already selected by the caller) over `region` to a native-CRS float32
    GeoTIFF. OUTPUT CRS = `product.gee_native_epsg` if set else `epsg` (the ALS UTM)
    — never a forced reprojection. Masked pixels -> NaN nodata, metres throughout."""
    sentinels = list(product.invalid_values)   # native-unit fills, e.g. GLAD 101/102/103
    if product.nodata is not None:
        sentinels.append(product.nodata)
    for v in sentinels:
        img = img.updateMask(img.neq(v))        # drop sentinel pixels -> masked -> NaN
    img = (
        img.multiply(product.scale_factor)      # source units -> metres
        .toFloat()
        .unmask(_GEE_FILL)                       # masked -> numeric sentinel (NaN not allowed)
    )
    url = img.getDownloadURL({
        "region": region,
        "scale": product.native_res_m,
        "crs": f"EPSG:{product.gee_native_epsg or epsg}",
        "format": "GEO_TIFF",
    })
    out_path = Path(out_path)
    urllib.request.urlretrieve(url, out_path)
    _fill_to_nan(out_path)
    return out_path


def _region(ee, epsg: int, bounds):
    """ee.Geometry.Rectangle for the ALS footprint, defined in the tile UTM."""
    left, bottom, right, top = bounds
    return ee.Geometry.Rectangle([left, bottom, right, top],
                                 proj=f"EPSG:{epsg}", geodesic=False)


def clip_gee_band(product: Product, band: str, epsg: int, bounds,
                  out_path: Path, project: str = "forest-als") -> Path:
    """Download `band` of `product.gee_asset` (collection mosaic) over `bounds`.
    Used by single-epoch GEE products (GLAD) and ECHOSAT's per-year band select."""
    ee = ee_init(project)
    region = _region(ee, epsg, bounds)
    img = ee.ImageCollection(product.gee_asset).filterBounds(region).mosaic().select([band])
    return _export_image(product, img, region, epsg, out_path)


def clip_gee_year_by_date(product: Product, year: int, epsg: int, bounds,
                          out_path: Path, project: str = "forest-als") -> Path:
    """Temporal GEE products with one IMAGE per year (GPW): filter the collection to
    `year` by date, mosaic, select `product.gee_band`, then export like the rest."""
    ee = ee_init(project)
    region = _region(ee, epsg, bounds)
    img = (
        ee.ImageCollection(product.gee_asset)
        .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
        .filterBounds(region)
        .mosaic()
        .select([product.gee_band])
    )
    return _export_image(product, img, region, epsg, out_path)


def clip_echosat_year(product: Product, year: int, epsg: int, bounds,
                      out_path: Path, project: str = "forest-als") -> Path:
    """ECHOSAT temporal clip: resolve `year` -> band b1..b7, then clip_gee_band."""
    return clip_gee_band(product, echosat_band(product, year), epsg, bounds,
                         out_path, project=project)


def _fill_to_nan(path: Path) -> None:
    """Convert the GEE numeric fill to NaN and tag nodata=NaN (float32)."""
    import numpy as np
    import rasterio
    with rasterio.open(path) as src:
        data = src.read(1).astype("float32")
        profile = src.profile.copy()
    data[data == _GEE_FILL] = np.nan
    profile.update(dtype="float32", count=1, nodata=NODATA, compress="deflate")
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)

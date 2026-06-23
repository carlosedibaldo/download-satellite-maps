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


def clip_gee_band(product: Product, band: str, epsg: int, bounds,
                  out_path: Path, project: str = "forest-als") -> Path:
    """Download `band` of `product.gee_asset` over `bounds` (in EPSG:`epsg`, the ALS
    tile's UTM) to a native-resolution float32-metre GeoTIFF. The OUTPUT CRS is the
    product's native CRS — `product.gee_native_epsg` if set (e.g. GLAD is global
    EPSG:4326), else `epsg` (e.g. ECHOSAT's per-tile UTM == the ALS zone). We never
    force a reprojection: the output stays in the source's own projection.

    Source sentinels (`nodata` + `invalid_values`, native units) are masked in EE
    before scaling; the value is scaled *scale_factor -> metres; masked pixels become
    NaN nodata so the public clip reads directly in metres like the other products."""
    ee = ee_init(project)
    left, bottom, right, top = bounds
    # The footprint is given in the ALS tile UTM; define the region there. The OUTPUT
    # grid uses the product's native CRS so we don't resample into a foreign zone.
    region = ee.Geometry.Rectangle([left, bottom, right, top],
                                   proj=f"EPSG:{epsg}", geodesic=False)
    out_crs = f"EPSG:{product.gee_native_epsg or epsg}"
    img = (
        ee.ImageCollection(product.gee_asset)
        .filterBounds(region)
        .mosaic()
        .select([band])
    )
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
        "crs": out_crs,
        "format": "GEO_TIFF",
    })
    out_path = Path(out_path)
    urllib.request.urlretrieve(url, out_path)
    _fill_to_nan(out_path)
    return out_path


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

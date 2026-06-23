"""Earth Engine access for the ECHOSAT temporal canopy-height product.

ECHOSAT (`projects/ai4forest/assets/echosat`) is a GEE ImageCollection of ~643
UTM tiles, 10 m, int16, each with 7 bands `b1..b7` = years 2018..2024 (heights in
centimeters). It is NOT /vsicurl-able, so it can't go through the gdal_translate
clip path used for the HTTP products. Instead we filter the collection to the
tile footprint, mosaic, select the requested year's band, and download a windowed
GeoTIFF via getDownloadURL.

The clip is written in the ALS tile's UTM (the same zone ECHOSAT uses for that
location) at 10 m — effectively native, and directly comparable to the ALS grid.
Unlike the HTTP products (kept in native units, scaled at sampling), ECHOSAT is
written as float32 **metres** (source cm * 0.01) with nodata -9999, so the public
clips read directly in metres and are consistent with the other CHM products.

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


def clip_echosat_year(product: Product, year: int, epsg: int, bounds,
                      out_path: Path, project: str = "forest-als") -> Path:
    """Download ECHOSAT's `year` band over `bounds` (in EPSG:`epsg`) to a 10 m
    float32-metre GeoTIFF in that UTM. Source cm are scaled *0.01 -> m; masked
    pixels become NaN nodata so the public clip reads directly in metres."""
    ee = ee_init(project)
    left, bottom, right, top = bounds
    crs = f"EPSG:{epsg}"
    region = ee.Geometry.Rectangle([left, bottom, right, top], proj=crs,
                                   geodesic=False)
    band = echosat_band(product, year)
    img = (
        ee.ImageCollection(product.gee_asset)
        .filterBounds(region)
        .mosaic()
        .select([band])
        .multiply(product.scale_factor)        # source (cm) -> metres
        .toFloat()
        .unmask(_GEE_FILL)                      # masked -> numeric sentinel (NaN not allowed)
    )
    url = img.getDownloadURL({
        "region": region,
        "scale": product.native_res_m,
        "crs": crs,
        "format": "GEO_TIFF",
    })
    out_path = Path(out_path)
    urllib.request.urlretrieve(url, out_path)
    _fill_to_nan(out_path)
    return out_path


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

"""Download the window of a satellite product covering one ALS tile — a pure
spatial subset, NOT a warp.

`gdal_translate -projwin` extracts exactly the source pixels intersecting the
tile bounds, in the product's NATIVE CRS / resolution / dtype, with raw values
and the nodata flag preserved. No reprojection, no resampling, no value change.
(nodata -> NaN is handled later at sampling time, using the product's
nodata/invalid_values from the registry.)"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .products import Product, glad_region

_GDAL_ENV = {
    "GDAL_HTTP_MAX_RETRY": "5",
    "GDAL_HTTP_RETRY_DELAY": "3",
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
}


def source_url(product: Product, lon: float, lat: float) -> str:
    if product.regional:
        if not product.url_template:
            raise ValueError(f"{product.id} is regional but has no url_template")
        return product.url_template.format(region=glad_region(lon, lat))
    if not product.url:
        raise ValueError(f"{product.id} has no source URL (not yet wired)")
    return product.url


def clip_to_tile(product: Product, epsg: int, bounds, out_path: Path,
                 lon: float, lat: float) -> Path:
    """Subset the product to `bounds` (given in EPSG:`epsg`) without altering it."""
    src = source_url(product, lon, lat)
    vsi = f"/vsicurl/{src}" if src.startswith(("http://", "https://")) else src
    left, bottom, right, top = bounds
    cmd = [
        "gdal_translate",
        # -projwin is ulx uly lrx lry; -projwin_srs lets us pass the ALS tile's
        # UTM bounds while the OUTPUT stays in the source's native CRS.
        "-projwin", str(left), str(top), str(right), str(bottom),
        "-projwin_srs", f"EPSG:{epsg}",
        "-co", "COMPRESS=DEFLATE",   # lossless container only — values untouched
        vsi, str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True,
                   env={**os.environ, **_GDAL_ENV})
    return out_path

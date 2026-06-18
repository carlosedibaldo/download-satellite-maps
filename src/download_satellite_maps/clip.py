"""Clip a global satellite product to one ALS tile footprint via gdalwarp.

Reads the public source over /vsicurl and reprojects+clips to the ALS tile's
UTM CRS and 1 km bounds at the product's native resolution → a COG."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .products import Product, glad_region

_GDAL_ENV = {
    "GDAL_HTTP_MAX_RETRY": "5",
    "GDAL_HTTP_RETRY_DELAY": "3",
    # NB: do NOT set CPL_VSIL_CURL_ALLOWED_EXTENSIONS — it would reject sources
    # whose URL has no .tif/.vrt suffix (e.g. GPW's Zenodo `…/content` URL).
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
    src = source_url(product, lon, lat)
    vsi = f"/vsicurl/{src}" if src.startswith(("http://", "https://")) else src
    left, bottom, right, top = bounds
    cmd = [
        "gdalwarp", "-t_srs", f"EPSG:{epsg}",
        "-te", str(left), str(bottom), str(right), str(top),
        "-tr", str(product.native_res_m), str(product.native_res_m),
        "-r", "bilinear", "-of", "COG", "-co", "COMPRESS=DEFLATE",
        "-overwrite", vsi, str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True,
                   env={**os.environ, **_GDAL_ENV})
    return out_path

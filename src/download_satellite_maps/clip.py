"""Download the window of a satellite product covering one ALS tile.

`gdal_translate -projwin` extracts exactly the source pixels intersecting the
tile bounds, in the product's NATIVE CRS / resolution — no reprojection, no
resampling, geometry untouched. We then normalize the VALUES (only) to the
shared public convention: float32 canopy height in METRES (source * scale_factor)
with a single nodata = NODATA, remapping each product's source sentinels
(`nodata` / `invalid_values`). Heights are not rounded — full float precision."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import rasterio

from .products import NODATA, Product

_GDAL_ENV = {
    "GDAL_HTTP_MAX_RETRY": "5",
    "GDAL_HTTP_RETRY_DELAY": "3",
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
}


def source_url(product: Product, lon: float, lat: float) -> str:
    if not product.url:
        raise ValueError(f"{product.id} has no source URL (not yet wired)")
    return product.url


def _to_float_metres(src_path: Path, out_path: Path, product: Product) -> None:
    """Rewrite a native clip as float32 metres with nodata=NODATA. Same grid/CRS
    (no warp): only dtype, the documented scale, and the nodata sentinel change."""
    with rasterio.open(src_path) as src:
        data = src.read(1).astype("float64")
        profile = src.profile.copy()
        src_nodata = src.nodata
    invalid = np.zeros(data.shape, dtype=bool)
    if src_nodata is not None:
        invalid |= data == src_nodata
    if product.nodata is not None:
        invalid |= data == product.nodata
    for v in product.invalid_values:
        invalid |= data == v
    out = (data * product.scale_factor).astype("float32")
    out[invalid] = NODATA
    profile.update(dtype="float32", count=1, nodata=NODATA,
                   compress="deflate", predictor=2)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(out, 1)


def clip_to_tile(product: Product, epsg: int, bounds, out_path: Path,
                 lon: float, lat: float) -> Path:
    """Subset the product to `bounds` (in EPSG:`epsg`), then normalize values to
    float32 metres + NODATA. The spatial subset is a pure native window (no warp);
    only the values/dtype/nodata are converted to the shared convention."""
    src = source_url(product, lon, lat)
    vsi = f"/vsicurl/{src}" if src.startswith(("http://", "https://")) else src
    left, bottom, right, top = bounds
    work = Path(tempfile.mkdtemp(prefix="clip_"))
    native = work / f"native_{out_path.name}"
    cmd = [
        "gdal_translate",
        # -projwin is ulx uly lrx lry; -projwin_srs lets us pass the ALS tile's
        # UTM bounds while the OUTPUT stays in the source's native CRS.
        "-projwin", str(left), str(top), str(right), str(bottom),
        "-projwin_srs", f"EPSG:{epsg}",
        "-co", "COMPRESS=DEFLATE",
        vsi, str(native),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True,
                       env={**os.environ, **_GDAL_ENV})
        _to_float_metres(native, out_path, product)
    finally:
        native.unlink(missing_ok=True)
        try:
            work.rmdir()
        except OSError:
            pass
    return out_path

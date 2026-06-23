"""LANDFIRE canopy-height clips via the USGS LFPS ArcGIS ImageServer.

LANDFIRE products aren't /vsicurl COGs or on GEE (only EVH is mirrored to GEE), but
the LF Product Service exposes each layer as an ArcGIS ImageServer with a SYNCHRONOUS
`exportImage` op — we request the ALS tile's bbox and get a native GeoTIFF back, no
async job. Output stays in LANDFIRE's native CONUS Albers (EPSG:5070, 30 m); only the
clip-to-bbox happens (nearest-neighbour, same CRS — no reprojection).

Forest Canopy Height (CH) is int16 in **metres x 10** (0-510 -> 0-51 m; 0 = non-forest;
-9999 = nodata), so scale_factor 0.1 -> metres and -9999 -> NaN via the shared
`_to_float_metres`. NOTE: the LF2025 ImageServer currently only serves the western US
(eastern GeoAreas not yet loaded), so we use LF2024 — the most recent CH with full
national coverage (verified to return data at eastern sites like HARV).
"""
from __future__ import annotations

import urllib.parse
import urllib.request
from pathlib import Path

from pyproj import Transformer

from .clip import _to_float_metres
from .products import Product

LANDFIRE_EPSG = 5070   # CONUS Albers (NAD83) — LANDFIRE's native grid


def clip_landfire(product: Product, epsg: int, bounds, out_path: Path) -> Path:
    """Clip a LANDFIRE ImageServer layer to `bounds` (in EPSG:`epsg`), output native
    EPSG:5070 float32 metres + NaN. The bbox is reprojected ALS-UTM -> 5070, the pixels
    are served already in 5070 (no warp), then scaled to metres."""
    left, bottom, right, top = bounds
    tr = Transformer.from_crs(f"EPSG:{epsg}", f"EPSG:{LANDFIRE_EPSG}", always_xy=True)
    xs, ys = zip(*(tr.transform(x, y)
                   for x in (left, right) for y in (bottom, top)))
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    w = max(1, round((xmax - xmin) / product.native_res_m))
    h = max(1, round((ymax - ymin) / product.native_res_m))
    params = {
        "bbox": f"{xmin},{ymin},{xmax},{ymax}",
        "bboxSR": str(LANDFIRE_EPSG),
        "imageSR": str(LANDFIRE_EPSG),       # output in native Albers — no reprojection
        "size": f"{w},{h}",
        "format": "tiff",
        "pixelType": "S16",                  # raw values (U8 silently zeroes them)
        "interpolation": "RSP_NearestNeighbor",   # categorical/binned -> no blending
        "f": "image",
    }
    url = f"{product.arcgis_imageserver}/exportImage?" + urllib.parse.urlencode(params)
    out_path = Path(out_path)
    native = out_path.with_suffix(".native.tif")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            native.write_bytes(r.read())
        _to_float_metres(native, out_path, product)
    finally:
        native.unlink(missing_ok=True)
    return out_path

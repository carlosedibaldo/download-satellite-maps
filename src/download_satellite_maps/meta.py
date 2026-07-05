"""Meta global canopy-height maps (v1 Tolan 2024, v2 DINOv3 / Brandt 2026).

Both are ~1.19 m uint8-metre COGs in EPSG:3857, tiled on the Bing/Microsoft
quadkey grid and served over HTTPS with range requests:
  v1: dataforgood-fb-data.s3 .../chm/<quadkey>.tif        (zoom 9, 65536^2 px)
  v2: data.source.coop/tge-labs/meta-chm-v2/chm/<quadkey>.tif  (zoom 10, 32768^2)

A 1 km ALS tile fits inside one quadkey COG (occasionally spans 2-4 at an edge),
so we resolve the covering quadkeys from the footprint corners, /vsicurl them
(mosaic via VRT when >1), and clip with `gdal_translate -projwin` in the ALS
tile's UTM bounds while the OUTPUT stays NATIVE EPSG:3857 (no warp — preserves the
1.19 m Web Mercator grid). Values (uint8 metres, 0-254, 255=nodata) are normalized
to float32 metres + NaN by the shared `_to_float_metres`, like the other products.
"""
from __future__ import annotations

import math
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from pyproj import Transformer

from .clip import _GDAL_ENV, _to_float_metres
from .products import Product

_WEBMERC_LAT = 85.05112878   # Web Mercator latitude limit


def lonlat_to_quadkey(lon: float, lat: float, zoom: int) -> str:
    """Bing/Microsoft quadkey for the slippy tile containing (lon, lat) at `zoom`."""
    n = 1 << zoom
    lat = max(-_WEBMERC_LAT, min(_WEBMERC_LAT, lat))
    xt = min(n - 1, max(0, int((lon + 180.0) / 360.0 * n)))
    yt = min(n - 1, max(0, int(
        (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)))
    digits = []
    for i in range(zoom, 0, -1):
        d = 0
        mask = 1 << (i - 1)
        if xt & mask:
            d += 1
        if yt & mask:
            d += 2
        digits.append(str(d))
    return "".join(digits)


def _covering_quadkeys(epsg: int, bounds, zoom: int) -> list[str]:
    """Quadkeys covering an ALS footprint (UTM `bounds`) at `zoom`. The footprint is
    far smaller than a tile, so its corners + centre pin every tile it touches."""
    left, bottom, right, top = bounds
    tr = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    pts = [(left, bottom), (left, top), (right, bottom), (right, top),
           ((left + right) / 2.0, (bottom + top) / 2.0)]
    qks = set()
    for x, y in pts:
        lon, lat = tr.transform(x, y)
        qks.add(lonlat_to_quadkey(lon, lat, zoom))
    return sorted(qks)


def _url_exists(url: str) -> bool:
    """Probe a COG URL (covering quadkeys over ocean/no-data have no tile). Uses a
    1-byte ranged GET with a browser UA — source.coop's CDN 403s the default Python
    user-agent, and some hosts don't answer HEAD."""
    req = urllib.request.Request(
        url, method="GET",
        headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status in (200, 206)
    except Exception:  # noqa: BLE001 - 404/403/timeout all mean "skip this tile"
        return False


def clip_meta_tile(product: Product, epsg: int, bounds, out_path: Path) -> Path:
    """Clip the Meta product to `bounds` (in EPSG:`epsg`), output in native EPSG:3857
    float32 metres + NaN. Resolves the covering quadkey COG(s), mosaics if >1, then
    takes a pure native window (no warp)."""
    qks = _covering_quadkeys(epsg, bounds, product.tile_zoom)
    urls = [product.tile_url_template.format(quadkey=q) for q in qks]
    urls = [u for u in urls if _url_exists(u)]
    if not urls:
        raise FileNotFoundError(
            f"{product.id}: no COG for quadkeys {qks} (zoom {product.tile_zoom})")
    vsis = [f"/vsicurl/{u}" for u in urls]
    left, bottom, right, top = bounds
    work = Path(tempfile.mkdtemp(prefix="meta_"))
    native = work / f"native_{out_path.name}"
    env = {**os.environ, **_GDAL_ENV}
    try:
        if len(vsis) == 1:
            src = vsis[0]
        else:
            vrt = work / "mosaic.vrt"
            subprocess.run(["gdalbuildvrt", str(vrt), *vsis],
                           check=True, capture_output=True, text=True, env=env)
            src = str(vrt)
        subprocess.run(
            ["gdal_translate",
             "-projwin", str(left), str(top), str(right), str(bottom),
             "-projwin_srs", f"EPSG:{epsg}",   # bounds in ALS UTM; output stays native 3857
             "-co", "COMPRESS=DEFLATE",
             src, str(native)],
            check=True, capture_output=True, text=True, env=env)
        _to_float_metres(native, out_path, product)
    finally:
        native.unlink(missing_ok=True)
        for p in work.glob("*"):
            p.unlink(missing_ok=True)
        try:
            work.rmdir()
        except OSError:
            pass
    return out_path

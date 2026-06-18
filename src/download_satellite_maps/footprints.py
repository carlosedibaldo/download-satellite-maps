"""Derive ALS tile footprints (CRS + 1 km bounds + centroid lon/lat) for a site
from the ALS CHM tiles already in the bucket — so each satellite clip lands on
exactly the ALS tile grid."""
from __future__ import annotations

import re
import tempfile
from functools import lru_cache

import rasterio
from pyproj import Transformer

from .config import ALS_CHM_PREFIX
from . import storage

_TILE_RE = re.compile(r"_(\d{6})_(\d{7})_")
TILE_SIZE_M = 1000.0


def _chm_tifs(site: str) -> list[str]:
    return [
        e.path for e in storage.list_bucket(ALS_CHM_PREFIX.format(site=site), recursive=True)
        if getattr(e, "path", "").endswith(".tif")
    ]


@lru_cache(maxsize=None)
def site_epsg(site: str) -> int:
    """UTM EPSG for a site, read from one ALS CHM COG (authoritative)."""
    tifs = _chm_tifs(site)
    if not tifs:
        raise RuntimeError(f"no ALS CHM tiles found for site '{site}'")
    local = storage.download_one(tifs[0], tempfile.mkdtemp())
    with rasterio.open(local) as src:
        return src.crs.to_epsg()


def als_tile_footprints(site: str) -> list[dict]:
    """Unique tile footprints: {tile_id, epsg, bounds, lon, lat}."""
    epsg = site_epsg(site)
    to_wgs84 = Transformer.from_crs(epsg, 4326, always_xy=True)
    seen: dict[str, dict] = {}
    for path in _chm_tifs(site):
        m = _TILE_RE.search(path.split("/")[-1])
        if not m:
            continue
        e, n = int(m.group(1)), int(m.group(2))
        tid = f"{e}_{n}"
        if tid in seen:
            continue
        lon, lat = to_wgs84.transform(e + TILE_SIZE_M / 2, n + TILE_SIZE_M / 2)
        seen[tid] = {
            "tile_id": tid, "epsg": epsg,
            "bounds": (e, n, e + TILE_SIZE_M, n + TILE_SIZE_M),
            "lon": lon, "lat": lat,
        }
    return sorted(seen.values(), key=lambda d: d["tile_id"])

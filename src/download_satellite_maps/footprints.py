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
_YEAR_RE = re.compile(r"/chm/1m/(\d{4})/")   # ALS acquisition year in the CHM path
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
    """Unique tile footprints: {tile_id, epsg, bounds, lon, lat, years}.

    `years` is the sorted set of ALS acquisition years that tile was flown
    (parsed from the CHM path `chm/1m/<year>/`) — used to pick which years of a
    temporal product (e.g. ECHOSAT) to clip per tile.
    """
    epsg = site_epsg(site)
    to_wgs84 = Transformer.from_crs(epsg, 4326, always_xy=True)
    seen: dict[str, dict] = {}
    for path in _chm_tifs(site):
        m = _TILE_RE.search(path.split("/")[-1])
        if not m:
            continue
        e, n = int(m.group(1)), int(m.group(2))
        tid = f"{e}_{n}"
        ym = _YEAR_RE.search(path)
        year = int(ym.group(1)) if ym else None
        if tid not in seen:
            lon, lat = to_wgs84.transform(e + TILE_SIZE_M / 2, n + TILE_SIZE_M / 2)
            seen[tid] = {
                "tile_id": tid, "epsg": epsg,
                "bounds": (e, n, e + TILE_SIZE_M, n + TILE_SIZE_M),
                "lon": lon, "lat": lat, "years": set(),
            }
        if year is not None:
            seen[tid]["years"].add(year)
    out = sorted(seen.values(), key=lambda d: d["tile_id"])
    for f in out:
        f["years"] = sorted(f["years"])
    return out

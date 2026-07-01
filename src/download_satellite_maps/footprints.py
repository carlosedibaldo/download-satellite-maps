"""Derive ALS tile footprints (CRS + bounds + centroid lon/lat) for a site from the
ALS CHM COGs already in the bucket — so each satellite clip lands on exactly the ALS
tile grid. Bounds/CRS are read from each COG header (authoritative for ANY campaign's
tile naming/CRS); the tile_id is the trailing `<east>_<north>` of the CHM stem."""
from __future__ import annotations

import re
import tempfile
from functools import lru_cache

import rasterio
from pyproj import Transformer

from .config import ALS_CHM_PREFIX
from . import storage

# Trailing UTM/Lambert <east>_<north> of the CHM stem — robust across campaigns
# (NEON 725000_4696000, IGN 0486_6195, SBE 571000_562000, NCALM 70000_1959000, …).
_COORD_RE = re.compile(r"(\d+)_(\d+)$")
_YEAR_RE = re.compile(r"/chm/1m/(\d{4})/")   # ALS acquisition year in the CHM path


def _chm_tifs(acquisition: str, site: str) -> list[str]:
    prefix = ALS_CHM_PREFIX.format(acquisition=acquisition, site=site)
    return [
        e.path for e in storage.list_bucket(prefix, recursive=True)
        if getattr(e, "path", "").endswith(".tif")
    ]


def _tile_id(stem: str) -> str | None:
    m = _COORD_RE.search(stem)
    return f"{m.group(1)}_{m.group(2)}" if m else None


def als_tile_footprints(acquisition: str, site: str) -> list[dict]:
    """Unique tile footprints: {tile_id, epsg, bounds, lon, lat, years}.

    Bounds + EPSG are read from the actual CHM COG header (not parsed from the
    filename), so non-NEON tile namings/CRS are handled correctly. `years` is the
    sorted set of ALS acquisition years for that tile (from the `chm/1m/<year>/`
    path) — used to pick which years of a temporal product to clip.
    """
    seen: dict[str, dict] = {}
    work = tempfile.mkdtemp(prefix="foot_")
    for path in _chm_tifs(acquisition, site):
        fname = path.split("/")[-1]
        if not fname.endswith("_chm_1m.tif"):
            continue
        tid = _tile_id(fname[: -len("_chm_1m.tif")])
        if not tid:
            continue
        ym = _YEAR_RE.search(path)
        year = int(ym.group(1)) if ym else None
        if tid not in seen:
            local = storage.download_one(path, work)
            with rasterio.open(local) as src:
                b, epsg = src.bounds, src.crs.to_epsg()
            lon, lat = Transformer.from_crs(epsg, 4326, always_xy=True).transform(
                (b.left + b.right) / 2, (b.bottom + b.top) / 2)
            seen[tid] = {
                "tile_id": tid, "epsg": epsg,
                "bounds": (b.left, b.bottom, b.right, b.top),
                "lon": lon, "lat": lat, "years": set(),
            }
        if year is not None:
            seen[tid]["years"].add(year)
    out = sorted(seen.values(), key=lambda d: d["tile_id"])
    for f in out:
        f["years"] = sorted(f["years"])
    return out


@lru_cache(maxsize=None)
def site_epsg(acquisition: str, site: str) -> int:
    """UTM/projected EPSG for a site, from its first ALS CHM COG."""
    foots = als_tile_footprints(acquisition, site)
    if not foots:
        raise RuntimeError(f"no ALS CHM tiles found for '{acquisition}/{site}'")
    return foots[0]["epsg"]

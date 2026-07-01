"""download-satellite-maps: clip satellite canopy-height products to a site's
ALS tile footprints and upload to canopyboard-storage/satellite/.

    download-satellite-maps --acquisition neon --site harv --products eth gpw glad

Output: satellite/<product>/<acquisition>/<site>/<year>/<tile>_<product>_<year>.tif
Idempotent: skips clips already in the bucket (unless --overwrite).
"""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from . import storage
from .config import SATELLITE_PREFIX
from .clip import clip_to_tile
from .footprints import als_tile_footprints
from .products import PRODUCTS


def _dest(pid: str, acquisition: str, site: str, year) -> str:
    """Upload dir for one product/acquisition/site/year — the single source of
    truth for the satellite layout: `satellite/<pid>/<acquisition>/<site>/<year>/`.
    `<acquisition>` is the campaign top dir (neon, ign, sbe, ncalm, forestgeo),
    mirroring the ALS `ALS/<acquisition>/<site>/…` layout. The `<year>/` subdir
    declutters multi-year products and mirrors the ALS `<…>/<year>/…` layout."""
    return f"{SATELLITE_PREFIX}/{pid}/{acquisition}/{site}/{year}"


def _do_http_product(pid, product, foots, work, overwrite, acquisition) -> None:
    """Single-epoch HTTP products (eth/gpw): one native subset per tile."""
    dest = _dest(pid, acquisition, foots[0]["site"], product.epoch_year)
    ok = skip = err = 0
    for f in foots:
        name = f"{f['tile_id']}_{pid}_{product.epoch_year}.tif"
        key = f"{dest}/{name}"
        if not overwrite and storage.exists(key):
            skip += 1
            continue
        out = work / name
        try:
            clip_to_tile(product, f["epsg"], f["bounds"], out, f["lon"], f["lat"])
            storage.upload_file(out, dest)
            ok += 1
            print(f"  OK   {key}", flush=True)
        except Exception as e:  # noqa: BLE001
            err += 1
            print(f"  ERR  {pid} {f['tile_id']}: {repr(e)[:160]}", flush=True)
        finally:
            out.unlink(missing_ok=True)
    print(f"[{pid}] done: ok={ok} skip={skip} err={err}", flush=True)


def _do_landfire(pid, product, foots, work, overwrite, acquisition) -> None:
    """LANDFIRE ImageServer products (landfire_ch): one native-5070 clip per tile."""
    from .landfire import clip_landfire
    dest = _dest(pid, acquisition, foots[0]["site"], product.epoch_year)
    ok = skip = err = 0
    for f in foots:
        name = f"{f['tile_id']}_{pid}_{product.epoch_year}.tif"
        key = f"{dest}/{name}"
        if not overwrite and storage.exists(key):
            skip += 1
            continue
        out = work / name
        try:
            clip_landfire(product, f["epsg"], f["bounds"], out)
            storage.upload_file(out, dest)
            ok += 1
            print(f"  OK   {key}", flush=True)
        except Exception as e:  # noqa: BLE001
            err += 1
            print(f"  ERR  {pid} {f['tile_id']}: {repr(e)[:160]}", flush=True)
        finally:
            out.unlink(missing_ok=True)
    print(f"[{pid}] done: ok={ok} skip={skip} err={err}", flush=True)


def _do_meta(pid, product, foots, work, overwrite, acquisition) -> None:
    """Meta quadkey-tiled COGs (meta_v1/meta_v2): one native-3857 clip per tile."""
    from .meta import clip_meta_tile
    dest = _dest(pid, acquisition, foots[0]["site"], product.epoch_year)
    ok = skip = err = 0
    for f in foots:
        name = f"{f['tile_id']}_{pid}_{product.epoch_year}.tif"
        key = f"{dest}/{name}"
        if not overwrite and storage.exists(key):
            skip += 1
            continue
        out = work / name
        try:
            clip_meta_tile(product, f["epsg"], f["bounds"], out)
            storage.upload_file(out, dest)
            ok += 1
            print(f"  OK   {key}", flush=True)
        except Exception as e:  # noqa: BLE001
            err += 1
            print(f"  ERR  {pid} {f['tile_id']}: {repr(e)[:160]}", flush=True)
        finally:
            out.unlink(missing_ok=True)
    print(f"[{pid}] done: ok={ok} skip={skip} err={err}", flush=True)


def _do_gee_single(pid, product, foots, work, overwrite, ee_project, acquisition) -> None:
    """Single-epoch GEE products (glad): one clip per tile at product.epoch_year."""
    from .gee import clip_gee_band
    dest = _dest(pid, acquisition, foots[0]["site"], product.epoch_year)
    ok = skip = err = 0
    for f in foots:
        name = f"{f['tile_id']}_{pid}_{product.epoch_year}.tif"
        key = f"{dest}/{name}"
        if not overwrite and storage.exists(key):
            skip += 1
            continue
        out = work / name
        try:
            clip_gee_band(product, product.gee_band, f["epsg"], f["bounds"], out,
                          project=ee_project)
            storage.upload_file(out, dest)
            ok += 1
            print(f"  OK   {key}", flush=True)
        except Exception as e:  # noqa: BLE001
            err += 1
            print(f"  ERR  {pid} {f['tile_id']}: {repr(e)[:160]}", flush=True)
        finally:
            out.unlink(missing_ok=True)
    print(f"[{pid}] done: ok={ok} skip={skip} err={err}", flush=True)


def _do_gee_temporal(pid, product, foots, work, overwrite, ee_project, acquisition) -> None:
    """Temporal GEE products (ECHOSAT, GPW): one clip per tile per ALS-matched year.

    GPW has one ee.Image per year (filter by date); ECHOSAT has one mosaic with a
    band per year — `product.gee_temporal_by_date` selects the right clip function.
    """
    from .gee import clip_echosat_year, clip_gee_year_by_date
    clip_year = (clip_gee_year_by_date if product.gee_temporal_by_date
                 else clip_echosat_year)
    avail = set(product.temporal_years)
    ok = skip = err = 0
    for f in foots:
        years = sorted(set(f["years"]) & avail)   # ALS years the product covers
        if not years:
            print(f"  ..   {f['tile_id']}: no ALS year in {product.temporal_years}",
                  flush=True)
            continue
        for year in years:
            dest = _dest(pid, acquisition, f["site"], year)
            name = f"{f['tile_id']}_{pid}_{year}.tif"
            key = f"{dest}/{name}"
            if not overwrite and storage.exists(key):
                skip += 1
                continue
            out = work / name
            try:
                clip_year(product, year, f["epsg"], f["bounds"], out,
                          project=ee_project)
                storage.upload_file(out, dest)
                ok += 1
                print(f"  OK   {key}", flush=True)
            except Exception as e:  # noqa: BLE001
                err += 1
                print(f"  ERR  {pid} {f['tile_id']} {year}: {repr(e)[:160]}",
                      flush=True)
            finally:
                out.unlink(missing_ok=True)
    print(f"[{pid}] done: ok={ok} skip={skip} err={err}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--acquisition", default="neon",
                    help="campaign top dir (neon, ign, sbe, ncalm, forestgeo)")
    ap.add_argument("--site", required=True)
    ap.add_argument("--products", nargs="+", default=["eth", "gpw", "glad"],
                    choices=list(PRODUCTS))
    ap.add_argument("--ee-project", default="forest-als",
                    help="GCP project for Earth Engine (echosat only)")
    ap.add_argument("--tiles", nargs="+", default=None,
                    help="Restrict to these tile_ids (e.g. 724000_4699000)")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    acq = args.acquisition
    foots = als_tile_footprints(acq, args.site)
    if args.tiles:
        want = set(args.tiles)
        foots = [f for f in foots if f["tile_id"] in want]
    for f in foots:                                # carry site for dest paths
        f["site"] = args.site
    print(f"{acq}/{args.site}: {len(foots)} ALS tile footprints "
          f"(EPSG:{foots[0]['epsg'] if foots else '?'})", flush=True)

    work = Path(tempfile.mkdtemp(prefix="satmaps_"))
    for pid in args.products:
        product = PRODUCTS[pid]
        if product.gee_asset and product.temporal_years:
            _do_gee_temporal(pid, product, foots, work, args.overwrite, args.ee_project, acq)
        elif product.gee_asset:
            _do_gee_single(pid, product, foots, work, args.overwrite, args.ee_project, acq)
        elif product.tile_url_template is not None:
            _do_meta(pid, product, foots, work, args.overwrite, acq)
        elif product.arcgis_imageserver is not None:
            _do_landfire(pid, product, foots, work, args.overwrite, acq)
        elif product.url is not None:
            _do_http_product(pid, product, foots, work, args.overwrite, acq)
        else:
            print(f"[{pid}] not wired yet — {product.notes}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

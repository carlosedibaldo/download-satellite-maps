"""download-satellite-maps: clip satellite canopy-height products to a site's
ALS tile footprints and upload to canopyboard-storage/satellite/.

    download-satellite-maps --site harv --products eth gpw glad

Output: satellite/<product>/neon/<site>/<tile>_<product>_<year>.tif
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


def _do_http_product(pid, product, foots, work, overwrite) -> None:
    """Single-epoch HTTP products (eth/gpw): one native subset per tile."""
    dest = f"{SATELLITE_PREFIX}/{pid}/neon/{foots[0]['site']}"
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


def _do_meta(pid, product, foots, work, overwrite) -> None:
    """Meta quadkey-tiled COGs (meta_v1/meta_v2): one native-3857 clip per tile."""
    from .meta import clip_meta_tile
    dest = f"{SATELLITE_PREFIX}/{pid}/neon/{foots[0]['site']}"
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


def _do_gee_single(pid, product, foots, work, overwrite, ee_project) -> None:
    """Single-epoch GEE products (glad): one clip per tile at product.epoch_year."""
    from .gee import clip_gee_band
    dest = f"{SATELLITE_PREFIX}/{pid}/neon/{foots[0]['site']}"
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


def _do_echosat(pid, product, foots, work, overwrite, ee_project) -> None:
    """ECHOSAT (GEE, temporal): one clip per tile per ALS-matched year."""
    from .gee import clip_echosat_year
    dest = f"{SATELLITE_PREFIX}/{pid}/neon/{foots[0]['site']}"
    avail = set(product.temporal_years)
    ok = skip = err = 0
    for f in foots:
        years = sorted(set(f["years"]) & avail)   # ALS years covered by ECHOSAT
        if not years:
            print(f"  ..   {f['tile_id']}: no ALS year in {product.temporal_years}",
                  flush=True)
            continue
        for year in years:
            name = f"{f['tile_id']}_{pid}_{year}.tif"
            key = f"{dest}/{name}"
            if not overwrite and storage.exists(key):
                skip += 1
                continue
            out = work / name
            try:
                clip_echosat_year(product, year, f["epsg"], f["bounds"], out,
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
    ap.add_argument("--site", required=True)
    ap.add_argument("--products", nargs="+", default=["eth", "gpw", "glad"],
                    choices=list(PRODUCTS))
    ap.add_argument("--ee-project", default="forest-als",
                    help="GCP project for Earth Engine (echosat only)")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    foots = als_tile_footprints(args.site)
    for f in foots:                                # carry site for dest paths
        f["site"] = args.site
    print(f"{args.site}: {len(foots)} ALS tile footprints "
          f"(EPSG:{foots[0]['epsg'] if foots else '?'})", flush=True)

    work = Path(tempfile.mkdtemp(prefix="satmaps_"))
    for pid in args.products:
        product = PRODUCTS[pid]
        if product.gee_asset and product.temporal_years:
            _do_echosat(pid, product, foots, work, args.overwrite, args.ee_project)
        elif product.gee_asset:
            _do_gee_single(pid, product, foots, work, args.overwrite, args.ee_project)
        elif product.tile_url_template is not None:
            _do_meta(pid, product, foots, work, args.overwrite)
        elif product.url is not None:
            _do_http_product(pid, product, foots, work, args.overwrite)
        else:
            print(f"[{pid}] not wired yet — {product.notes}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

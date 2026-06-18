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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", required=True)
    ap.add_argument("--products", nargs="+", default=["eth", "gpw", "glad"],
                    choices=list(PRODUCTS))
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    foots = als_tile_footprints(args.site)
    print(f"{args.site}: {len(foots)} ALS tile footprints "
          f"(EPSG:{foots[0]['epsg'] if foots else '?'})", flush=True)

    work = Path(tempfile.mkdtemp(prefix="satmaps_"))
    for pid in args.products:
        product = PRODUCTS[pid]
        if product.url is None and not product.regional:
            print(f"[{pid}] not wired yet — {product.notes}", flush=True)
            continue
        dest = f"{SATELLITE_PREFIX}/{pid}/neon/{args.site}"
        ok = skip = err = 0
        for f in foots:
            name = f"{f['tile_id']}_{pid}_{product.epoch_year}.tif"
            key = f"{dest}/{name}"
            if not args.overwrite and storage.exists(key):
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

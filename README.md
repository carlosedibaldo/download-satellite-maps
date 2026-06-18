# download-satellite-maps

Download satellite **canopy-height products** clipped to **ALS tile boundaries**
and store them on Hugging Face, for validating against the ALS CHMs.

Division of labour:
- **This repo** — clip each product to each ALS tile footprint → COG → HF.
- **canopyboard** — sample these clips (+ the ALS CHM) → parquet → leaderboard.

## Output
Xet bucket `canopyboard/canopyboard-storage`:

```
satellite/<product>/neon/<site>/<tile>_<product>_<year>.tif
```

One clip per ALS tile *footprint* (single-epoch global maps → year-independent,
reused across all ALS acquisition years). CRS + 1 km bounds match the ALS tile
grid; native resolution per product.

## Products
| id | source | res | epoch | status |
|----|--------|-----|-------|--------|
| `eth`  | ETH/Lang global S2 CHM (libdrive VRT) | 10 m | 2020 | ✅ |
| `gpw`  | GPW short-veg height (Zenodo) | 90 m | 2017 | ✅ |
| `glad` | GLAD/Potapov forest height (UMD, per-region) | 30 m | 2019 | ✅ (regional resolver) |
| `meta` | Meta CHM (Tolan) — AWS S3 quadkey tiles | 1 m | 2024 | 🔧 TODO (S3 tiling) |

## Usage
```bash
download-satellite-maps --site harv --products eth gpw glad
```
Idempotent (skips existing clips). Tile footprints are derived from the ALS CHM
tiles already in the bucket (`ALS/neon/<site>/chm/1m/...`).

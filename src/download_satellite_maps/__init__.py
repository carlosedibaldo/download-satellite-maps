"""download-satellite-maps — clip satellite canopy-height products to ALS tile
boundaries and store them on Hugging Face for downstream sampling.

Output layout (Xet bucket `canopyboard/canopyboard-storage`):
    satellite/<product>/neon/<site>/<tile>_<product>_<year>.tif

Products are single-epoch global maps, so a clip is keyed by the ALS tile
*footprint* (year-independent) and reused across all ALS acquisition years.
The canopyboard repo then samples these clips → parquet for the leaderboard.
"""
__version__ = "0.1.0"

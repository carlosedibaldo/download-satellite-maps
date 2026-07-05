"""download-satellite-maps — clip satellite canopy-height products to ALS tile
boundaries and store them on Hugging Face for downstream sampling.

Output layout (Xet bucket `canopyboard/canopyboard-storage`):
    satellite/<product>/neon/<site>/<year>/<tile>_<product>_<year>.tif

The `<year>/` subdir keeps multi-year products (gpw/echosat) separable and mirrors
the ALS `<…>/<year>/…` layout. Single-epoch products (eth/glad/…) file under their
one epoch year. The canopyboard repo then samples these clips → parquet.
"""
__version__ = "0.1.0"

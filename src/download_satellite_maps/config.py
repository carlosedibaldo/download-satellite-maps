import os

# Derived artifacts live in the PRIVATE Xet bucket (same as the ALS CHMs).
HF_BUCKET = os.getenv("HF_BUCKET", "canopyboard/canopyboard-storage")
# satellite clips sit at a top-level sibling of ALS/ in the bucket.
SATELLITE_PREFIX = "satellite"
# ALS CHM tiles (used to derive tile footprints): ALS/neon/<site>/chm/1m/...
ALS_CHM_PREFIX = "ALS/neon/{site}/chm/1m"

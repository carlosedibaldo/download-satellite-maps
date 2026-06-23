"""Registry of satellite canopy-height products + their public raster sources.

Ported from canopyboard's `subset_product_extraction.py` / `real_data_import.py`,
but using the GLOBAL sources (canopyboard hardcoded South-America tiles). Each
product is a single-epoch global map; `epoch_year` goes into the output filename.
"""
from __future__ import annotations

from dataclasses import dataclass

# All clips are written as float32 CANOPY HEIGHT IN METRES with NaN nodata, so
# the public products are unit- and nodata-consistent. NaN can never collide with
# a real height and QGIS/GDAL/rasterio mask it automatically. Heights stay
# full-precision float (submetre precision is illusory but we don't round, to keep
# the values unaltered) — only the documented per-product scale is applied and the
# source sentinels are remapped to NaN. Geometry/CRS are NOT touched (no warp).
NODATA = float("nan")


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    epoch_year: int
    native_res_m: float
    url: str | None = None            # single global source (/vsicurl)
    regional: bool = False            # GLAD: per-region tiles
    url_template: str | None = None   # regional: format with {region}
    scale_factor: float = 1.0         # SOURCE value -> metres (e.g. GPW dm *0.1)
    nodata: float | None = None       # source in-band fill -> NODATA
    invalid_values: tuple = ()        # extra source sentinels -> NODATA
    gee_asset: str | None = None      # Earth Engine asset id (not /vsicurl-able)
    temporal_years: tuple[int, ...] = ()  # per-year layers (temporal products)
    notes: str = ""


ETH = Product(
    id="eth", name="ETH/Lang Global Sentinel-2 Canopy Height", epoch_year=2020,
    native_res_m=10.0, nodata=255.0,
    url=("https://libdrive.ethz.ch/public.php/dav/files/cO8or7iOe5dT2Rt/"
         "ETH_GlobalCanopyHeight_10m_2020_mosaic_Map.vrt"),
)
GPW = Product(
    id="gpw", name="GPW Global Short Vegetation Height", epoch_year=2017,
    native_res_m=90.0, scale_factor=0.1, nodata=-32000.0,
    url=("https://zenodo.org/api/records/15198672/files/"
         "gpw_short.veg.height_egbt_m_90m_s_20170101_20171231_go_epsg.4326_v1.tif/content"),
)
GLAD = Product(
    id="glad", name="GLAD/Potapov Global Forest Canopy Height", epoch_year=2019,
    native_res_m=30.0, regional=True, invalid_values=(101.0, 102.0, 103.0),
    url_template=("https://glad.geog.umd.edu/Potapov/Forest_height_2019/"
                  "Forest_height_2019_{region}.tif"),
    notes="raster values 101/102/103 = water/snow-ice/nodata (mask downstream)",
)
META = Product(
    id="meta", name="Meta Global Canopy Height (Tolan et al.)", epoch_year=2024,
    native_res_m=1.0,
    notes=("TODO: distributed as AWS S3 quadkey tiles "
           "s3://dataforgood-fb-data/forests/v1/alsgedi_global_v6_float/ — needs "
           "tile-intersection + mosaic before clip."),
)
ECHOSAT = Product(
    id="echosat", name="AI4Forest ECHOSAT temporal canopy height", epoch_year=2024,
    native_res_m=10.0, scale_factor=0.01, nodata=None,   # source cm; masked (no in-band fill)
    gee_asset="projects/ai4forest/assets/echosat",
    temporal_years=tuple(range(2018, 2025)),   # 2018–2024 → bands b1..b7 (in order)
    notes=("GEE ImageCollection of UTM tiles, 10 m. Source is int16 cm with 7 "
           "bands b1..b7 = years 2018..2024; written as float32 metres (*0.01) "
           "with nodata NODATA. CC-BY 4.0, Pauls et al. 2026 arXiv:2602.21421. "
           "GEE-only (not /vsicurl); clipped per ALS-matched year — see gee.py."),
)

PRODUCTS: dict[str, Product] = {p.id: p for p in (ETH, GPW, GLAD, META, ECHOSAT)}


def glad_region(lon: float, lat: float) -> str:
    """Map a point to a Potapov-2019 regional tile code (coarse continental boxes)."""
    if lat < 12 and -82 <= lon <= -33:
        return "SAM"                              # South America
    if lon <= -30:
        return "NAM"                              # North/Central America
    if -30 < lon <= 60 and lat < 38:
        return "AFR"                              # Africa
    if -30 < lon <= 60:
        return "EURO"                             # Europe / W Asia
    if lat >= 38:
        return "NASIA"                            # N Asia
    if lat < -10 and lon > 100:
        return "AUS"                              # Australia / Oceania
    return "SASIA"                                # S/SE Asia (fallback)

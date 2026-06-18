"""Registry of satellite canopy-height products + their public raster sources.

Ported from canopyboard's `subset_product_extraction.py` / `real_data_import.py`,
but using the GLOBAL sources (canopyboard hardcoded South-America tiles). Each
product is a single-epoch global map; `epoch_year` goes into the output filename.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    epoch_year: int
    native_res_m: float
    url: str | None = None            # single global source (/vsicurl)
    regional: bool = False            # GLAD: per-region tiles
    url_template: str | None = None   # regional: format with {region}
    scale_factor: float = 1.0         # applied after masking (e.g. GPW int*0.1 -> m)
    nodata: float | None = None       # raster fill mapped to NaN
    invalid_values: tuple = ()        # extra sentinel values mapped to NaN
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

PRODUCTS: dict[str, Product] = {p.id: p for p in (ETH, GPW, GLAD, META)}


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

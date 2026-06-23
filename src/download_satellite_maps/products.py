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
    scale_factor: float = 1.0         # SOURCE value -> metres (e.g. GPW dm *0.1)
    nodata: float | None = None       # source in-band fill -> NODATA
    invalid_values: tuple = ()        # extra source sentinels -> NODATA
    gee_asset: str | None = None      # Earth Engine asset id (not /vsicurl-able)
    gee_band: str = "b1"              # band id for single-epoch GEE assets
    gee_native_epsg: int | None = None  # output CRS for GEE clips (None=ALS tile UTM)
    temporal_years: tuple[int, ...] = ()  # per-year layers (temporal products)
    tile_zoom: int | None = None      # Bing/MS quadkey zoom (Meta: v1=9, v2=10)
    tile_url_template: str | None = None  # quadkey COG url, format with {quadkey}
    arcgis_imageserver: str | None = None  # LANDFIRE LFPS ImageServer base url
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
    native_res_m=30.0, invalid_values=(101.0, 102.0, 103.0),
    gee_asset="users/potapovpeter/GEDI_V27", gee_band="b1", gee_native_epsg=4326,
    notes=("GEDI+Landsat 2019 (Potapov et al. 2020). GEE ImageCollection of 7 "
           "regional tiles, single band b1, filterBounds+mosaic stitches them. "
           "Native CRS is global EPSG:4326 (output kept there, not warped to UTM). "
           "Source values 101/102/103 = water/snow-ice/nodata -> NaN. Replaces the "
           "dead glad.umd.edu /vsicurl source. Mirror: "
           "projects/sat-io/open-datasets/GLAD/GEDI_V27."),
)
# Meta global canopy height: ~1.19 m uint8 metres (0-254, 255=nodata), EPSG:3857,
# tiled on the Bing quadkey grid and served as /vsicurl COGs. Kept in native 3857
# (no warp — preserves the 1 m grid). See meta.py for the quadkey-tile clip path.
_META_RES = 1.1943285669558747   # native Web Mercator pixel size (m)
META_V1 = Product(
    id="meta_v1", name="Meta Global Canopy Height v1 (Tolan et al. 2024)",
    epoch_year=2020, native_res_m=_META_RES, nodata=255.0, tile_zoom=9,
    tile_url_template=("https://dataforgood-fb-data.s3.amazonaws.com/forests/v1/"
                       "alsgedi_global_v6_float/chm/{quadkey}.tif"),
    notes=("AWS Open Data (dataforgood-fb-data), zoom-9 quadkey COGs, 65536^2 px. "
           "uint8 metres, EPSG:3857, native ~1.19 m -> float32 m + NaN. Tolan et al. "
           "2024 arXiv:2304.07213. epoch_year=2020 = nominal canopy reference."),
)
META_V2 = Product(
    id="meta_v2", name="Meta Global Canopy Height v2 (DINOv3, Brandt et al. 2026)",
    epoch_year=2020, native_res_m=_META_RES, nodata=255.0, tile_zoom=10,
    tile_url_template=("https://data.source.coop/tge-labs/meta-chm-v2/chm/"
                       "{quadkey}.tif"),
    notes=("source.coop tge-labs/meta-chm-v2, zoom-10 quadkey COGs, 32768^2 px. "
           "uint8 metres, EPSG:3857, native ~1.19 m -> float32 m + NaN. DINOv3 "
           "model ml3, Brandt et al. 2026 arXiv:2603.06382. CC-BY 4.0."),
)
ECHOSAT = Product(
    id="echosat", name="AI4Forest ECHOSAT temporal canopy height", epoch_year=2024,
    native_res_m=10.0, scale_factor=0.01, nodata=None,   # source cm; masked (no in-band fill)
    gee_asset="projects/ai4forest/assets/echosat",
    gee_native_epsg=None,   # native MGRS UTM (ALS-tile zone); avoid needless warp.
    # gee_native_epsg=4326,  # <- uncomment for the authors' README export CRS.
    temporal_years=tuple(range(2018, 2025)),   # 2018–2024 → bands b1..b7 (in order)
    notes=("GEE ImageCollection of per-MGRS-tile UTM images, 10 m. Source is int16 "
           "cm with 7 bands b1..b7 = years 2018..2024; written as float32 metres "
           "(*0.01) with nodata NODATA. Output kept in its native UTM (the ALS tile's "
           "zone) so the only reprojection is the one onto the ALS grid at validation "
           "time. CC-BY 4.0, Pauls et al. 2026 arXiv:2602.21421. GEE-only (not "
           "/vsicurl); clipped per ALS-matched year — see gee.py."),
)

IS2CHM = Product(
    id="is2chm", name="ICESat-2 Canopy Height CONUS (Malambo & Popescu 2025)",
    epoch_year=2020, native_res_m=30.0, scale_factor=0.1, gee_native_epsg=4326,
    gee_asset="projects/sat-io/open-datasets/ICESAT/CHM_CONUS", gee_band="b1",
    notes=("GEE ImageCollection (6 CONUS regional tiles), band b1, native EPSG:4326 "
           "~30 m. Source int *0.1 -> metres (0-54 m). 2019-2021 epoch (epoch_year="
           "2020 nominal). Malambo & Popescu 2025, doi:10.5067/J8DMNXTBZ22J. "
           "CONUS-only; dispatches via _do_gee_single like GLAD."),
)

LANDFIRE_CH = Product(
    id="landfire_ch", name="LANDFIRE Forest Canopy Height (LF2024)",
    epoch_year=2024, native_res_m=30.0, scale_factor=0.1, nodata=-9999.0,
    arcgis_imageserver=("https://lfps.usgs.gov/arcgis/rest/services/"
                        "Landfire_LF2024/LF2024_CH_CONUS/ImageServer"),
    notes=("LFPS ArcGIS ImageServer exportImage (synchronous), native EPSG:5070 30 m. "
           "int16 metres*10 (0-510 -> 0-51 m; 0 = non-forest; -9999 nodata) -> float32 "
           "m + NaN. Uses LF2024 not LF2025: the LF2025 service only serves the western "
           "US so far (eastern GeoAreas incl. HARV are NoData) — LF2024 is the most "
           "recent CH with national coverage. CONUS-only. See landfire.py."),
)

PRODUCTS: dict[str, Product] = {
    p.id: p for p in (ETH, GPW, GLAD, ECHOSAT, META_V1, META_V2, IS2CHM, LANDFIRE_CH)
}

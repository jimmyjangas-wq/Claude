"""Default NZ land-use materials and name-matching rules.

Values are typical of New Zealand flood modelling practice and are compiled
from commonly used references:

- Auckland Council Stormwater "Hydraulic / Hydrological Modelling Specifications"
- Christchurch City Council "Waterways, Wetlands and Drainage Guide" (WWDG)
- Waikato Regional Council flood modelling technical reports
- TUFLOW Manual (BMT) recommended Manning's n ranges
- Chow (1959) Open Channel Hydraulics

They are sensible defaults for a first model build. They MUST be reviewed and,
where required, adjusted/calibrated by the modeller for the specific project
and the relevant council's modelling specification before results are relied
upon.

Losses (initial loss IL in mm, continuing loss CL in mm/hr) are for direct
rainfall ("rain on grid") modelling and follow common NZ practice of low
losses on impervious surfaces and moderate losses on pervious surfaces.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Material library
# ---------------------------------------------------------------------------
# id: TUFLOW material ID written to the 2d_mat layer and materials.csv
# name: human readable land-use name
# n: Manning's n
# il / cl: initial loss (mm) and continuing loss (mm/hr) for rain-on-grid
# imperv: fraction impervious (used for reporting / hydrology summaries)
DEFAULT_MATERIALS: list[dict] = [
    {"id": 1,  "name": "Road / Sealed Pavement",      "n": 0.020, "il": 1.0,  "cl": 0.0, "imperv": 1.00},
    {"id": 2,  "name": "Building / Roof",             "n": 0.300, "il": 1.0,  "cl": 0.0, "imperv": 1.00},
    {"id": 3,  "name": "Car Park / Concrete Apron",   "n": 0.018, "il": 1.0,  "cl": 0.0, "imperv": 1.00},
    {"id": 4,  "name": "Residential (mixed lot)",     "n": 0.080, "il": 2.0,  "cl": 1.0, "imperv": 0.55},
    {"id": 5,  "name": "Commercial / Industrial",     "n": 0.050, "il": 1.0,  "cl": 0.5, "imperv": 0.85},
    {"id": 6,  "name": "Open Space / Mown Grass",     "n": 0.035, "il": 5.0,  "cl": 2.5, "imperv": 0.00},
    {"id": 7,  "name": "Pasture / Rural Grass",       "n": 0.040, "il": 5.0,  "cl": 2.5, "imperv": 0.00},
    {"id": 8,  "name": "Crops / Horticulture",        "n": 0.060, "il": 5.0,  "cl": 2.5, "imperv": 0.00},
    {"id": 9,  "name": "Scrub / Shrubland",           "n": 0.070, "il": 7.5,  "cl": 3.0, "imperv": 0.00},
    {"id": 10, "name": "Native Bush / Forest",        "n": 0.120, "il": 10.0, "cl": 4.0, "imperv": 0.00},
    {"id": 11, "name": "Wetland",                     "n": 0.080, "il": 2.0,  "cl": 0.5, "imperv": 0.00},
    {"id": 12, "name": "Stream / Open Channel",       "n": 0.035, "il": 0.0,  "cl": 0.0, "imperv": 1.00},
    {"id": 13, "name": "Concrete Lined Channel",      "n": 0.015, "il": 0.0,  "cl": 0.0, "imperv": 1.00},
    {"id": 14, "name": "Lake / Pond / Open Water",    "n": 0.025, "il": 0.0,  "cl": 0.0, "imperv": 1.00},
    {"id": 15, "name": "Gravel / Unsealed Road",      "n": 0.030, "il": 2.0,  "cl": 1.0, "imperv": 0.50},
    {"id": 16, "name": "Bare Earth / Construction",   "n": 0.025, "il": 3.0,  "cl": 2.0, "imperv": 0.10},
]

# ---------------------------------------------------------------------------
# Keyword rules for automatic assignment from catchment / land-use names
# ---------------------------------------------------------------------------
# Each rule is (list of keywords, material id). Rules are evaluated in order
# and the first rule with any keyword found (case-insensitive substring) in
# the catchment name wins. Keep the more specific keywords first.
DEFAULT_NAME_RULES: list[tuple[list[str], int]] = [
    (["concrete channel", "lined channel", "flume"],                    13),
    (["carpark", "car park", "car_park", "parking", "apron", "concrete"], 3),
    (["road", "rd_", "_rd", "street", "highway", "motorway", "pavement",
      "sealed", "driveway", "footpath", "accessway"],                    1),
    (["building", "bldg", "roof", "house", "dwelling", "shed", "garage",
      "warehouse", "structure"],                                         2),
    (["commercial", "industrial", "retail", "business", "comm_",
      "town centre", "town center", "cbd"],                              5),
    (["residential", "resi", "urban", "lot", "housing", "subdivision",
      "development", "dev_", "_dev"],                                    4),
    (["wetland", "swale", "raingarden", "rain garden", "bioretention",
      "detention", "retention", "basin"],                                11),
    (["lake", "pond", "reservoir", "dam", "water body", "waterbody",
      "lagoon", "estuary"],                                              14),
    (["stream", "creek", "river", "channel", "drain", "waterway",
      "watercourse", "awa", "gully floor"],                              12),
    (["bush", "forest", "native", "trees", "woodlot", "pines", "pine",
      "plantation", "ngahere", "totara", "kauri", "manuka", "kanuka"],   10),
    (["scrub", "shrub", "gorse", "regenerat", "revegetat"],               9),
    (["crop", "horticult", "orchard", "vineyard", "market garden",
      "maize", "kiwifruit"],                                              8),
    (["pasture", "paddock", "rural", "farm", "grazing", "stock",
      "dairy", "sheep"],                                                  7),
    (["park", "reserve", "lawn", "grass", "open space", "openspace",
      "field", "sports", "playground", "berm", "esplanade"],              6),
    (["gravel", "unsealed", "metal road", "shingle"],                     15),
    (["bare", "earthworks", "construction", "cleared", "stripped",
      "exposed"],                                                         16),
]

# Material id used when no rule matches a catchment name.
DEFAULT_FALLBACK_MATERIAL_ID = 7  # Pasture / Rural Grass (conservative rural default)

# ---------------------------------------------------------------------------
# Design events — common NZ reporting set
# ---------------------------------------------------------------------------
# AEPs typically required by NZ councils for flood assessments. The 10% and 1%
# AEP events are near-universal; 50%/20%/2% are often added for freeboard,
# habitability and network-performance assessments.
DEFAULT_AEPS: list[float] = [50.0, 20.0, 10.0, 5.0, 2.0, 1.0]

# Standard HIRDS v4 durations (hours) for the DDF table.
HIRDS_DURATIONS_HR: list[float] = [
    1 / 6, 1 / 3, 0.5, 1, 2, 6, 12, 24, 48, 72, 96, 120,
]

# Climate change: MfE guidance derives rainfall augmentation from projected
# temperature increase. ~8 %/degC is the commonly applied default for short
# duration events (MfE 2008/2018 guidance; HIRDS v4 provides scenario-specific
# factors). The app lets you override these per scenario.
MFE_PCT_PER_DEGC = 8.0
DEFAULT_CC_SCENARIOS: list[dict] = [
    {"name": "EX",     "label": "Existing climate",         "deltaT": 0.0},
    {"name": "CC2.1",  "label": "RCP6.0 ~2100 (+2.1 degC)", "deltaT": 2.1},
    {"name": "CC3.8",  "label": "RCP8.5 ~2100 (+3.8 degC)", "deltaT": 3.8},
]

# Default storm durations (hours) to run. 24 hr nested storms are the common
# NZ council requirement; shorter durations are added to capture critical
# duration for small/steep urban catchments.
DEFAULT_STORM_DURATIONS_HR: list[float] = [1.0, 2.0, 6.0, 24.0]

# Default 2D cell size (m) and timestep guidance
DEFAULT_CELL_SIZE = 2.0

# Default NZ projection: NZGD2000 / New Zealand Transverse Mercator
DEFAULT_EPSG = 2193

# Sample HIRDS-style DDF depths (mm) used for demo/sample data only —
# loosely representative of an Auckland-region site. ALWAYS replace with a
# real HIRDS v4 export for the project site.
SAMPLE_DDF: dict[float, dict[float, float]] = {
    # AEP %: {duration hr: depth mm}
    50.0: {1/6: 9,  1/3: 13, 0.5: 16, 1: 22, 2: 29, 6: 44, 12: 56, 24: 70,  48: 87,  72: 98,  96: 106, 120: 113},
    20.0: {1/6: 12, 1/3: 17, 0.5: 21, 1: 29, 2: 38, 6: 57, 12: 72, 24: 89,  48: 110, 72: 124, 96: 134, 120: 142},
    10.0: {1/6: 14, 1/3: 20, 0.5: 25, 1: 34, 2: 45, 6: 67, 12: 84, 24: 104, 48: 128, 72: 144, 96: 155, 120: 164},
    5.0:  {1/6: 16, 1/3: 23, 0.5: 29, 1: 39, 2: 52, 6: 77, 12: 97, 24: 119, 48: 146, 72: 164, 96: 177, 120: 187},
    2.0:  {1/6: 19, 1/3: 27, 0.5: 34, 1: 46, 2: 61, 6: 91, 12: 114, 24: 139, 48: 171, 72: 191, 96: 206, 120: 218},
    1.0:  {1/6: 22, 1/3: 31, 0.5: 39, 1: 52, 2: 69, 6: 102, 12: 128, 24: 156, 48: 191, 72: 214, 96: 230, 120: 243},
}

"""NZ TUFLOW Flood Model Builder.

Builds a complete pre/post-development TUFLOW model package from GIS
catchment layers: auto-assigned roughness/losses from catchment names,
HIRDS-based nested design storms with climate change, TUFLOW control files,
GIS layers and a build report.
"""

from .config import BuildConfig, CCScenario, Material
from .catchments import (assign_materials, compare_scenarios, match_material,
                         read_catchments, scenario_summary, unmatched_names)
from .rainfall import (build_all_storms, load_ddf_csv, nested_storm,
                       sample_ddf, storm_to_tuflow_csv)
from .writer import build_model
from .reporting import write_report
from .sample_data import make_sample_catchments

__version__ = "1.0.0"

__all__ = [
    "BuildConfig", "CCScenario", "Material",
    "read_catchments", "assign_materials", "match_material",
    "scenario_summary", "compare_scenarios", "unmatched_names",
    "load_ddf_csv", "nested_storm", "storm_to_tuflow_csv", "build_all_storms",
    "sample_ddf", "build_model", "write_report", "make_sample_catchments",
]

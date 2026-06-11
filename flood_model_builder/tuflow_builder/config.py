"""Model build configuration objects and YAML round-tripping."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path

import yaml

from . import defaults


@dataclass
class Material:
    id: int
    name: str
    n: float
    il: float = 0.0
    cl: float = 0.0
    imperv: float = 0.0


@dataclass
class CCScenario:
    """Climate change scenario expressed as a rainfall uplift.

    If ``uplift_pct`` is None it is derived from ``deltaT`` using the MfE
    percent-per-degree default.
    """

    name: str
    label: str = ""
    deltaT: float = 0.0
    uplift_pct: float | None = None

    @property
    def factor(self) -> float:
        pct = self.uplift_pct
        if pct is None:
            pct = self.deltaT * defaults.MFE_PCT_PER_DEGC
        return 1.0 + pct / 100.0


@dataclass
class BuildConfig:
    """Everything needed to build a pre/post TUFLOW model."""

    project_name: str = "Project"
    model_id: str = "FM01"
    epsg: int = defaults.DEFAULT_EPSG

    # GIS inputs
    pre_catchments: str = ""           # path to pre-development catchment layer
    post_catchments: str = ""          # path to post-development catchment layer
    name_field: str = ""               # attribute holding catchment/land-use name ("" = auto-detect)
    dem_path: str = "grid\\DEM.tif"    # referenced in the TGC, relative to model/ (user supplies the raster)

    # Grid
    cell_size: float = defaults.DEFAULT_CELL_SIZE
    grid_buffer: float = 50.0          # m buffer applied around catchments for the 2D domain

    # Hydrology
    aeps: list[float] = field(default_factory=lambda: list(defaults.DEFAULT_AEPS))
    storm_durations_hr: list[float] = field(
        default_factory=lambda: list(defaults.DEFAULT_STORM_DURATIONS_HR))
    hyetograph_dt_min: float = 5.0
    cc_scenarios: list[CCScenario] = field(default_factory=lambda: [
        CCScenario(**s) for s in defaults.DEFAULT_CC_SCENARIOS])

    # Run control
    run_time_buffer_hr: float = 3.0    # simulation continues this long after rain stops
    timestep_2d: float | None = None   # None => cell_size / 2 (HPC adaptive start)
    output_interval_s: float = 300.0
    hardware_gpu: bool = True

    # Materials / assignment
    materials: list[Material] = field(default_factory=lambda: [
        Material(**m) for m in defaults.DEFAULT_MATERIALS])
    name_rules: list[tuple[list[str], int]] = field(
        default_factory=lambda: [(list(k), v) for k, v in defaults.DEFAULT_NAME_RULES])
    fallback_material_id: int = defaults.DEFAULT_FALLBACK_MATERIAL_ID

    # Output
    output_dir: str = "tuflow_model"
    gis_format: str = "gpkg"           # "gpkg" or "shp"

    # ------------------------------------------------------------------
    def material_by_id(self, mat_id: int) -> Material:
        for m in self.materials:
            if m.id == mat_id:
                return m
        raise KeyError(f"Material id {mat_id} not in materials table")

    def to_yaml(self, path: str | Path) -> None:
        data = asdict(self)
        Path(path).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    @classmethod
    def from_yaml(cls, path: str | Path) -> "BuildConfig":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "BuildConfig":
        data = dict(data)
        if "materials" in data:
            data["materials"] = [Material(**m) for m in data["materials"]]
        if "cc_scenarios" in data:
            data["cc_scenarios"] = [CCScenario(**s) for s in data["cc_scenarios"]]
        if "name_rules" in data:
            data["name_rules"] = [(list(k), int(v)) for k, v in data["name_rules"]]
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

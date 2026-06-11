"""End-to-end and unit tests for the TUFLOW builder."""

import math
from pathlib import Path

import pandas as pd
import pytest

from tuflow_builder import (BuildConfig, assign_materials, build_all_storms,
                            build_model, make_sample_catchments, match_material,
                            nested_storm, read_catchments, sample_ddf,
                            storm_to_tuflow_csv, write_report)
from tuflow_builder.rainfall import (aep_event_name, depth_for_duration,
                                     duration_event_name, load_ddf_csv)


@pytest.fixture()
def cfg(tmp_path):
    c = BuildConfig(project_name="Test", model_id="TST",
                    aeps=[10.0, 1.0], storm_durations_hr=[1.0, 24.0],
                    output_dir=str(tmp_path / "model_out"))
    pre, post = make_sample_catchments(tmp_path / "data")
    c.pre_catchments, c.post_catchments = str(pre), str(post)
    return c


# ---------------------------------------------------------------- name matching

def test_name_matching(cfg):
    assert cfg.material_by_id(match_material("Road Network", cfg)[0]).name.startswith("Road")
    assert match_material("Residential Stage 1", cfg)[0] == 4
    assert match_material("Native Bush Reserve", cfg)[0] == 10
    assert match_material("Stream Corridor", cfg)[0] == 12
    assert match_material("Detention Basin", cfg)[0] == 11
    # unmatched falls back
    mat, kw = match_material("Zone XYZ", cfg)
    assert mat == cfg.fallback_material_id and kw == ""


def test_assignment_and_summary(cfg):
    pre = assign_materials(read_catchments(cfg.pre_catchments, cfg), cfg, "PRE")
    assert {"material", "n", "il", "cl", "area_ha"} <= set(pre.columns)
    assert (pre["n"] > 0).all()
    assert pre["area_ha"].sum() == pytest.approx(24.0, rel=0.01)  # 600x400 m site


# ---------------------------------------------------------------- rainfall

def test_ddf_interpolation():
    row = sample_ddf()[1.0]
    d1, d2, d6 = row[1], row[2], row[6]
    mid = depth_for_duration(row, 4.0)
    assert d2 < mid < d6
    assert depth_for_duration(row, 1.0) == pytest.approx(d1)


def test_nested_storm_conserves_depth():
    row = sample_ddf()[1.0]
    storm = nested_storm(row, 24.0, 5.0)
    assert storm["rain_mm"].sum() == pytest.approx(row[24], rel=1e-3)
    # peak block at the centre
    peak_t = storm.loc[storm["rain_mm"].idxmax(), "time_hr"]
    assert abs(peak_t - 12.0) < 1.0
    assert (storm["rain_mm"] >= 0).all()


def test_storm_cc_uplift():
    row = sample_ddf()[1.0]
    base = nested_storm(row, 24.0, 5.0, 1.0)["rain_mm"].sum()
    cc = nested_storm(row, 24.0, 5.0, 1.168)["rain_mm"].sum()
    assert cc == pytest.approx(base * 1.168, rel=1e-4)  # blocks rounded to 4 dp


def test_tuflow_csv_monotonic():
    storm = nested_storm(sample_ddf()[10.0], 6.0, 5.0)
    ts = storm_to_tuflow_csv(storm, run_time_buffer_hr=3.0)
    assert ts["Time_hr"].is_monotonic_increasing
    assert ts["Rain_mm"].is_monotonic_increasing
    assert ts["Time_hr"].iloc[0] == 0.0 and ts["Rain_mm"].iloc[0] == 0.0
    assert ts["Time_hr"].iloc[-1] == pytest.approx(9.0)


def test_ddf_csv_parser(tmp_path):
    p = tmp_path / "ddf.csv"
    p.write_text("AEP,10m,1h,24h\n1%,22,52,156\n10%,14,34,104\n")
    ddf = load_ddf_csv(p)
    assert ddf[1.0][24] == 156
    assert ddf[10.0][1] == 34


def test_event_names():
    assert aep_event_name(1.0) == "1pAEP"
    assert aep_event_name(0.5) == "0_5pAEP"
    assert duration_event_name(0.5) == "30m"
    assert duration_event_name(24.0) == "24h"


# ---------------------------------------------------------------- end to end

def test_full_build(cfg, tmp_path):
    pre = assign_materials(read_catchments(cfg.pre_catchments, cfg), cfg, "PRE")
    post = assign_materials(read_catchments(cfg.post_catchments, cfg), cfg, "POST")
    storms = build_all_storms(cfg, sample_ddf())
    manifest = build_model(cfg, pre, post, storms)
    root = Path(manifest["root"])

    tcf = Path(manifest["tcf"])
    assert tcf.exists()
    tcf_txt = tcf.read_text()
    assert "Geometry Control File" in tcf_txt and "Event File" in tcf_txt

    tgc = (root / "model" / "TST_001.tgc").read_text()
    assert "If Scenario == PRE" in tgc and "Read GIS Mat" in tgc

    mats = (root / "model" / "materials.csv").read_text()
    assert "Manning's n" in mats and "0.120" in mats  # bush n present

    tef = (root / "runs" / "TST_events.tef").read_text()
    assert "Define Event == 1pAEP" in tef and "End Time == 27" in tef

    # rainfall files: 2 AEP x 2 dur x 3 CC
    rf = list((root / "bc_dbase" / "rainfall").glob("rf_*.csv"))
    assert len(rf) == manifest["n_rainfall_files"] == 12

    # GIS layers exist
    gis = root / "model" / "gis"
    for key, fn in manifest["gis_files"].items():
        assert (gis / fn).exists(), fn

    report = write_report(cfg, pre, post, manifest, root)
    assert report.exists()
    html = report.read_text()
    assert "Pre vs post comparison" in html

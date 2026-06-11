"""Design rainfall: HIRDS DDF handling, nested storms, climate change scaling.

NZ practice (most council specifications) is to derive design storms from the
NIWA HIRDS v4 depth-duration-frequency (DDF) data for the site and build a
nested (alternating-block) hyetograph so that every duration within the storm
contains its full design depth. Climate change is applied as a percentage
uplift on rainfall depths (HIRDS v4 RCP tables, or the MfE ~8 %/degC rule).
"""

from __future__ import annotations

import io
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

from . import defaults
from .config import BuildConfig, CCScenario

# ---------------------------------------------------------------------------
# DDF table handling
# ---------------------------------------------------------------------------


def _parse_duration_label(label: str) -> float | None:
    """'10m' -> 1/6 hr, '1h'/'1hr' -> 1.0, '24h' -> 24.0, '0.5' -> 0.5 hr."""
    s = str(label).strip().lower().replace(" ", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(m|min|mins|minute|minutes)", s)
    if m:
        return float(m.group(1)) / 60.0
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(h|hr|hrs|hour|hours)", s)
    if m:
        return float(m.group(1))
    try:
        return float(s)
    except ValueError:
        return None


def _parse_aep_label(label: str) -> float | None:
    """Accept '1%', 'AEP 1', '1% AEP', ARI labels like '100y'/'ARI100'."""
    s = str(label).strip().lower().replace(" ", "")
    m = re.fullmatch(r"(?:aep)?(\d+(?:\.\d+)?)%?(?:aep)?", s)
    if m and ("%" in s or "aep" in s):
        return float(m.group(1))
    m = re.fullmatch(r"(?:ari)?(\d+(?:\.\d+)?)(?:y|yr|yrs|year|years)?(?:ari)?", s)
    if m:
        v = float(m.group(1))
        # bare numbers <= 50 with no marker are ambiguous; treat <=50 as AEP %
        if s.isdigit() or re.fullmatch(r"\d+(\.\d+)?", s):
            return v if v <= 50 else round(100.0 / v, 4)
        return round(100.0 / v, 4)  # ARI years -> AEP %
    return None


def load_ddf_csv(source: str | Path | io.IOBase | bytes) -> dict[float, dict[float, float]]:
    """Load a DDF table from CSV into ``{aep_pct: {duration_hr: depth_mm}}``.

    Accepts a tidy wide table: first column AEP/ARI labels, remaining columns
    duration labels ('10m', '30m', '1h', '24h', ...). HIRDS v4 site exports
    can be reduced to this shape by keeping the depth block of the table.
    """
    if isinstance(source, bytes):
        source = io.BytesIO(source)
    df = pd.read_csv(source)
    first = df.columns[0]
    ddf: dict[float, dict[float, float]] = {}
    dur_cols = {c: _parse_duration_label(c) for c in df.columns[1:]}
    dur_cols = {c: d for c, d in dur_cols.items() if d is not None}
    if not dur_cols:
        raise ValueError(
            "No duration columns recognised. Expected headers like '10m', '1h', '24h'.")
    for _, row in df.iterrows():
        aep = _parse_aep_label(row[first])
        if aep is None:
            continue
        depths = {}
        for col, dur in dur_cols.items():
            try:
                v = float(row[col])
            except (TypeError, ValueError):
                continue
            if math.isfinite(v):
                depths[dur] = v
        if depths:
            ddf[aep] = depths
    if not ddf:
        raise ValueError("No AEP rows recognised in the DDF table.")
    return ddf


def depth_for_duration(ddf_row: dict[float, float], duration_hr: float) -> float:
    """Depth (mm) for an arbitrary duration by log-log interpolation."""
    durs = np.array(sorted(ddf_row))
    deps = np.array([ddf_row[d] for d in durs])
    if duration_hr <= durs[0]:
        # scale below the shortest tabulated duration assuming constant intensity
        return float(deps[0] * duration_hr / durs[0])
    if duration_hr >= durs[-1]:
        return float(deps[-1])
    return float(np.exp(np.interp(np.log(duration_hr), np.log(durs), np.log(deps))))


# ---------------------------------------------------------------------------
# Nested (alternating block) design storm
# ---------------------------------------------------------------------------


def nested_storm(ddf_row: dict[float, float], duration_hr: float, dt_min: float,
                 cc_factor: float = 1.0) -> pd.DataFrame:
    """Build an alternating-block nested hyetograph.

    Returns a DataFrame with columns ``time_hr`` and ``rain_mm`` (incremental
    depth per timestep) plus ``intensity_mmhr``. The peak block is placed at
    the centre of the storm, consistent with common NZ council practice.
    """
    n = int(round(duration_hr * 60.0 / dt_min))
    if n < 1:
        raise ValueError("Storm duration must contain at least one timestep")
    dt_hr = dt_min / 60.0

    # cumulative design depth for each duration k*dt, scaled for climate change
    cum = np.array([depth_for_duration(ddf_row, (k + 1) * dt_hr) for k in range(n)])
    cum *= cc_factor
    blocks = np.diff(cum, prepend=0.0)
    blocks = np.maximum.accumulate(blocks[::-1])[::-1]  # enforce non-increasing blocks
    order = np.argsort(-blocks)                          # largest first

    # alternating placement: biggest block at the centre, next blocks placed
    # alternately either side, decreasing outwards
    centre = (n - 1) // 2
    slots = sorted(range(n), key=lambda j: (abs(j - centre), j))
    rain = np.empty(n)
    for rank, slot in enumerate(slots):
        rain[slot] = blocks[order[rank]]

    time_hr = (np.arange(n) + 1) * dt_hr
    return pd.DataFrame({
        "time_hr": np.round(time_hr, 6),
        "rain_mm": np.round(rain, 4),
        "intensity_mmhr": np.round(rain / dt_hr, 3),
    })


def storm_to_tuflow_csv(storm: pd.DataFrame, run_time_buffer_hr: float = 0.0) -> pd.DataFrame:
    """Convert a nested storm to the cumulative-time series TUFLOW RF expects.

    TUFLOW rainfall boundaries read time (hours) vs cumulative rainfall (mm).
    A leading zero row and a trailing flat row (post-storm buffer) are added.
    """
    cum = storm["rain_mm"].cumsum()
    t = pd.concat([pd.Series([0.0]), storm["time_hr"]], ignore_index=True)
    r = pd.concat([pd.Series([0.0]), cum], ignore_index=True)
    if run_time_buffer_hr > 0:
        t = pd.concat([t, pd.Series([t.iloc[-1] + run_time_buffer_hr])], ignore_index=True)
        r = pd.concat([r, pd.Series([r.iloc[-1]])], ignore_index=True)
    return pd.DataFrame({"Time_hr": t.round(6), "Rain_mm": r.round(3)})


# ---------------------------------------------------------------------------
# Event naming / generation
# ---------------------------------------------------------------------------


def aep_event_name(aep: float) -> str:
    """1.0 -> '1pAEP', 0.5 -> '0.5pAEP'."""
    s = f"{aep:g}".replace(".", "_")
    return f"{s}pAEP"


def duration_event_name(duration_hr: float) -> str:
    if duration_hr < 1:
        return f"{int(round(duration_hr * 60))}m"
    return f"{duration_hr:g}h"


def build_all_storms(cfg: BuildConfig, ddf: dict[float, dict[float, float]]
                     ) -> dict[tuple[str, str, str], pd.DataFrame]:
    """Generate every AEP x duration x CC-scenario storm.

    Returns ``{(aep_name, dur_name, cc_name): tuflow_csv_dataframe}``.
    """
    out: dict[tuple[str, str, str], pd.DataFrame] = {}
    for aep in cfg.aeps:
        if aep not in ddf:
            raise KeyError(
                f"AEP {aep}% not present in the DDF table (has {sorted(ddf)}). "
                "Add the row to your HIRDS export or remove the AEP from the config.")
        for dur in cfg.storm_durations_hr:
            for cc in cfg.cc_scenarios:
                storm = nested_storm(ddf[aep], dur, cfg.hyetograph_dt_min, cc.factor)
                out[(aep_event_name(aep), duration_event_name(dur), cc.name)] = \
                    storm_to_tuflow_csv(storm, cfg.run_time_buffer_hr)
    return out


def cc_scenario_table(scenarios: list[CCScenario]) -> pd.DataFrame:
    return pd.DataFrame([{
        "Name": s.name,
        "Label": s.label,
        "deltaT_degC": s.deltaT,
        "Uplift_%": round((s.factor - 1.0) * 100.0, 1),
    } for s in scenarios])


def sample_ddf() -> dict[float, dict[float, float]]:
    """Demo DDF table (NOT for production use — export real HIRDS data)."""
    return {a: dict(d) for a, d in defaults.SAMPLE_DDF.items()}

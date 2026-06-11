"""HTML build report: configuration, materials, pre/post comparison, QA flags."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd

from .catchments import compare_scenarios, scenario_summary, unmatched_names
from .config import BuildConfig
from .rainfall import aep_event_name, cc_scenario_table, duration_event_name

_CSS = """
body { font-family: 'Segoe UI', Arial, sans-serif; margin: 2em auto; max-width: 1100px; color: #222; }
h1 { border-bottom: 3px solid #1565c0; padding-bottom: .2em; }
h2 { color: #1565c0; margin-top: 1.6em; }
table { border-collapse: collapse; margin: 1em 0; font-size: .9em; }
th, td { border: 1px solid #bbb; padding: 4px 10px; text-align: right; }
th { background: #e3f0fb; } td:first-child, th:first-child { text-align: left; }
.warn { background: #fff3cd; border: 1px solid #ffc107; padding: .8em 1em; border-radius: 4px; }
.ok { background: #d9f2e0; border: 1px solid #28a745; padding: .8em 1em; border-radius: 4px; }
.note { color: #666; font-size: .85em; }
"""


def _tbl(df: pd.DataFrame) -> str:
    return df.to_html(index=False, float_format=lambda v: f"{v:,.3f}".rstrip("0").rstrip("."),
                      border=0, na_rep="")


def build_report_html(cfg: BuildConfig, pre: gpd.GeoDataFrame, post: gpd.GeoDataFrame,
                      manifest: dict) -> str:
    mats = pd.DataFrame([vars(m) for m in cfg.materials]).rename(columns={
        "id": "ID", "name": "Land use", "n": "Manning's n",
        "il": "IL (mm)", "cl": "CL (mm/hr)", "imperv": "Fraction impervious"})
    cmp_tbl = compare_scenarios(pre, post).rename(columns={
        "material": "ID", "mat_name": "Land use", "n": "Manning's n",
        "imperv": "Imperv", "area_ha_pre": "Pre (ha)", "area_ha_post": "Post (ha)",
        "change_ha": "Change (ha)"})

    events = pd.DataFrame(
        [(aep_event_name(a), duration_event_name(d), c.name)
         for a in cfg.aeps for d in cfg.storm_durations_hr for c in cfg.cc_scenarios],
        columns=["AEP (e1)", "Duration (e2)", "Climate (e3)"])

    warn_html = ""
    un = sorted(set(unmatched_names(pre)) | set(unmatched_names(post)))
    if un:
        warn_html = (f"<div class='warn'><b>{len(un)} catchment name(s) did not match any "
                     f"keyword rule</b> and were assigned the fallback material "
                     f"(ID {cfg.fallback_material_id} - "
                     f"{cfg.material_by_id(cfg.fallback_material_id).name}):<br>"
                     + ", ".join(un) + "</div>")
    else:
        warn_html = "<div class='ok'>All catchment names matched a keyword rule.</div>"

    todo = """
    <div class='warn'><b>Before running, the modeller must:</b>
    <ol>
      <li>Place the project DEM at <code>model/grid/</code> and confirm the
          <code>Read GRID Zpts</code> reference in the .tgc.</li>
      <li>Move the placeholder <b>2d_bc HQ line</b> and the <b>Q_OUTLET PO line</b>
          to the true downstream boundary.</li>
      <li>Review the auto-assigned materials in the <code>0_qa_catchments_*</code> layers.</li>
      <li>Confirm Manning's n, losses and climate-change factors against the relevant
          council modelling specification, and replace the demo DDF with a HIRDS v4
          export for the site if applicable.</li>
      <li>Check cell size, grid extent/orientation (2d_loc) and timestep.</li>
    </ol></div>"""

    return f"""<!doctype html><html><head><meta charset='utf-8'>
<title>{cfg.project_name} - TUFLOW Build Report</title><style>{_CSS}</style></head><body>
<h1>{cfg.project_name} &mdash; TUFLOW Model Build Report</h1>
<p class='note'>Model ID {cfg.model_id} &middot; built {datetime.now():%d %b %Y %H:%M} &middot;
EPSG:{cfg.epsg} &middot; cell size {cfg.cell_size:g} m &middot;
{manifest.get('n_runs', '?')} simulations ({manifest.get('n_rainfall_files', '?')} rainfall files)</p>

{todo}

<h2>1. Land use / roughness assignment</h2>
{warn_html}
<h3>Materials library</h3>{_tbl(mats)}
<h3>Pre-development land use</h3>{_tbl(scenario_summary(pre).round(3))}
<h3>Post-development land use</h3>{_tbl(scenario_summary(post).round(3))}
<h3>Pre vs post comparison</h3>{_tbl(cmp_tbl.round(3))}

<h2>2. Design events</h2>
<h3>Climate change scenarios</h3>{_tbl(cc_scenario_table(cfg.cc_scenarios))}
<h3>Run matrix ({len(events)} events x 2 scenarios = {2 * len(events)} runs)</h3>{_tbl(events)}

<h2>3. Generated files</h2>
<p>TCF: <code>{manifest.get('tcf', '')}</code></p>
<p class='note'>Roughness, loss and climate-change defaults are compiled from common NZ
guidance (Auckland Council stormwater modelling specifications, Christchurch WWDG,
TUFLOW Manual, MfE climate guidance). They are starting values only and must be
reviewed and where necessary calibrated for the project and the consenting authority's
requirements.</p>
</body></html>"""


def write_report(cfg: BuildConfig, pre: gpd.GeoDataFrame, post: gpd.GeoDataFrame,
                 manifest: dict, out_dir: str | Path) -> Path:
    out = Path(out_dir) / "report"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "build_report.html"
    path.write_text(build_report_html(cfg, pre, post, manifest), encoding="utf-8")
    compare_scenarios(pre, post).to_csv(out / "landuse_comparison_pre_post.csv", index=False)
    return path

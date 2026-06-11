"""NZ TUFLOW Flood Model Builder - Streamlit app.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import io
import shutil
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

from tuflow_builder import (BuildConfig, CCScenario, Material, assign_materials,
                            build_all_storms, build_model, load_ddf_csv,
                            make_sample_catchments, nested_storm, read_catchments,
                            sample_ddf, unmatched_names, write_report)
from tuflow_builder.catchments import compare_scenarios, scenario_summary
from tuflow_builder.rainfall import aep_event_name, cc_scenario_table, duration_event_name
from tuflow_builder.reporting import build_report_html

st.set_page_config(page_title="NZ TUFLOW Flood Model Builder", layout="wide",
                   page_icon="🌊")


# ---------------------------------------------------------------------------
# session state
# ---------------------------------------------------------------------------

def cfg() -> BuildConfig:
    if "cfg" not in st.session_state:
        st.session_state.cfg = BuildConfig()
    return st.session_state.cfg


def _save_upload(uploaded, suffix: str) -> Path:
    tmp = Path(tempfile.mkdtemp()) / uploaded.name
    tmp.write_bytes(uploaded.getbuffer())
    return tmp


def _load_layer(uploaded, c: BuildConfig):
    """Read an uploaded GIS file (gpkg/geojson/zipped shp) into a GeoDataFrame."""
    name = uploaded.name.lower()
    if name.endswith(".zip"):
        tmpdir = Path(tempfile.mkdtemp())
        with zipfile.ZipFile(io.BytesIO(uploaded.getbuffer())) as z:
            z.extractall(tmpdir)
        shp = next(tmpdir.rglob("*.shp"), None)
        if shp is None:
            raise ValueError("Zip does not contain a .shp file")
        return read_catchments(shp, c)
    path = _save_upload(uploaded, Path(name).suffix)
    return read_catchments(path, c)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.title("🌊 NZ TUFLOW Flood Model Builder")
st.caption(
    "Builds a complete pre/post-development TUFLOW model package: catchments from GIS, "
    "roughness & losses auto-assigned from catchment names, HIRDS nested design storms "
    "with climate change, TUFLOW control files, reporting layers and a build report. "
    "**Defaults follow common NZ guidance and must be reviewed by the modeller.**")

c = cfg()

with st.sidebar:
    st.header("Project")
    c.project_name = st.text_input("Project name", c.project_name)
    c.model_id = st.text_input("Model ID (file prefix)", c.model_id)
    c.epsg = st.number_input("EPSG (2193 = NZTM)", value=c.epsg, step=1)
    st.header("2D grid")
    c.cell_size = st.number_input("Cell size (m)", value=c.cell_size, min_value=0.25, step=0.25)
    c.grid_buffer = st.number_input("Domain buffer around catchments (m)",
                                    value=c.grid_buffer, min_value=0.0, step=10.0)
    c.gis_format = st.selectbox("GIS format", ["gpkg", "shp"],
                                index=0 if c.gis_format == "gpkg" else 1)
    c.hardware_gpu = st.checkbox("HPC on GPU", value=c.hardware_gpu)
    st.header("Run control")
    c.run_time_buffer_hr = st.number_input("Post-storm run buffer (hr)",
                                           value=c.run_time_buffer_hr, min_value=0.0)
    c.output_interval_s = st.number_input("Map output interval (s)",
                                          value=c.output_interval_s, min_value=30.0)

tab_catch, tab_mat, tab_rain, tab_build = st.tabs(
    ["1 · Catchments", "2 · Roughness & losses", "3 · Rainfall", "4 · Build & report"])

# --------------------------------------------------------------------- catchments
with tab_catch:
    st.subheader("Catchment layers (pre & post development)")
    st.markdown(
        "Upload polygon layers (**GPKG**, **GeoJSON** or **zipped shapefile**). The "
        "catchment/land-use *name* attribute is auto-detected (override below) and is "
        "used to assign roughness and losses.")

    c.name_field = st.text_input("Name attribute (blank = auto-detect)", c.name_field)

    col1, col2 = st.columns(2)
    with col1:
        up_pre = st.file_uploader("Pre-development catchments",
                                  type=["gpkg", "geojson", "json", "zip"], key="up_pre")
    with col2:
        up_post = st.file_uploader("Post-development catchments",
                                   type=["gpkg", "geojson", "json", "zip"], key="up_post")

    if st.button("No data yet? Load sample catchments"):
        d = Path(tempfile.mkdtemp())
        pre_p, post_p = make_sample_catchments(d, c.epsg)
        st.session_state.pre_raw = read_catchments(pre_p, c)
        st.session_state.post_raw = read_catchments(post_p, c)
        st.success("Sample pre/post catchments loaded.")

    for up, key, label in ((up_pre, "pre_raw", "pre"), (up_post, "post_raw", "post")):
        if up is not None:
            try:
                st.session_state[key] = _load_layer(up, c)
                st.success(f"Loaded {label}-development layer: "
                           f"{len(st.session_state[key])} polygons.")
            except Exception as e:  # surface GIS errors to the user
                st.error(f"Could not read {label} layer: {e}")

    if "pre_raw" in st.session_state and "post_raw" in st.session_state:
        pre = assign_materials(st.session_state.pre_raw, c, "PRE")
        post = assign_materials(st.session_state.post_raw, c, "POST")
        st.session_state.pre, st.session_state.post = pre, post

        st.subheader("Auto-assignment preview")
        colA, colB = st.columns(2)
        for col, gdf, label in ((colA, pre, "Pre"), (colB, post, "Post")):
            with col:
                st.markdown(f"**{label}-development** — {gdf['area_ha'].sum():.2f} ha")
                st.dataframe(
                    gdf[["catch_name", "mat_name", "n", "il", "cl", "imperv", "area_ha"]]
                    .rename(columns={"catch_name": "Catchment", "mat_name": "Material",
                                     "area_ha": "Area (ha)"}).round(3),
                    use_container_width=True, hide_index=True)
                un = unmatched_names(gdf)
                if un:
                    st.warning(f"No keyword match (fallback material used): {', '.join(un)}")

        st.subheader("Pre vs post land-use comparison")
        st.dataframe(compare_scenarios(pre, post).round(3),
                     use_container_width=True, hide_index=True)
    else:
        st.info("Load both pre and post layers (or the sample data) to continue.")

# --------------------------------------------------------------------- materials
with tab_mat:
    st.subheader("Materials library (NZ defaults — review before use)")
    st.markdown(
        "Manning's n, rain-on-grid losses and imperviousness per land use. Values are "
        "compiled from common NZ practice (Auckland Council SW modelling specs, "
        "Christchurch WWDG, TUFLOW Manual). Edit as required — changes apply to the "
        "assignment and the generated `materials.csv`.")

    mat_df = pd.DataFrame([vars(m) for m in c.materials])
    edited = st.data_editor(mat_df, num_rows="dynamic", use_container_width=True,
                            key="mat_editor",
                            column_config={
                                "id": st.column_config.NumberColumn("ID", step=1),
                                "name": "Land use",
                                "n": st.column_config.NumberColumn("Manning's n", format="%.3f"),
                                "il": st.column_config.NumberColumn("IL (mm)"),
                                "cl": st.column_config.NumberColumn("CL (mm/hr)"),
                                "imperv": st.column_config.NumberColumn("Fraction impervious"),
                            })
    c.materials = [Material(**{k: r[k] for k in ("id", "name", "n", "il", "cl", "imperv")})
                   for r in edited.dropna(subset=["id", "name", "n"]).to_dict("records")]
    c.materials = [Material(m.id if isinstance(m.id, int) else int(m.id), m.name,
                            float(m.n), float(m.il or 0), float(m.cl or 0),
                            float(m.imperv or 0)) for m in c.materials]

    ids = [m.id for m in c.materials]
    c.fallback_material_id = st.selectbox(
        "Fallback material for unmatched names",
        ids, index=ids.index(c.fallback_material_id) if c.fallback_material_id in ids else 0,
        format_func=lambda i: f"{i} — {c.material_by_id(i).name}")

    with st.expander("Keyword matching rules (first match wins)"):
        rules = pd.DataFrame(
            [{"Keywords (comma separated)": ", ".join(k), "Material ID": v}
             for k, v in c.name_rules])
        edited_rules = st.data_editor(rules, num_rows="dynamic", use_container_width=True,
                                      key="rule_editor")
        new_rules = []
        for r in edited_rules.dropna().to_dict("records"):
            kws = [k.strip().lower() for k in str(r["Keywords (comma separated)"]).split(",")
                   if k.strip()]
            if kws:
                new_rules.append((kws, int(r["Material ID"])))
        if new_rules:
            c.name_rules = new_rules

# --------------------------------------------------------------------- rainfall
with tab_rain:
    st.subheader("Design rainfall (HIRDS v4)")
    st.markdown(
        "Upload the site **DDF table** as CSV — first column AEP/ARI labels "
        "(`1%`, `10%`, …), remaining columns duration depths (`10m, 30m, 1h, 2h, 6h, "
        "12h, 24h, 48h, 72h`). Nested (alternating-block) storms are built per NZ "
        "practice, with climate change applied as a depth uplift.")

    up_ddf = st.file_uploader("HIRDS DDF CSV", type=["csv"], key="up_ddf")
    if up_ddf is not None:
        try:
            st.session_state.ddf = load_ddf_csv(bytes(up_ddf.getbuffer()))
            st.success(f"DDF loaded — AEPs: {sorted(st.session_state.ddf)}")
        except Exception as e:
            st.error(f"Could not parse DDF: {e}")
    if st.button("Use DEMO rainfall (Auckland-like, not for production)"):
        st.session_state.ddf = sample_ddf()
        st.warning("Demo DDF loaded. Replace with a real HIRDS v4 export for any "
                   "real assessment.")

    ddf = st.session_state.get("ddf")
    if ddf:
        ddf_df = pd.DataFrame(ddf).T.sort_index(ascending=False)
        ddf_df.columns = [duration_event_name(d) for d in ddf_df.columns]
        ddf_df.index.name = "AEP %"
        st.dataframe(ddf_df.round(1), use_container_width=True)

        avail = sorted(ddf, reverse=True)
        c.aeps = st.multiselect("AEPs to model (%)", avail,
                                default=[a for a in c.aeps if a in avail] or avail)
        c.storm_durations_hr = st.multiselect(
            "Storm durations (hr)", [1/6, 0.5, 1.0, 2.0, 3.0, 6.0, 12.0, 24.0, 48.0],
            default=c.storm_durations_hr,
            format_func=duration_event_name)
        c.hyetograph_dt_min = st.number_input("Hyetograph timestep (min)",
                                              value=c.hyetograph_dt_min, min_value=1.0)

        st.markdown("**Climate change scenarios** (uplift = ΔT × 8 %/°C per MfE "
                    "guidance unless overridden)")
        cc_df = pd.DataFrame([{"name": s.name, "label": s.label, "deltaT": s.deltaT,
                               "uplift_pct": s.uplift_pct} for s in c.cc_scenarios])
        cc_edit = st.data_editor(cc_df, num_rows="dynamic", key="cc_editor",
                                 use_container_width=True)
        c.cc_scenarios = [CCScenario(str(r["name"]), str(r.get("label") or ""),
                                     float(r.get("deltaT") or 0),
                                     None if pd.isna(r.get("uplift_pct")) else
                                     float(r["uplift_pct"]))
                          for r in cc_edit.dropna(subset=["name"]).to_dict("records")]
        st.dataframe(cc_scenario_table(c.cc_scenarios), hide_index=True)

        if c.aeps and c.storm_durations_hr:
            st.subheader("Hyetograph preview")
            p1, p2, p3 = st.columns(3)
            aep_p = p1.selectbox("AEP", c.aeps, format_func=lambda a: f"{a:g}%")
            dur_p = p2.selectbox("Duration", c.storm_durations_hr,
                                 format_func=duration_event_name)
            cc_p = p3.selectbox("Climate", c.cc_scenarios, format_func=lambda s: s.name)
            storm = nested_storm(ddf[aep_p], dur_p, c.hyetograph_dt_min, cc_p.factor)
            st.bar_chart(storm.set_index("time_hr")["intensity_mmhr"],
                         x_label="Time (hr)", y_label="Intensity (mm/hr)")
            st.caption(f"Total depth {storm['rain_mm'].sum():.1f} mm · "
                       f"peak intensity {storm['intensity_mmhr'].max():.1f} mm/hr")
    else:
        st.info("Upload a DDF CSV or load the demo rainfall to continue.")

# --------------------------------------------------------------------- build
with tab_build:
    st.subheader("Build the TUFLOW model package")
    ready = all(k in st.session_state for k in ("pre", "post", "ddf")) \
        and c.aeps and c.storm_durations_hr and c.cc_scenarios
    if not ready:
        st.info("Complete tabs 1–3 first (catchments + rainfall).")
    else:
        n_runs = 2 * len(c.aeps) * len(c.storm_durations_hr) * len(c.cc_scenarios)
        st.markdown(
            f"**{n_runs} simulations** will be configured "
            f"(2 scenarios × {len(c.aeps)} AEPs × {len(c.storm_durations_hr)} durations "
            f"× {len(c.cc_scenarios)} climate scenarios).")
        c.dem_path = st.text_input("DEM reference written to the TGC",
                                   c.dem_path)

        if st.button("🛠️ Build model package", type="primary"):
            # re-assign with the latest materials/rules edits
            pre = assign_materials(st.session_state.pre_raw, c, "PRE")
            post = assign_materials(st.session_state.post_raw, c, "POST")
            with st.spinner("Generating storms, GIS layers and control files…"):
                out = Path(tempfile.mkdtemp()) / f"{c.model_id}_TUFLOW"
                storms = build_all_storms(c, st.session_state.ddf)
                manifest = build_model(c, pre, post, storms, out)
                write_report(c, pre, post, manifest, out)

                zbuf = io.BytesIO()
                with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
                    for p in sorted(out.rglob("*")):
                        if p.is_file():
                            z.write(p, p.relative_to(out.parent))
                st.session_state.zip_bytes = zbuf.getvalue()
                st.session_state.report_html = build_report_html(c, pre, post, manifest)
                st.session_state.manifest = manifest
            st.success(f"Model built — {manifest['n_rainfall_files']} rainfall files, "
                       f"{manifest['n_runs']} simulations configured.")

        if "zip_bytes" in st.session_state:
            st.download_button(
                "⬇️ Download model package (.zip)",
                data=st.session_state.zip_bytes,
                file_name=f"{c.model_id}_TUFLOW.zip", mime="application/zip",
                type="primary")
            with st.expander("Build report", expanded=True):
                st.components.v1.html(st.session_state.report_html,
                                      height=900, scrolling=True)

st.divider()
st.caption(
    "⚠️ Engineering review required: generated roughness, losses, climate factors and "
    "boundaries are defaults from common NZ guidance. The modeller must verify them "
    "against the relevant council specification, supply the project DEM, and position "
    "the downstream boundary before running TUFLOW.")

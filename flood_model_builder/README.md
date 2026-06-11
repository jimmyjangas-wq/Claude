# NZ TUFLOW Flood Model Builder

Builds a complete **pre/post-development TUFLOW model package** from GIS catchment
layers, following common New Zealand flood-modelling practice:

- Reads **pre- and post-development catchments** from GIS (GeoPackage, GeoJSON or
  zipped shapefile, any CRS — reprojected to NZTM / EPSG:2193).
- **Auto-assigns Manning's n, rain-on-grid losses (IL/CL) and imperviousness** to every
  catchment by keyword-matching the catchment name (e.g. `"Road Network"` → Road,
  `"Native Bush Reserve"` → Bush). The material library and matching rules are fully
  editable.
- Builds **nested (alternating-block) design storms** from a HIRDS v4 DDF table for any
  set of AEPs and durations, with **climate change** uplift (MfE ~8 %/°C rule or
  explicit percentages, e.g. HIRDS RCP factors).
- Writes a **ready-to-review TUFLOW model**: `.tcf` (HPC/GPU, scenario & event
  wildcards), `.tgc`, `.tbc`, `.tef`, `materials.csv`, `bc_dbase.csv`, rainfall CSVs,
  TUFLOW-schema GIS layers (`2d_mat` PRE/POST, `2d_code`, `2d_loc`, `2d_rf`, `2d_bc`,
  `2d_po` reporting points/lines), QA layers and a run-everything batch file.
- Generates an **HTML build report** with the materials table, pre vs post land-use
  comparison (areas, area-weighted n and imperviousness), the run matrix, climate
  factors, and a checklist of items the modeller must complete.

## Quick start (web app)

```bash
cd flood_model_builder
pip install -r requirements.txt
streamlit run app.py
```

1. **Catchments** — upload pre & post polygon layers (or click *Load sample
   catchments*). Review the automatic material assignment and any unmatched names.
2. **Roughness & losses** — edit the NZ-default materials table and keyword rules if
   needed.
3. **Rainfall** — upload your HIRDS v4 DDF CSV (AEP rows × duration columns), pick
   AEPs/durations, set climate scenarios, preview hyetographs.
4. **Build & report** — build, view the report, download the model `.zip`.

## Quick start (CLI)

```bash
python -m tuflow_builder.cli sample-data ./data        # demo catchments
python -m tuflow_builder.cli init-config project.yaml  # template config
# edit project.yaml: pre_catchments / post_catchments paths, AEPs, durations...
python -m tuflow_builder.cli build project.yaml --ddf hirds_site_export.csv
```

## Generated model structure

```
<ModelID>_TUFLOW/
├── runs/
│   ├── <ID>_~s1~_~e1~_~e2~_~e3~_001.tcf   # -s1 PRE|POST  -e1 AEP  -e2 duration  -e3 climate
│   └── <ID>_events.tef                    # event definitions incl. End Time per duration
├── model/
│   ├── <ID>_001.tgc / <ID>_001.tbc / materials.csv
│   ├── grid/                              # ← place the project DEM here
│   └── gis/                               # 2d_mat (PRE/POST), 2d_code, 2d_loc, 2d_rf,
│                                          #   2d_bc (HQ outlet), 2d_po, 0_qa_* layers
├── bc_dbase/  bc_dbase.csv + rainfall/rf_<AEP>_<dur>_<CC>.csv
├── check/  results/
├── report/  build_report.html + land-use summary CSVs
└── <ID>_run_all.bat                       # runs every scenario/event combination
```

## HIRDS DDF CSV format

First column = AEP/ARI label, remaining columns = depths (mm) per duration:

```csv
AEP,10m,30m,1h,2h,6h,12h,24h,48h,72h
10%,14,25,34,45,67,84,104,128,144
1%,22,39,52,69,102,128,156,191,214
```

## ⚠️ Engineering review required

Default roughness, losses, imperviousness and climate factors are compiled from
commonly used NZ references (Auckland Council stormwater modelling specifications,
Christchurch City Council Waterways Wetlands & Drainage Guide, TUFLOW Manual, MfE
climate-change guidance). They are **starting values only**. Before running or relying
on results, a suitably qualified modeller must:

1. Supply the project DEM (`model/grid/`) and confirm the `Read GRID Zpts` reference.
2. Move the placeholder downstream **HQ boundary line** (and `Q_OUTLET` PO line) to the
   true downstream boundary — they are generated along the southern domain edge.
3. Review auto-assigned materials in the `0_qa_catchments_*` layers.
4. Verify all parameters against the relevant council's modelling specification and use
   a real HIRDS v4 export for the site.

## Tests

```bash
cd flood_model_builder && python -m pytest tests -q
```

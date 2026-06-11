"""Read catchment GIS layers and assign materials/roughness from names."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

from .config import BuildConfig

# Candidate attribute names checked (in order) when auto-detecting the field
# that holds the catchment / land-use name.
NAME_FIELD_CANDIDATES = [
    "name", "catchment", "catch_name", "landuse", "land_use", "lu",
    "description", "desc", "label", "type", "class", "category", "id",
]


def read_catchments(path: str | Path, cfg: BuildConfig, layer: str | None = None) -> gpd.GeoDataFrame:
    """Read a catchment polygon layer and normalise it.

    Returns a GeoDataFrame with columns: ``catch_name``, ``geometry`` in the
    configured CRS, exploded to single-part polygons with invalid geometry
    repaired.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Catchment layer not found: {path}")

    gdf = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    if gdf.empty:
        raise ValueError(f"No features in {path}")

    geom_types = set(gdf.geometry.geom_type.unique())
    if not geom_types <= {"Polygon", "MultiPolygon"}:
        raise ValueError(
            f"Catchment layer must contain polygons; found {sorted(geom_types)} in {path}")

    name_field = cfg.name_field or detect_name_field(gdf)
    if name_field not in gdf.columns:
        raise ValueError(
            f"Name field '{name_field}' not found in {path}. "
            f"Available fields: {[c for c in gdf.columns if c != 'geometry']}")

    out = gdf[[name_field, "geometry"]].rename(columns={name_field: "catch_name"})
    out["catch_name"] = out["catch_name"].astype(str).str.strip()

    # Repair and project
    out["geometry"] = out.geometry.buffer(0)
    if out.crs is None:
        out = out.set_crs(epsg=cfg.epsg)
    elif out.crs.to_epsg() != cfg.epsg:
        out = out.to_crs(epsg=cfg.epsg)

    out = out.explode(index_parts=False).reset_index(drop=True)
    out = out[~out.geometry.is_empty & out.geometry.notna()]
    return out


def detect_name_field(gdf: gpd.GeoDataFrame) -> str:
    cols = {c.lower(): c for c in gdf.columns if c != "geometry"}
    for cand in NAME_FIELD_CANDIDATES:
        if cand in cols:
            return cols[cand]
    # fall back to the first text column, then the first column
    for c in gdf.columns:
        if c != "geometry" and gdf[c].dtype == object:
            return c
    non_geom = [c for c in gdf.columns if c != "geometry"]
    if not non_geom:
        raise ValueError("Catchment layer has no attribute fields to use as a name")
    return non_geom[0]


def match_material(name: str, cfg: BuildConfig) -> tuple[int, str]:
    """Return (material_id, matched_keyword) for a catchment name.

    Keyword rules are evaluated in order; first hit wins. Falls back to
    ``cfg.fallback_material_id`` when nothing matches.
    """
    low = name.lower()
    for keywords, mat_id in cfg.name_rules:
        for kw in keywords:
            if kw in low:
                return mat_id, kw
    return cfg.fallback_material_id, ""


def assign_materials(gdf: gpd.GeoDataFrame, cfg: BuildConfig, scenario: str) -> gpd.GeoDataFrame:
    """Assign material id / roughness / losses to every catchment polygon."""
    gdf = gdf.copy()
    mats = {m.id: m for m in cfg.materials}

    assigned = [match_material(n, cfg) for n in gdf["catch_name"]]
    gdf["material"] = [a[0] for a in assigned]
    gdf["match_kw"] = [a[1] for a in assigned]
    gdf["mat_name"] = [mats[i].name for i in gdf["material"]]
    gdf["n"] = [mats[i].n for i in gdf["material"]]
    gdf["il"] = [mats[i].il for i in gdf["material"]]
    gdf["cl"] = [mats[i].cl for i in gdf["material"]]
    gdf["imperv"] = [mats[i].imperv for i in gdf["material"]]
    gdf["scenario"] = scenario
    gdf["area_m2"] = gdf.geometry.area
    gdf["area_ha"] = gdf["area_m2"] / 10_000.0
    return gdf


def scenario_summary(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """Area-weighted summary by material for one scenario."""
    g = (gdf.groupby(["material", "mat_name"], as_index=False)
            .agg(area_ha=("area_ha", "sum"),
                 n=("n", "first"),
                 il=("il", "first"),
                 cl=("cl", "first"),
                 imperv=("imperv", "first"),
                 polygons=("catch_name", "count")))
    total = g["area_ha"].sum()
    g["area_pct"] = 100.0 * g["area_ha"] / total if total else 0.0
    return g.sort_values("material").reset_index(drop=True)


def compare_scenarios(pre: gpd.GeoDataFrame, post: gpd.GeoDataFrame) -> pd.DataFrame:
    """Pre vs post land-use comparison table for reporting."""
    p = scenario_summary(pre)[["material", "mat_name", "n", "imperv", "area_ha"]]
    q = scenario_summary(post)[["material", "mat_name", "n", "imperv", "area_ha"]]
    merged = p.merge(q, on=["material", "mat_name", "n", "imperv"], how="outer",
                     suffixes=("_pre", "_post")).fillna(0.0)
    merged["change_ha"] = merged["area_ha_post"] - merged["area_ha_pre"]
    merged = merged.sort_values("material").reset_index(drop=True)

    def weighted(df, col, area_col):
        a = df[area_col].sum()
        return float((df[col] * df[area_col]).sum() / a) if a else 0.0

    totals = pd.DataFrame([{
        "material": "",
        "mat_name": "TOTAL (area-weighted n / imperv)",
        "n": weighted(merged, "n", "area_ha_post"),
        "imperv": weighted(merged, "imperv", "area_ha_post"),
        "area_ha_pre": merged["area_ha_pre"].sum(),
        "area_ha_post": merged["area_ha_post"].sum(),
        "change_ha": merged["change_ha"].sum(),
    }])
    out = pd.concat([merged, totals], ignore_index=True)
    out["material"] = out["material"].astype(str).str.replace(r"\.0$", "", regex=True)
    return out


def unmatched_names(gdf: gpd.GeoDataFrame) -> list[str]:
    """Catchment names that fell through to the fallback material."""
    return sorted(gdf.loc[gdf["match_kw"] == "", "catch_name"].unique().tolist())

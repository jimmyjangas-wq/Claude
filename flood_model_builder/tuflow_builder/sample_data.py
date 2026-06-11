"""Generate demo pre/post catchment layers so the app works out of the box."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

from . import defaults


def _grid_cells(x0: float, y0: float, w: float, h: float, names: list[list[str]]):
    """Build a grid of rectangles labelled by a 2D list of names."""
    rows = len(names)
    cols = len(names[0])
    cw, ch = w / cols, h / rows
    geoms, labels = [], []
    for r in range(rows):
        for c in range(cols):
            if not names[r][c]:
                continue
            geoms.append(box(x0 + c * cw, y0 + (rows - 1 - r) * ch,
                             x0 + (c + 1) * cw, y0 + (rows - r) * ch))
            labels.append(names[r][c])
    return geoms, labels


def make_sample_catchments(out_dir: str | Path, epsg: int = defaults.DEFAULT_EPSG
                           ) -> tuple[Path, Path]:
    """Write sample pre/post catchment GPKGs (~16 ha site near Auckland in NZTM)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    x0, y0 = 1_757_000.0, 5_915_000.0  # NZTM, Auckland-ish

    pre_names = [
        ["Native Bush Reserve", "Pasture North",   "Pasture North"],
        ["Stream Corridor",     "Pasture Central", "Scrub Gully"],
        ["Pasture South",       "Pasture South",   "Wetland Lower"],
    ]
    post_names = [
        ["Native Bush Reserve",  "Residential Stage 1", "Residential Stage 2"],
        ["Stream Corridor",      "Road Network",        "Commercial Block A"],
        ["Residential Stage 3",  "Open Space Park",     "Detention Basin"],
    ]

    pre_g, pre_l = _grid_cells(x0, y0, 600, 400, pre_names)
    post_g, post_l = _grid_cells(x0, y0, 600, 400, post_names)

    pre = gpd.GeoDataFrame({"Name": pre_l}, geometry=pre_g, crs=f"EPSG:{epsg}")
    post = gpd.GeoDataFrame({"Name": post_l}, geometry=post_g, crs=f"EPSG:{epsg}")

    pre_path = out / "sample_catchments_pre.gpkg"
    post_path = out / "sample_catchments_post.gpkg"
    pre.to_file(pre_path, layer="catchments_pre", driver="GPKG")
    post.to_file(post_path, layer="catchments_post", driver="GPKG")
    return pre_path, post_path

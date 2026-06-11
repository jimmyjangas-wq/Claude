"""Command line interface.

Usage:
    python -m tuflow_builder.cli init-config my_project.yaml
    python -m tuflow_builder.cli sample-data ./data
    python -m tuflow_builder.cli build my_project.yaml [--ddf hirds.csv]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import (BuildConfig, assign_materials, build_all_storms, build_model,
               load_ddf_csv, make_sample_catchments, read_catchments,
               sample_ddf, unmatched_names, write_report)


def cmd_init_config(args) -> int:
    cfg = BuildConfig()
    cfg.to_yaml(args.path)
    print(f"Wrote template config: {args.path}")
    print("Edit pre_catchments / post_catchments paths, AEPs and materials, then run:")
    print(f"  python -m tuflow_builder.cli build {args.path} --ddf <hirds_export.csv>")
    return 0


def cmd_sample_data(args) -> int:
    pre, post = make_sample_catchments(args.path)
    print(f"Wrote sample catchments:\n  {pre}\n  {post}")
    return 0


def cmd_build(args) -> int:
    cfg = BuildConfig.from_yaml(args.config)
    if not cfg.pre_catchments or not cfg.post_catchments:
        print("Config must set pre_catchments and post_catchments paths", file=sys.stderr)
        return 2

    ddf = load_ddf_csv(args.ddf) if args.ddf else sample_ddf()
    if not args.ddf:
        print("WARNING: no --ddf supplied; using built-in DEMO rainfall depths. "
              "Export HIRDS v4 data for the site for any real assessment.")

    pre = assign_materials(read_catchments(cfg.pre_catchments, cfg), cfg, "PRE")
    post = assign_materials(read_catchments(cfg.post_catchments, cfg), cfg, "POST")

    for label, gdf in (("PRE", pre), ("POST", post)):
        un = unmatched_names(gdf)
        if un:
            print(f"WARNING [{label}]: {len(un)} name(s) fell back to material "
                  f"{cfg.fallback_material_id}: {', '.join(un)}")

    storms = build_all_storms(cfg, ddf)
    manifest = build_model(cfg, pre, post, storms)
    report = write_report(cfg, pre, post, manifest, manifest["root"])

    print(f"\nModel written to: {manifest['root']}")
    print(f"  TCF:            {manifest['tcf']}")
    print(f"  Rainfall files: {manifest['n_rainfall_files']}")
    print(f"  Simulations:    {manifest['n_runs']}")
    print(f"  Build report:   {report}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tuflow_builder",
                                description="NZ TUFLOW flood model builder")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init-config", help="write a template YAML config")
    s.add_argument("path", type=Path)
    s.set_defaults(func=cmd_init_config)

    s = sub.add_parser("sample-data", help="write demo pre/post catchment layers")
    s.add_argument("path", type=Path)
    s.set_defaults(func=cmd_sample_data)

    s = sub.add_parser("build", help="build the TUFLOW model from a config")
    s.add_argument("config", type=Path)
    s.add_argument("--ddf", type=Path, default=None,
                   help="HIRDS-style DDF CSV (AEP rows x duration columns)")
    s.set_defaults(func=cmd_build)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

"""Benchmark parameter sweep CLI command (task-029)."""

from __future__ import annotations

import argparse
from pathlib import Path


def cmd_tune(args: argparse.Namespace) -> int:
    """Run a face detection parameter sweep and print a ranked results table."""
    from benchmarking.tuner import load_tune_config, print_sweep_results, run_face_sweep

    param_grid: dict[str, list] = {}
    split = args.split or "iteration"
    metric = args.metric or "face_f1"

    if args.config:
        cfg = load_tune_config(Path(args.config))
        param_grid = cfg["param_grid"]
        split = args.split or cfg["split"]
        metric = args.metric or cfg["metric"]

    if args.params:
        # Parse "KEY=v1,v2 KEY2=v1,v2"
        for token in args.params:
            if "=" not in token:
                print(f"Error: --params token must be KEY=v1,v2 format, got: {token!r}")
                return 1
            key, _, raw = token.partition("=")
            values = [_parse_value(v) for v in raw.split(",")]
            param_grid[key.strip()] = values

    if not param_grid:
        print("Error: provide --config or --params.")
        return 1

    verbose = not getattr(args, "quiet", False)
    try:
        results = run_face_sweep(
            param_grid=param_grid,
            split=split,
            metric=metric,
            verbose=verbose,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}")
        return 1

    print_sweep_results(results, metric=metric)
    return 0


def _parse_value(s: str):
    """Parse a string value to int, float, or str."""
    s = s.strip()
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s

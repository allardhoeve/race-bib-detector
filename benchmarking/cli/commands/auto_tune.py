"""Auto-tune CLI command (task-092)."""

from __future__ import annotations

import argparse


def cmd_auto_tune(args: argparse.Namespace) -> int:
    """Run auto-tune analysis on a benchmark run and print report."""
    from benchmarking.runner import get_latest_run, get_run
    from benchmarking.tuners.auto import print_auto_tune_report, run_auto_tune

    run_id = getattr(args, "run_id", None)
    if run_id:
        run = get_run(run_id)
        if run is None:
            print(f"Error: run '{run_id}' not found.")
            return 1
    else:
        run = get_latest_run()
        if run is None:
            print("Error: no benchmark runs found. Run 'bnr benchmark run' first.")
            return 1

    result = run_auto_tune(run)
    print_auto_tune_report(result)
    return 0

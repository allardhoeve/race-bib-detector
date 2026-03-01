"""Benchmark command CLI parsing and control flow."""

from __future__ import annotations

import argparse
import importlib


def _lazy_cmd(module_path: str, func_name: str):
    """Return a function that lazily imports and calls a command function."""
    def _wrapper(args: argparse.Namespace) -> int:
        mod = importlib.import_module(module_path)
        return getattr(mod, func_name)(args)
    return _wrapper


def add_benchmark_subparser(subparsers: argparse._SubParsersAction) -> None:
    benchmark_parser = subparsers.add_parser(
        "benchmark",
        help="Benchmark detection accuracy",
    )
    benchmark_subparsers = benchmark_parser.add_subparsers(
        dest="benchmark_command",
        help="Benchmark command",
    )

    # ---- prepare ----
    bench_prepare = benchmark_subparsers.add_parser(
        "prepare",
        help="Import photos from a directory into the benchmark set",
    )
    bench_prepare.add_argument(
        "source",
        help="Source directory containing photos to import",
    )
    bench_prepare.add_argument(
        "--refresh",
        action="store_true",
        help="Re-run ghost labeling on existing photos",
    )
    bench_prepare.add_argument(
        "--reset-labels",
        action="store_true",
        help="Clear all labels (keep photos)",
    )
    bench_prepare.set_defaults(_cmd=_lazy_cmd("benchmarking.cli.commands.photos", "cmd_prepare"))

    # ---- run ----
    bench_run = benchmark_subparsers.add_parser(
        "run",
        help="Run benchmark",
    )
    bench_run.add_argument(
        "-s", "--split",
        choices=["iteration", "full"],
        default="iteration",
        help="Which split to run (default: iteration)",
    )
    bench_run.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress per-photo output",
    )
    bench_run.add_argument(
        "-S", "--set",
        dest="frozen_set",
        metavar="NAME",
        help="Only run against photos in this frozen set",
    )
    bench_run.add_argument(
        "--note", "--comment",
        dest="note",
        help="Optional note to attach to the benchmark run",
    )
    bench_run.set_defaults(_cmd=_lazy_cmd("benchmarking.cli.commands.benchmark", "cmd_benchmark"))

    # ---- ui ----
    bench_ui = benchmark_subparsers.add_parser(
        "ui",
        help="Launch web UI for labeling and inspection (port 30002)",
    )
    bench_ui.set_defaults(_cmd=_lazy_cmd("benchmarking.cli.commands.photos", "cmd_ui"))

    # ---- list ----
    bench_list = benchmark_subparsers.add_parser(
        "list",
        help="List saved benchmark runs",
    )
    bench_list.set_defaults(_cmd=_lazy_cmd("benchmarking.cli.commands.benchmark", "cmd_benchmark_list"))

    # ---- clean ----
    bench_clean = benchmark_subparsers.add_parser(
        "clean",
        help="Remove old benchmark runs",
    )
    bench_clean.add_argument(
        "--keep-latest",
        type=int,
        default=5,
        metavar="N",
        help="Keep the N most recent runs (default: 5)",
    )
    bench_clean.add_argument(
        "--keep-baseline",
        action="store_true",
        help="Never delete the baseline run",
    )
    bench_clean.add_argument(
        "--older-than",
        type=int,
        metavar="DAYS",
        help="Only delete runs older than N days",
    )
    bench_clean.add_argument(
        "-f", "--force",
        action="store_true",
        help="Skip confirmation prompt",
    )
    bench_clean.set_defaults(_cmd=_lazy_cmd("benchmarking.cli.commands.benchmark", "cmd_benchmark_clean"))

    # ---- delete ----
    bench_delete = benchmark_subparsers.add_parser(
        "delete",
        help="Delete specific benchmark runs by ID",
    )
    bench_delete.add_argument(
        "run_ids",
        nargs="+",
        metavar="RUN_ID",
        help="One or more run IDs (or prefixes) to delete",
    )
    bench_delete.add_argument(
        "-f", "--force",
        action="store_true",
        help="Skip confirmation prompt",
    )
    bench_delete.set_defaults(_cmd=_lazy_cmd("benchmarking.cli.commands.benchmark", "cmd_benchmark_delete"))

    # ---- baseline ----
    bench_baseline = benchmark_subparsers.add_parser(
        "baseline",
        help="Update baseline if metrics improved",
    )
    bench_baseline.add_argument(
        "-f", "--force",
        action="store_true",
        help="Update without prompting",
    )
    bench_baseline.set_defaults(_cmd=_lazy_cmd("benchmarking.cli.commands.benchmark", "cmd_set_baseline"))

    # ---- scan ----
    bench_scan = benchmark_subparsers.add_parser(
        "scan",
        help="Scan photos directory and update index",
    )
    bench_scan.set_defaults(_cmd=_lazy_cmd("benchmarking.cli.commands.photos", "cmd_scan"))

    # ---- stats ----
    bench_stats = benchmark_subparsers.add_parser(
        "stats",
        help="Show labeling statistics",
    )
    bench_stats.set_defaults(_cmd=_lazy_cmd("benchmarking.cli.commands.photos", "cmd_stats"))

    # ---- freeze ----
    bench_freeze = benchmark_subparsers.add_parser(
        "freeze",
        help="Freeze current photo set as a named snapshot",
    )
    bench_freeze.add_argument("--name", required=True, help="Name for the snapshot")
    bench_freeze.add_argument("--description", default="", help="Optional description")
    bench_freeze.add_argument(
        "--all",
        action="store_true",
        help="Freeze every photo in the index regardless of labeling status",
    )
    bench_freeze.add_argument(
        "--include-incomplete",
        action="store_true",
        help="Include photos that are not fully labeled in all dimensions",
    )
    bench_freeze.set_defaults(_cmd=_lazy_cmd("benchmarking.cli.commands.benchmark", "cmd_freeze"))

    # ---- frozen-list ----
    bench_frozen_list = benchmark_subparsers.add_parser(
        "frozen-list",
        help="List all frozen snapshots",
    )
    bench_frozen_list.set_defaults(_cmd=_lazy_cmd("benchmarking.cli.commands.benchmark", "cmd_frozen_list"))

    # ---- tune ----
    bench_tune = benchmark_subparsers.add_parser(
        "tune",
        help="Sweep face detection parameters and print ranked results",
    )
    bench_tune.add_argument(
        "--config",
        metavar="YAML",
        help="Path to tune config YAML (e.g. benchmarking/tune_configs/face_default.yaml)",
    )
    bench_tune.add_argument(
        "--params",
        nargs="+",
        metavar="KEY=v1,v2",
        help="Inline param grid (e.g. FACE_DNN_CONFIDENCE_MIN=0.2,0.3,0.4)",
    )
    bench_tune.add_argument(
        "-s", "--split",
        choices=["iteration", "full"],
        default=None,
        help="Photo split to evaluate on (overrides config)",
    )
    bench_tune.add_argument(
        "--metric",
        choices=["face_f1", "face_recall", "face_precision"],
        default=None,
        help="Metric to rank by (overrides config)",
    )
    bench_tune.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress per-combo progress output",
    )
    bench_tune.set_defaults(_cmd=_lazy_cmd("benchmarking.cli.commands.tune", "cmd_tune"))

    # ---- inspect ----
    bench_inspect = benchmark_subparsers.add_parser(
        "inspect",
        help="Show URL to inspect a benchmark run",
    )
    bench_inspect.add_argument(
        "run_id",
        nargs="?",
        default=None,
        help="Run ID to inspect (defaults to latest)",
    )
    bench_inspect.set_defaults(_cmd=_lazy_cmd("benchmarking.cli.commands.benchmark", "cmd_benchmark_inspect"))

    benchmark_parser.set_defaults(_benchmark_parser=benchmark_parser)

"""CLI for benchmark management."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path (needed when invoked directly)
sys.path.insert(0, str(Path(__file__).parents[2]))

from logging_utils import configure_logging, add_logging_args

from benchmarking.cli.commands.photos import (
    cmd_scan,
    cmd_stats,
    cmd_unlabeled,
    cmd_show,
    cmd_label,
    cmd_prepare,
    cmd_ui,
)
from benchmarking.cli.commands.benchmark import (
    cmd_benchmark,
    cmd_benchmark_inspect,
    cmd_benchmark_list,
    cmd_benchmark_clean,
    cmd_set_baseline,
    cmd_freeze,
    cmd_frozen_list,
    cmd_update_baseline,
)
from benchmarking.cli.commands.tune import cmd_tune


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark ground truth management"
    )
    add_logging_args(parser)
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # prepare command
    prepare_parser = subparsers.add_parser(
        "prepare", help="Import photos into benchmark set"
    )
    prepare_parser.add_argument(
        "source", help="Source directory containing photos to import"
    )
    prepare_parser.add_argument(
        "--refresh", action="store_true",
        help="Re-run ghost labeling on existing photos"
    )
    prepare_parser.add_argument(
        "--reset-labels", action="store_true",
        help="Clear all labels (keep photos)"
    )

    # scan command
    subparsers.add_parser("scan", help="Scan photos directory")

    # ui command
    subparsers.add_parser("ui", help="Launch web UI (labels + benchmark inspection)")

    # benchmark command
    benchmark_parser = subparsers.add_parser("benchmark", help="Run benchmark")
    benchmark_parser.add_argument(
        "-s", "--split", choices=["iteration", "full"],
        default="iteration",
        help="Which split to run: 'full' = all photos, 'iteration' = subset for quick feedback (default: iteration)"
    )
    benchmark_parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="Suppress per-photo output"
    )
    benchmark_parser.add_argument(
        "--note", "--comment",
        dest="note",
        help="Optional note to attach to the benchmark run",
    )

    # set-baseline command
    set_baseline_parser = subparsers.add_parser(
        "set-baseline", help="Set a specific run as the baseline"
    )
    set_baseline_parser.add_argument(
        "run_id", nargs="?", default=None,
        help="Run ID to set as baseline (defaults to latest)"
    )
    set_baseline_parser.add_argument(
        "-f", "--force", action="store_true",
        help="Skip confirmation prompts"
    )

    # benchmark-list command
    subparsers.add_parser(
        "benchmark-list", help="List saved benchmark runs"
    )

    # benchmark-inspect command
    benchmark_inspect_parser = subparsers.add_parser(
        "benchmark-inspect", help="Show URL to inspect a benchmark run (use 'ui' command to start server)"
    )
    benchmark_inspect_parser.add_argument(
        "run_id", nargs="?", default=None,
        help="Run ID to inspect (defaults to latest)"
    )

    # benchmark-clean command
    benchmark_clean_parser = subparsers.add_parser(
        "benchmark-clean", help="Remove old benchmark runs (like docker system prune)"
    )
    benchmark_clean_parser.add_argument(
        "--keep-latest", type=int, default=5,
        metavar="N",
        help="Keep the N most recent runs (default: 5)"
    )
    benchmark_clean_parser.add_argument(
        "--keep-baseline", action="store_true",
        help="Never delete the baseline run"
    )
    benchmark_clean_parser.add_argument(
        "--older-than", type=int,
        metavar="DAYS",
        help="Only delete runs older than N days"
    )
    benchmark_clean_parser.add_argument(
        "-f", "--force", action="store_true",
        help="Skip confirmation prompt"
    )

    # freeze command
    freeze_parser = subparsers.add_parser(
        "freeze", help="Freeze current photo set as a named snapshot"
    )
    freeze_parser.add_argument("--name", required=True, help="Name for the snapshot")
    freeze_parser.add_argument("--description", default="", help="Optional description")
    freeze_parser.add_argument(
        "--all",
        action="store_true",
        help="Freeze every photo in the index regardless of labeling status",
    )
    freeze_parser.add_argument(
        "--include-incomplete",
        action="store_true",
        help="Include photos that are not fully labeled in all dimensions",
    )

    # frozen-list command
    subparsers.add_parser("frozen-list", help="List all frozen snapshots")

    # tune command
    tune_parser = subparsers.add_parser(
        "tune", help="Sweep face detection parameters and print ranked results"
    )
    tune_parser.add_argument(
        "--config",
        metavar="YAML",
        help="Path to tune config YAML (e.g. benchmarking/tune_configs/face_default.yaml)",
    )
    tune_parser.add_argument(
        "--params",
        nargs="+",
        metavar="KEY=v1,v2",
        help="Inline param grid (e.g. FACE_DNN_CONFIDENCE_MIN=0.2,0.3,0.4)",
    )
    tune_parser.add_argument(
        "-s", "--split", choices=["iteration", "full"],
        default=None,
        help="Photo split to evaluate on (overrides config)",
    )
    tune_parser.add_argument(
        "--metric",
        choices=["face_f1", "face_recall", "face_precision"],
        default=None,
        help="Metric to rank by (overrides config)",
    )
    tune_parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="Suppress per-combo progress output",
    )

    # stats command
    subparsers.add_parser("stats", help="Show statistics")

    # unlabeled command
    unlabeled_parser = subparsers.add_parser(
        "unlabeled", help="List unlabeled photos"
    )
    unlabeled_parser.add_argument(
        "-n", "--limit", type=int, help="Max photos to show"
    )

    # show command
    show_parser = subparsers.add_parser("show", help="Show photo details")
    show_parser.add_argument("hash", help="Content hash (or prefix)")

    # label command
    label_parser = subparsers.add_parser("label", help="Add/update a label")
    label_parser.add_argument("hash", help="Content hash (or prefix)")
    label_parser.add_argument(
        "-b", "--bibs", help="Comma-separated bib numbers"
    )
    label_parser.add_argument(
        "-t", "--tags", help="Comma-separated tags"
    )
    label_parser.add_argument(
        "-s", "--split", choices=["iteration", "full"],
        help="Split assignment"
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level, args.verbose, args.quiet)

    if args.command is None:
        parser.print_help()
        return 1

    commands = {
        "prepare": cmd_prepare,
        "scan": cmd_scan,
        "ui": cmd_ui,
        "benchmark": cmd_benchmark,
        "set-baseline": cmd_set_baseline,
        "benchmark-list": cmd_benchmark_list,
        "benchmark-inspect": cmd_benchmark_inspect,
        "benchmark-clean": cmd_benchmark_clean,
        "freeze": cmd_freeze,
        "frozen-list": cmd_frozen_list,
        "stats": cmd_stats,
        "unlabeled": cmd_unlabeled,
        "show": cmd_show,
        "label": cmd_label,
        "tune": cmd_tune,
    }

    return commands[args.command](args)

#!/usr/bin/env python3
"""
Unified CLI for the Bib Number Recognizer.

Usage:
    bnr serve                    # Launch photo viewer website (port 30001)
    bnr scan <path>              # Scan local directory or file for bib numbers
    bnr album list               # List albums and photo counts
    bnr album forget <album_id>  # Forget an album (DB only)
    bnr faces cluster --album X  # Cluster face embeddings for an album
    bnr benchmark prepare <path> # Import photos into benchmark set
    bnr benchmark run            # Run benchmark on iteration split
    bnr benchmark run --full     # Run benchmark on all photos
    bnr benchmark ui             # Launch benchmark web UI (labels + inspection)
    bnr benchmark list           # List saved benchmark runs
    bnr benchmark clean          # Clean old benchmark runs
    bnr benchmark baseline       # Update baseline if metrics improved
"""

import argparse
import logging
import sys

from logging_utils import configure_logging, add_logging_args
from cli.scan import add_scan_subparser
from cli.album import add_album_subparser
from cli.cache import add_cache_subparser
from cli.faces import add_faces_subparser

logger = logging.getLogger(__name__)


def cmd_serve(args: argparse.Namespace) -> int:
    """Launch the photo viewer web server."""
    from web import main
    main()
    return 0


def cmd_benchmark_run(args: argparse.Namespace) -> int:
    """Run benchmark."""
    from benchmarking.cli import cmd_benchmark

    bench_args = argparse.Namespace(
        split="full" if args.full else "iteration",
        quiet=args.quiet,
        note=args.note,
        update_baseline=False,
    )
    return cmd_benchmark(bench_args)


def cmd_benchmark_ui(args: argparse.Namespace) -> int:
    """Launch benchmark web UI."""
    from benchmarking.web_app import main
    return main([])


def cmd_benchmark_list(args: argparse.Namespace) -> int:
    """List benchmark runs."""
    from benchmarking.cli import cmd_benchmark_list
    return cmd_benchmark_list(args)


def cmd_benchmark_clean(args: argparse.Namespace) -> int:
    """Clean old benchmark runs."""
    from benchmarking.cli import cmd_benchmark_clean
    return cmd_benchmark_clean(args)


def cmd_benchmark_baseline(args: argparse.Namespace) -> int:
    """Update baseline if metrics improved."""
    from benchmarking.cli import cmd_update_baseline
    return cmd_update_baseline(args)


def cmd_benchmark_prepare(args: argparse.Namespace) -> int:
    """Prepare benchmark photos from a source directory."""
    from benchmarking.cli import cmd_prepare
    return cmd_prepare(args)


def cmd_benchmark_scan(args: argparse.Namespace) -> int:
    """Scan photos directory for benchmark."""
    from benchmarking.cli import cmd_scan
    return cmd_scan(args)


def cmd_benchmark_stats(args: argparse.Namespace) -> int:
    """Show benchmark statistics."""
    from benchmarking.cli import cmd_stats
    return cmd_stats(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bnr",
        description="Bib Number Recognizer - detect race bib numbers in photos",
    )
    add_logging_args(parser)
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    serve_parser = subparsers.add_parser(
        "serve",
        help="Launch photo viewer website (port 30001)",
    )
    serve_parser.set_defaults(_cmd=cmd_serve)

    add_scan_subparser(subparsers)

    benchmark_parser = subparsers.add_parser(
        "benchmark",
        help="Benchmark detection accuracy",
    )
    benchmark_subparsers = benchmark_parser.add_subparsers(
        dest="benchmark_command",
        help="Benchmark command",
    )

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
    bench_prepare.set_defaults(_cmd=cmd_benchmark_prepare)

    bench_run = benchmark_subparsers.add_parser(
        "run",
        help="Run benchmark",
    )
    bench_run.add_argument(
        "--full",
        action="store_true",
        help="Run on all photos (default: iteration split for fast feedback)",
    )
    bench_run.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress per-photo output",
    )
    bench_run.add_argument(
        "--note", "--comment",
        dest="note",
        help="Optional note to attach to the benchmark run",
    )
    bench_run.set_defaults(_cmd=cmd_benchmark_run)

    bench_ui = benchmark_subparsers.add_parser(
        "ui",
        help="Launch web UI for labeling and inspection (port 30002)",
    )
    bench_ui.set_defaults(_cmd=cmd_benchmark_ui)

    bench_list = benchmark_subparsers.add_parser(
        "list",
        help="List saved benchmark runs",
    )
    bench_list.set_defaults(_cmd=cmd_benchmark_list)

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
    bench_clean.set_defaults(_cmd=cmd_benchmark_clean)

    bench_baseline = benchmark_subparsers.add_parser(
        "baseline",
        help="Update baseline if metrics improved",
    )
    bench_baseline.add_argument(
        "-f", "--force",
        action="store_true",
        help="Update without prompting",
    )
    bench_baseline.set_defaults(_cmd=cmd_benchmark_baseline)

    bench_scan = benchmark_subparsers.add_parser(
        "scan",
        help="Scan photos directory and update index",
    )
    bench_scan.set_defaults(_cmd=cmd_benchmark_scan)

    bench_stats = benchmark_subparsers.add_parser(
        "stats",
        help="Show labeling statistics",
    )
    bench_stats.set_defaults(_cmd=cmd_benchmark_stats)

    add_album_subparser(subparsers)
    add_cache_subparser(subparsers)
    add_faces_subparser(subparsers)

    parser.set_defaults(_benchmark_parser=benchmark_parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level, args.verbose, args.quiet)

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "benchmark" and args.benchmark_command is None:
        args._benchmark_parser.print_help()
        return 1
    if args.command == "album" and args.album_command is None:
        args._album_parser.print_help()
        return 1
    if args.command == "cache" and args.cache_command is None:
        args._cache_parser.print_help()
        return 1
    if args.command == "faces" and args.faces_command is None:
        args._faces_parser.print_help()
        return 1

    cmd = getattr(args, "_cmd", None)
    if cmd is None:
        parser.print_help()
        return 1
    return cmd(args)


if __name__ == "__main__":
    sys.exit(main())

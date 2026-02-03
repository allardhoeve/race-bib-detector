#!/usr/bin/env python3
"""
Unified CLI for the Bib Number Recognizer.

Usage:
    bnr serve                    # Launch photo viewer website (port 30001)
    bnr scan <url|path>          # Scan album or directory for bib numbers
    bnr benchmark run            # Run benchmark on iteration split
    bnr benchmark run --full     # Run benchmark on all photos
    bnr benchmark ui             # Launch benchmark web UI (labels + inspection)
    bnr benchmark list           # List saved benchmark runs
    bnr benchmark clean          # Clean old benchmark runs
    bnr benchmark baseline       # Update baseline if metrics improved
"""

import argparse
import sys


def cmd_serve(args: argparse.Namespace) -> int:
    """Launch the photo viewer web server."""
    from web import main
    main()
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    """Scan an album or directory for bib numbers."""
    from scan_album import run_scan

    if not args.source and not args.rescan:
        print("Error: Please provide a source (URL or path) or --rescan ID")
        return 1

    if args.rescan:
        return run_scan(args.rescan, rescan=True)
    else:
        return run_scan(args.source, rescan=args.force)


def cmd_benchmark_run(args: argparse.Namespace) -> int:
    """Run benchmark."""
    from benchmarking.cli import cmd_benchmark

    bench_args = argparse.Namespace(
        split="full" if args.full else "iteration",
        quiet=args.quiet,
        update_baseline=False,
    )
    return cmd_benchmark(bench_args)


def cmd_benchmark_ui(args: argparse.Namespace) -> int:
    """Launch benchmark web UI."""
    from benchmarking.web_app import main
    return main()


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


def cmd_benchmark_scan(args: argparse.Namespace) -> int:
    """Scan photos directory for benchmark."""
    from benchmarking.cli import cmd_scan
    return cmd_scan(args)


def cmd_benchmark_stats(args: argparse.Namespace) -> int:
    """Show benchmark statistics."""
    from benchmarking.cli import cmd_stats
    return cmd_stats(args)


def main():
    parser = argparse.ArgumentParser(
        prog="bnr",
        description="Bib Number Recognizer - detect race bib numbers in photos",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # -------------------------------------------------------------------------
    # serve - Launch photo viewer
    # -------------------------------------------------------------------------
    serve_parser = subparsers.add_parser(
        "serve",
        help="Launch photo viewer website (port 30001)",
    )

    # -------------------------------------------------------------------------
    # scan - Scan album or directory
    # -------------------------------------------------------------------------
    scan_parser = subparsers.add_parser(
        "scan",
        help="Scan album URL or local directory for bib numbers",
    )
    scan_parser.add_argument(
        "source",
        nargs="?",
        help="Google Photos album URL or local directory path",
    )
    scan_parser.add_argument(
        "--rescan",
        metavar="ID",
        help="Rescan a specific photo by hash or index",
    )
    scan_parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force rescan even if already processed",
    )

    # -------------------------------------------------------------------------
    # benchmark - Benchmark subcommands
    # -------------------------------------------------------------------------
    benchmark_parser = subparsers.add_parser(
        "benchmark",
        help="Benchmark detection accuracy",
    )
    benchmark_subparsers = benchmark_parser.add_subparsers(
        dest="benchmark_command",
        help="Benchmark command",
    )

    # benchmark run
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

    # benchmark ui
    benchmark_subparsers.add_parser(
        "ui",
        help="Launch web UI for labeling and inspection (port 30002)",
    )

    # benchmark list
    benchmark_subparsers.add_parser(
        "list",
        help="List saved benchmark runs",
    )

    # benchmark clean
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

    # benchmark baseline
    bench_baseline = benchmark_subparsers.add_parser(
        "baseline",
        help="Update baseline if metrics improved",
    )
    bench_baseline.add_argument(
        "-f", "--force",
        action="store_true",
        help="Update without prompting",
    )

    # benchmark scan
    benchmark_subparsers.add_parser(
        "scan",
        help="Scan photos directory and update index",
    )

    # benchmark stats
    benchmark_subparsers.add_parser(
        "stats",
        help="Show labeling statistics",
    )

    # -------------------------------------------------------------------------
    # Parse and dispatch
    # -------------------------------------------------------------------------
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "serve":
        return cmd_serve(args)
    elif args.command == "scan":
        return cmd_scan(args)
    elif args.command == "benchmark":
        if args.benchmark_command is None:
            benchmark_parser.print_help()
            return 1

        dispatch = {
            "run": cmd_benchmark_run,
            "ui": cmd_benchmark_ui,
            "list": cmd_benchmark_list,
            "clean": cmd_benchmark_clean,
            "baseline": cmd_benchmark_baseline,
            "scan": cmd_benchmark_scan,
            "stats": cmd_benchmark_stats,
        }
        return dispatch[args.benchmark_command](args)

    return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Unified CLI for the Bib Number Recognizer.

Usage:
    bnr serve                         # Launch photo viewer website (port 30001)
    bnr scan <path>                   # Scan local directory or file for bib numbers
    bnr album list                    # List albums and photo counts
    bnr album forget <album_id>       # Forget an album (DB only)
    bnr faces cluster --album X       # Cluster face embeddings for an album
    bnr benchmark prepare <path>      # Import photos into benchmark set
    bnr benchmark run                 # Run benchmark on iteration split
    bnr benchmark run -s full         # Run benchmark on all photos
    bnr benchmark ui                  # Launch benchmark web UI (labels + inspection)
    bnr benchmark list                # List saved benchmark runs
    bnr benchmark clean               # Clean old benchmark runs
    bnr benchmark baseline            # Update baseline if metrics improved
    bnr benchmark tune                # Sweep face detection parameters
    bnr benchmark inspect             # Show URL to inspect latest run
"""

import argparse
import sys

from logging_utils import configure_logging, add_logging_args
from cli.serve import add_serve_subparser
from cli.scan import add_scan_subparser
from cli.album import add_album_subparser
from cli.cache import add_cache_subparser
from cli.faces import add_faces_subparser
from cli.benchmark import add_benchmark_subparser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bnr",
        description="Bib Number Recognizer - detect race bib numbers in photos",
    )
    add_logging_args(parser)
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    add_serve_subparser(subparsers)
    add_scan_subparser(subparsers)
    add_benchmark_subparser(subparsers)
    add_album_subparser(subparsers)
    add_cache_subparser(subparsers)
    add_faces_subparser(subparsers)

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

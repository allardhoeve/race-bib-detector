"""Scan command CLI parsing and control flow."""

from __future__ import annotations

import argparse
import logging
from scan import run_scan

logger = logging.getLogger(__name__)


def add_scan_subparser(subparsers: argparse._SubParsersAction) -> None:
    scan_parser = subparsers.add_parser(
        "scan",
        help="Scan a local directory or file for bib numbers",
    )
    scan_parser.add_argument(
        "source",
        nargs="?",
        help="Local directory or image file path",
    )
    scan_parser.add_argument(
        "--rescan",
        metavar="ID",
        help="Rescan a specific photo by hash or index",
    )
    scan_parser.add_argument(
        "--album-label",
        help="Optional album label for grouping (used to derive album ID)",
    )
    scan_parser.add_argument(
        "--album-id",
        help="Optional explicit album ID (overrides derived ID)",
    )
    scan_parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force rescan even if already processed",
    )
    scan_parser.add_argument(
        "--limit", "-n",
        type=int,
        default=None,
        help="Maximum number of photos to process (default: all)",
    )
    mode_group = scan_parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--faces-only",
        action="store_true",
        help="Run face detection only (skip bib detection)",
    )
    mode_group.add_argument(
        "--no-faces",
        action="store_true",
        help="Skip face detection (bib detection only)",
    )
    scan_parser.set_defaults(_cmd=cmd_scan)


def cmd_scan(args: argparse.Namespace) -> int:
    if not args.source and not args.rescan:
        logger.error("Please provide a local path or --rescan ID")
        return 1

    try:
        if args.rescan:
            stats = run_scan(
                args.rescan,
                rescan=True,
                limit=args.limit,
                faces_only=args.faces_only,
                no_faces=args.no_faces,
            )
        else:
            stats = run_scan(
                args.source,
                rescan=args.force,
                limit=args.limit,
                faces_only=args.faces_only,
                no_faces=args.no_faces,
                album_label=args.album_label,
                album_id=args.album_id,
            )
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    logger.info("%s", "=" * 50)
    logger.info("Scan Complete!")
    logger.info("%s", "=" * 50)
    logger.info("Photos found:   %s", stats["photos_found"])
    logger.info("Photos scanned: %s", stats["photos_scanned"])
    logger.info("Photos skipped: %s", stats["photos_skipped"])
    logger.info("Bibs detected:  %s", stats["bibs_detected"])
    logger.info("Faces detected: %s", stats["faces_detected"])
    logger.info("Results saved to bibs.db")
    logger.info("Query example: sqlite3 bibs.db \"SELECT * FROM bib_detections LIMIT 10\"")
    return 0

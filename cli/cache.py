"""Cache cleanup CLI commands."""

from __future__ import annotations

import argparse
import logging

from cache_cleanup import cleanup_unreferenced_cache, delete_album_cache_by_id

logger = logging.getLogger(__name__)


def add_cache_subparser(subparsers: argparse._SubParsersAction) -> None:
    cache_parser = subparsers.add_parser(
        "cache",
        help="Manage cached artifacts",
    )
    cache_subparsers = cache_parser.add_subparsers(
        dest="cache_command",
        help="Cache command",
    )

    cleanup_parser = cache_subparsers.add_parser(
        "cleanup",
        help="Delete cached artifacts (default: remove unreferenced files)",
    )
    cleanup_parser.add_argument(
        "--album",
        help="Delete cached artifacts for a specific album ID",
    )
    cleanup_parser.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Print what would be deleted without removing files",
    )
    cleanup_parser.set_defaults(_cmd=cmd_cache_cleanup)

    cache_parser.set_defaults(_cache_parser=cache_parser)


def cmd_cache_cleanup(args: argparse.Namespace) -> int:
    if args.album:
        logger.info("Cleaning cache for album %s", args.album)
        counts = delete_album_cache_by_id(args.album, dry_run=args.dry_run)
    else:
        logger.info("Cleaning unreferenced cache artifacts")
        counts = cleanup_unreferenced_cache(dry_run=args.dry_run)

    if args.dry_run:
        logger.info("Dry run complete.")
    logger.info("Deleted: %s", counts["deleted"])
    logger.info("Missing: %s", counts["missing"])
    logger.info("Skipped: %s", counts["skipped"])
    return 0

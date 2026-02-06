"""Album command CLI parsing and control flow."""

from __future__ import annotations

import argparse
import logging

import db
from cache_cleanup import delete_album_cache

logger = logging.getLogger(__name__)


def add_album_subparser(subparsers: argparse._SubParsersAction) -> None:
    album_parser = subparsers.add_parser(
        "album",
        help="Manage album metadata (list/forget)",
    )
    album_subparsers = album_parser.add_subparsers(
        dest="album_command",
        help="Album command",
    )

    album_list = album_subparsers.add_parser(
        "list",
        help="List albums and photo counts",
    )
    album_list.set_defaults(_cmd=cmd_album_list)

    album_forget = album_subparsers.add_parser(
        "forget",
        help="Forget an album (remove DB records only)",
    )
    album_forget.add_argument("album_id", help="Album ID to forget")
    album_forget.add_argument(
        "-f", "--force",
        action="store_true",
        help="Skip confirmation prompt",
    )
    album_forget.set_defaults(_cmd=cmd_album_forget)

    album_parser.set_defaults(_album_parser=album_parser)


def cmd_album_list(args: argparse.Namespace) -> int:
    conn = db.get_connection()
    albums = db.list_albums(conn)
    conn.close()

    if not albums:
        logger.info("No albums found.")
        return 0

    logger.info("%-10s %-30s %-10s %s", "Album ID", "Label", "Photos", "Created")
    logger.info("%s", "-" * 80)
    for album in albums:
        label = album.get("label") or "(none)"
        created_at = album.get("created_at") or "(unknown)"
        logger.info(
            "%-10s %-30s %-10s %s",
            album["album_id"],
            label[:30],
            album.get("photo_count", 0),
            created_at,
        )
    return 0


def cmd_album_forget(args: argparse.Namespace) -> int:
    album_id = args.album_id
    if not args.force:
        confirm = input(
            f"Forget album '{album_id}' from the database? This does NOT delete originals. (y/N): "
        ).strip().lower()
        if confirm not in {"y", "yes"}:
            logger.info("Canceled.")
            return 1

    conn = db.get_connection()
    cache_entries = db.list_album_cache_entries(conn, album_id)
    cache_counts = delete_album_cache(cache_entries, dry_run=False)
    counts = db.forget_album(conn, album_id)
    conn.close()

    logger.info("Album %s forgotten:", album_id)
    logger.info("  Cache deleted:    %s", cache_counts["deleted"])
    logger.info("  Cache missing:    %s", cache_counts["missing"])
    logger.info("  Cache skipped:    %s", cache_counts["skipped"])
    logger.info("  Photos:           %s", counts["photos"])
    logger.info("  Bib detections:   %s", counts["bib_detections"])
    logger.info("  Face detections:  %s", counts["face_detections"])
    logger.info("  Bib assignments:  %s", counts["bib_assignments"])
    logger.info("  Face clusters:    %s", counts["face_clusters"])
    logger.info("  Cluster members:  %s", counts["face_cluster_members"])
    logger.info("  Album rows:       %s", counts["albums"])
    return 0

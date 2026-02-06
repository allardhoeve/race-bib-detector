#!/usr/bin/env python3
"""List all photos and their detected bib numbers."""

import argparse
import logging

import db
from logging_utils import add_logging_args, configure_logging

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List photos and detected bibs")
    add_logging_args(parser)
    parser.add_argument("--cache", "-c", action="store_true",
                        help="Show cache file paths instead of URLs")
    parser.add_argument("--hash", type=str, help="Show details for a specific photo hash")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level, args.verbose, args.quiet)

    if not db.DB_PATH.exists():
        logger.error("Database not found. Run scan_album.py first.")
        return 1

    conn = db.get_connection()
    cursor = conn.cursor()

    # Show single photo details
    if args.hash:
        cursor.execute("""
            SELECT p.photo_hash, p.photo_url, p.cache_path,
                   GROUP_CONCAT(bd.bib_number || ' (' || ROUND(bd.confidence, 2) || ')', ', ') as bibs
            FROM photos p
            LEFT JOIN bib_detections bd ON p.id = bd.photo_id
            WHERE p.photo_hash = ?
            GROUP BY p.id
        """, (args.hash,))
        row = cursor.fetchone()
        if row:
            photo_hash, photo_url, cache_path, bibs = row
            logger.info("Photo Hash:  %s", photo_hash)
            logger.info("Bibs:        %s", bibs or "(none)")
            logger.info("Cache:       %s", cache_path or "(not cached)")
            logger.info("URL:         %s", photo_url)
        else:
            logger.warning("Photo hash %s not found.", args.hash)
        conn.close()
        return 0

    # Get all photos with their detected bibs
    cursor.execute("""
        SELECT
            p.photo_hash,
            p.photo_url,
            p.cache_path,
            GROUP_CONCAT(bd.bib_number || ' (' || ROUND(bd.confidence, 2) || ')', ', ') as bibs
        FROM photos p
        LEFT JOIN bib_detections bd ON p.id = bd.photo_id
        GROUP BY p.id
        ORDER BY p.id
    """)

    rows = cursor.fetchall()

    if not rows:
        logger.info("No photos in database.")
        return 0

    if args.cache:
        logger.info("%-10s %-40s %s", "Hash", "Bibs Detected", "Cache Path")
        logger.info("%s", "-" * 94)
        for photo_hash, photo_url, cache_path, bibs in rows:
            bibs_str = bibs if bibs else "(none)"
            cache_display = cache_path if cache_path else "(not cached)"
            logger.info("%-10s %-40s %s", photo_hash, bibs_str, cache_display)
    else:
        logger.info("%-10s %-40s %s", "Hash", "Bibs Detected", "Photo URL")
        logger.info("%s", "-" * 104)
        for photo_hash, photo_url, cache_path, bibs in rows:
            bibs_str = bibs if bibs else "(none)"
            logger.info("%-10s %-40s %s", photo_hash, bibs_str, photo_url)

    # Summary stats
    cursor.execute("SELECT COUNT(*) FROM photos")
    total_photos = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM bib_detections")
    total_detections = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT bib_number) FROM bib_detections")
    unique_bibs = cursor.fetchone()[0]

    logger.info("%s", "-" * 100)
    logger.info(
        "Total: %s photos, %s detections, %s unique bibs",
        total_photos,
        total_detections,
        unique_bibs,
    )

    conn.close()
    return 0


if __name__ == "__main__":
    main()

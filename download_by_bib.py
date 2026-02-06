#!/usr/bin/env python3
"""Download photos containing specific bib numbers."""

import argparse
import logging
from pathlib import Path

from tqdm import tqdm

import db
from logging_utils import add_logging_args, configure_logging
from utils import download_image_to_file, get_full_res_url

logger = logging.getLogger(__name__)


def download_by_bib(bib_numbers: list[str], output_dir: Path) -> dict:
    """Download all photos containing the specified bib numbers."""
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get database connection
    conn = db.get_connection()

    # Query for matching photos
    photos = db.get_photos_by_bib(conn, bib_numbers)

    if not photos:
        logger.warning("No photos found for bib number(s): %s", ", ".join(bib_numbers))
        return {"found": 0, "downloaded": 0, "failed": 0}

    logger.info(
        "Found %s photo(s) matching bib number(s): %s",
        len(photos),
        ", ".join(bib_numbers),
    )

    stats = {"found": len(photos), "downloaded": 0, "failed": 0}

    for photo in tqdm(photos, desc="Downloading"):
        photo_hash = photo["photo_hash"]
        photo_url = photo["photo_url"]
        matched_bibs = photo["matched_bibs"]

        # Create filename with bib numbers and photo hash
        bibs_str = matched_bibs.replace(",", "-")
        filename = f"bib_{bibs_str}_{photo_hash}.jpg"
        output_path = output_dir / filename

        # Skip if already downloaded
        if output_path.exists():
            logger.info("Skipping (exists): %s", filename)
            stats["downloaded"] += 1
            continue

        # Download full resolution image
        full_res_url = get_full_res_url(photo_url)

        if download_image_to_file(full_res_url, output_path):
            stats["downloaded"] += 1
        else:
            stats["failed"] += 1

    conn.close()
    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download photos containing specific bib numbers"
    )
    add_logging_args(parser)
    parser.add_argument(
        "bib_numbers",
        help="Bib number(s) to search for (comma-separated for multiple)"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("./photos"),
        help="Output directory for downloaded photos (default: ./photos)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level, args.verbose, args.quiet)

    # Parse bib numbers (handle comma-separated input)
    bib_numbers = [b.strip() for b in args.bib_numbers.split(",")]
    bib_numbers = [b for b in bib_numbers if b]  # Remove empty strings

    if not bib_numbers:
        logger.error("No valid bib numbers provided")
        return 1

    stats = download_by_bib(bib_numbers, args.output)

    logger.info("%s", "=" * 50)
    logger.info("Download Complete!")
    logger.info("%s", "=" * 50)
    logger.info("Photos found:      %s", stats["found"])
    logger.info("Photos downloaded: %s", stats["downloaded"])
    logger.info("Failed downloads:  %s", stats["failed"])
    logger.info("Photos saved to: %s", args.output.absolute())
    return 0


if __name__ == "__main__":
    main()

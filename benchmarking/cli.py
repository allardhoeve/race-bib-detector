#!/usr/bin/env python3
"""CLI tools for benchmark management."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarking.ground_truth import (
    load_ground_truth,
    save_ground_truth,
    GroundTruth,
    PhotoLabel,
    ALLOWED_TAGS,
)
from benchmarking.photo_index import (
    update_photo_index,
    load_photo_index,
    get_path_for_hash,
)


def get_photos_dir() -> Path:
    """Get the photos directory."""
    return Path(__file__).parent.parent / "photos"


def cmd_scan(args: argparse.Namespace) -> int:
    """Scan photos directory and update the index."""
    photos_dir = get_photos_dir()

    if not photos_dir.exists():
        print(f"Error: Photos directory not found: {photos_dir}")
        return 1

    print(f"Scanning {photos_dir}...")
    index, stats = update_photo_index(photos_dir, recursive=True)

    print(f"\nScan complete:")
    print(f"  Total files: {stats['total_files']}")
    print(f"  Unique photos: {stats['unique_hashes']}")
    print(f"  Duplicates: {stats['duplicates']}")
    print(f"  New since last scan: {stats['new_photos']}")

    # Check ground truth status
    gt = load_ground_truth()
    labeled = len(gt.photos)
    unlabeled = stats['unique_hashes'] - labeled

    print(f"\nLabeling status:")
    print(f"  Labeled: {labeled}")
    print(f"  Unlabeled: {unlabeled}")

    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    """Show ground truth statistics."""
    gt = load_ground_truth()

    if not gt.photos:
        print("No ground truth data yet. Run 'scan' first, then start labeling.")
        return 0

    stats = gt.stats()

    print("Ground Truth Statistics")
    print("=" * 40)
    print(f"Total photos: {stats['total_photos']}")
    print(f"Photos with bibs: {stats['photos_with_bibs']}")
    print(f"Photos without bibs: {stats['photos_without_bibs']}")
    print(f"Total bib annotations: {stats['total_bibs']}")

    print(f"\nBy split:")
    for split, count in stats['by_split'].items():
        print(f"  {split}: {count}")

    print(f"\nBy tag:")
    for tag, count in sorted(stats['by_tag'].items()):
        if count > 0:
            print(f"  {tag}: {count}")

    return 0


def cmd_unlabeled(args: argparse.Namespace) -> int:
    """List unlabeled photos."""
    index = load_photo_index()
    gt = load_ground_truth()

    all_hashes = set(index.keys())
    unlabeled = gt.get_unlabeled_hashes(all_hashes)

    if not unlabeled:
        print("All photos are labeled!")
        return 0

    photos_dir = get_photos_dir()
    limit = args.limit or 20

    print(f"Unlabeled photos ({len(unlabeled)} total, showing first {limit}):")
    for i, content_hash in enumerate(sorted(unlabeled)):
        if i >= limit:
            print(f"  ... and {len(unlabeled) - limit} more")
            break

        path = get_path_for_hash(content_hash, photos_dir, index)
        if path:
            print(f"  {content_hash[:16]}... -> {path.relative_to(photos_dir)}")
        else:
            print(f"  {content_hash[:16]}... -> (path not found)")

    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """Show details for a specific photo."""
    gt = load_ground_truth()
    index = load_photo_index()
    photos_dir = get_photos_dir()

    # Find by hash prefix
    query = args.hash
    matches = [h for h in gt.photos.keys() if h.startswith(query)]

    if not matches:
        # Check if it's in the index but not labeled
        index_matches = [h for h in index.keys() if h.startswith(query)]
        if index_matches:
            print(f"Photo {query}... found but not labeled yet.")
            for h in index_matches[:5]:
                path = get_path_for_hash(h, photos_dir, index)
                print(f"  {h[:16]}... -> {path}")
            return 0
        else:
            print(f"No photo found matching: {query}")
            return 1

    if len(matches) > 1:
        print(f"Multiple matches for {query}:")
        for h in matches[:10]:
            print(f"  {h[:16]}...")
        return 1

    content_hash = matches[0]
    label = gt.get_photo(content_hash)
    path = get_path_for_hash(content_hash, photos_dir, index)

    print(f"Photo: {content_hash}")
    print(f"Path: {path}")
    print(f"Bibs: {label.bibs if label.bibs else '(none)'}")
    print(f"Tags: {label.tags if label.tags else '(none)'}")
    print(f"Split: {label.split}")
    if label.photo_hash:
        print(f"Photo hash: {label.photo_hash}")

    return 0


def cmd_label(args: argparse.Namespace) -> int:
    """Add or update a label for a photo."""
    gt = load_ground_truth()
    index = load_photo_index()

    # Find by hash prefix
    query = args.hash
    all_hashes = set(index.keys())
    matches = [h for h in all_hashes if h.startswith(query)]

    if not matches:
        print(f"No photo found matching: {query}")
        return 1

    if len(matches) > 1:
        print(f"Multiple matches for {query}, be more specific:")
        for h in matches[:10]:
            print(f"  {h[:16]}...")
        return 1

    content_hash = matches[0]

    # Parse bibs
    bibs = []
    if args.bibs:
        for b in args.bibs.split(","):
            b = b.strip()
            if b:
                try:
                    bibs.append(int(b))
                except ValueError:
                    print(f"Invalid bib number: {b}")
                    return 1

    # Parse tags
    tags = []
    if args.tags:
        for t in args.tags.split(","):
            t = t.strip()
            if t:
                if t not in ALLOWED_TAGS:
                    print(f"Invalid tag: {t}")
                    print(f"Allowed tags: {sorted(ALLOWED_TAGS)}")
                    return 1
                tags.append(t)

    # Get or create label
    existing = gt.get_photo(content_hash)
    if existing:
        # Update existing
        if args.bibs is not None:
            existing.bibs = sorted(set(bibs))
        if args.tags is not None:
            existing.tags = tags
        if args.split:
            existing.split = args.split
        label = existing
    else:
        # Create new
        label = PhotoLabel(
            content_hash=content_hash,
            bibs=bibs,
            tags=tags,
            split=args.split or "full",
        )
        gt.add_photo(label)

    save_ground_truth(gt)
    print(f"Saved label for {content_hash[:16]}...")
    print(f"  Bibs: {label.bibs}")
    print(f"  Tags: {label.tags}")
    print(f"  Split: {label.split}")

    return 0


def cmd_ui(args: argparse.Namespace) -> int:
    """Launch the labeling UI."""
    from benchmarking.labeling_app import main as labeling_main
    return labeling_main()


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark ground truth management"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # scan command
    scan_parser = subparsers.add_parser("scan", help="Scan photos directory")

    # ui command
    ui_parser = subparsers.add_parser("ui", help="Launch labeling UI")

    # stats command
    stats_parser = subparsers.add_parser("stats", help="Show statistics")

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

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    commands = {
        "scan": cmd_scan,
        "ui": cmd_ui,
        "stats": cmd_stats,
        "unlabeled": cmd_unlabeled,
        "show": cmd_show,
        "label": cmd_label,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())

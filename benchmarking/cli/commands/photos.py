"""Photo management CLI commands."""
from __future__ import annotations

import argparse
from pathlib import Path

from benchmarking.ground_truth import (
    BibBox,
    BibPhotoLabel,
    load_bib_ground_truth,
    save_bib_ground_truth,
    load_face_ground_truth,
    BIB_PHOTO_TAGS,
    FACE_PHOTO_TAGS,
    FACE_BOX_TAGS,
    ALLOWED_SPLITS,
)
from benchmarking.photo_index import (
    update_photo_index,
    load_photo_index,
    get_path_for_hash,
)
from benchmarking.photo_metadata import (
    PhotoMetadata,
    load_photo_metadata,
    save_photo_metadata,
)


def get_photos_dir() -> Path:
    """Get the photos directory."""
    return Path(__file__).parents[3] / "photos"


def cmd_scan(args: argparse.Namespace) -> int:
    """Scan photos directory and update the index."""
    photos_dir = get_photos_dir()

    if not photos_dir.exists():
        print(f"Error: Photos directory not found: {photos_dir}")
        return 1

    print(f"Scanning {photos_dir}...")
    index, stats = update_photo_index(photos_dir, recursive=True)

    print("\nScan complete:")
    print(f"  Total files: {stats['total_files']}")
    print(f"  Unique photos: {stats['unique_hashes']}")
    print(f"  Duplicates: {stats['duplicates']}")
    print(f"  New since last scan: {stats['new_photos']}")

    # Check ground truth status
    gt = load_bib_ground_truth()
    labeled = sum(1 for p in gt.photos.values() if p.labeled)
    unlabeled = stats['unique_hashes'] - labeled

    print("\nLabeling status:")
    print(f"  Labeled: {labeled}")
    print(f"  Unlabeled: {unlabeled}")

    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    """Show ground truth statistics."""
    bib_gt = load_bib_ground_truth()
    face_gt = load_face_ground_truth()

    if not bib_gt.photos and not face_gt.photos:
        print("No ground truth data yet. Run 'scan' first, then start labeling.")
        return 0

    total = len(bib_gt.photos)

    print("Ground Truth Statistics")
    print("=" * 40)
    print(f"Total photos: {total}")

    labeled = sum(1 for p in bib_gt.photos.values() if p.labeled)
    print(f"Photos with bib labels: {labeled}")
    print(f"Photos without bib labels: {total - labeled}")

    with_bibs = sum(1 for p in bib_gt.photos.values() if p.bib_numbers_int)
    print(f"Photos with bibs: {with_bibs}")
    print(f"Photos without bibs: {total - with_bibs}")

    total_bibs = sum(len(p.bib_numbers_int) for p in bib_gt.photos.values())
    print(f"Total bib annotations: {total_bibs}")

    meta_store = load_photo_metadata()

    print("\nBy split:")
    for split in sorted(ALLOWED_SPLITS):
        count = len(meta_store.get_hashes_by_split(split))
        print(f"  {split}: {count}")

    print("\nBy bib tag:")
    for tag in sorted(BIB_PHOTO_TAGS):
        count = sum(1 for m in meta_store.photos.values() if tag in m.bib_tags)
        if count > 0:
            print(f"  {tag}: {count}")

    print("\nFace labeling:")
    face_photos_with_boxes = sum(1 for p in face_gt.photos.values() if p.boxes)
    print(f"  Photos with face boxes: {face_photos_with_boxes}")
    print(f"  Photos without face boxes: {len(face_gt.photos) - face_photos_with_boxes}")

    print("\nBy face photo tag:")
    for tag in sorted(FACE_PHOTO_TAGS):
        count = sum(1 for m in meta_store.photos.values() if tag in m.face_tags)
        if count > 0:
            print(f"  {tag}: {count}")

    print("\nBy face box tag:")
    for tag in sorted(FACE_BOX_TAGS):
        count = sum(
            1 for p in face_gt.photos.values()
            for b in p.boxes if tag in b.tags
        )
        if count > 0:
            print(f"  {tag}: {count} boxes")

    return 0


def cmd_unlabeled(args: argparse.Namespace) -> int:
    """List unlabeled photos."""
    index = load_photo_index()
    gt = load_bib_ground_truth()

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
            print(f"  {content_hash[:8]}... -> {path.relative_to(photos_dir)}")
        else:
            print(f"  {content_hash[:8]}... -> (path not found)")

    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """Show details for a specific photo."""
    gt = load_bib_ground_truth()
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
                print(f"  {h[:8]}... -> {path}")
            return 0
        else:
            print(f"No photo found matching: {query}")
            return 1

    if len(matches) > 1:
        print(f"Multiple matches for {query}:")
        for h in matches[:10]:
            print(f"  {h[:8]}...")
        return 1

    content_hash = matches[0]
    label = gt.get_photo(content_hash)
    path = get_path_for_hash(content_hash, photos_dir, index)

    meta_store = load_photo_metadata()
    meta = meta_store.get(content_hash)

    print(f"Photo: {content_hash}")
    print(f"Path: {path}")
    print(f"Bibs: {label.bibs if label.bibs else '(none)'}")
    print(f"Tags: {meta.bib_tags if meta and meta.bib_tags else '(none)'}")
    print(f"Split: {meta.split if meta else '(unknown)'}")

    return 0


def cmd_label(args: argparse.Namespace) -> int:
    """Add or update a label for a photo."""
    gt = load_bib_ground_truth()
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
            print(f"  {h[:8]}...")
        return 1

    content_hash = matches[0]

    # Parse bibs → BibBox entries (zero-area coords for CLI-entered numbers)
    bib_boxes: list[BibBox] | None = None
    if args.bibs is not None:
        bib_boxes = []
        for b in args.bibs.split(","):
            b = b.strip()
            if b:
                try:
                    int(b)  # Validate it's a number
                except ValueError:
                    print(f"Invalid bib number: {b}")
                    return 1
                bib_boxes.append(BibBox(x=0, y=0, w=0, h=0, number=b, scope="bib"))

    # Parse tags
    tags: list[str] | None = None
    if args.tags is not None:
        tags = []
        for t in args.tags.split(","):
            t = t.strip()
            if t:
                if t not in BIB_PHOTO_TAGS:
                    print(f"Invalid tag: {t}")
                    print(f"Allowed tags: {sorted(BIB_PHOTO_TAGS)}")
                    return 1
                tags.append(t)

    # Get or create label
    existing = gt.get_photo(content_hash)
    if existing:
        if bib_boxes is not None:
            existing.boxes = bib_boxes
        existing.labeled = True
        label = existing
    else:
        label = BibPhotoLabel(
            content_hash=content_hash,
            boxes=bib_boxes or [],
            labeled=True,
        )
        gt.add_photo(label)

    save_bib_ground_truth(gt)

    # Save tags and split to PhotoMetadata
    meta_store = load_photo_metadata()
    meta = meta_store.get(content_hash) or PhotoMetadata(paths=[])
    if tags is not None:
        meta.bib_tags = tags
    if args.split:
        meta.split = args.split
    meta_store.set(content_hash, meta)
    save_photo_metadata(meta_store)

    print(f"Saved label for {content_hash[:8]}...")
    print(f"  Bibs: {label.bibs}")
    print(f"  Tags: {meta.bib_tags}")
    print(f"  Split: {meta.split}")

    return 0


def cmd_prepare(args: argparse.Namespace) -> int:
    """Prepare benchmark photos from a source directory."""
    from benchmarking.prepare import prepare_benchmark

    source_dir = Path(args.source)
    if not source_dir.exists():
        print(f"Error: Source directory not found: {source_dir}")
        return 1
    if not source_dir.is_dir():
        print(f"Error: Not a directory: {source_dir}")
        return 1

    photos_dir = get_photos_dir()

    print(f"Preparing benchmark from: {source_dir}")
    print(f"Photos directory: {photos_dir}")

    if args.reset_labels:
        print("  --reset-labels: will clear all labels")
    if args.refresh:
        print("  --refresh: will re-run ghost labeling")

    result = prepare_benchmark(
        source_dir=source_dir,
        photos_dir=photos_dir,
        reset_labels=args.reset_labels,
        refresh=args.refresh,
    )

    print("\nPrepare complete:")
    print(f"  Copied: {result.copied}")
    print(f"  Skipped (already present): {result.skipped}")
    print(f"  Total photos in benchmark: {result.total_photos}")

    if result.new_hashes:
        print(f"  New photos added: {len(result.new_hashes)}")

    if args.reset_labels:
        print(f"  Labels reset for all {result.total_photos} photos")

    return 0


def cmd_ui(args: argparse.Namespace) -> int:
    """Launch the unified web UI (labels + benchmark inspection)."""
    from benchmarking.web_app import main as web_main
    return web_main()

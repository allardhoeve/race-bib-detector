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
    """Launch the unified web UI (labels + benchmark inspection)."""
    from benchmarking.web_app import main as web_main
    return web_main()


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Run benchmark and report results."""
    from benchmarking.runner import (
        run_benchmark,
        compare_to_baseline,
        load_baseline,
        RESULTS_DIR,
    )
    from config import BENCHMARK_REGRESSION_TOLERANCE

    split = args.split or "iteration"
    verbose = not args.quiet

    try:
        run = run_benchmark(split=split, verbose=verbose)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    # Print results
    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)

    m = run.metrics
    print(f"\nSplit: {split}")
    print(f"Photos: {m.total_photos}")
    print(f"Runtime: {run.metadata.total_runtime_seconds:.1f}s")

    print(f"\nMetrics:")
    print(f"  Precision: {m.precision:.1%}")
    print(f"  Recall:    {m.recall:.1%}")
    print(f"  F1:        {m.f1:.1%}")

    print(f"\nDetection counts:")
    print(f"  TP: {m.total_tp}  FP: {m.total_fp}  FN: {m.total_fn}")

    print(f"\nPhoto status:")
    print(f"  PASS:    {m.pass_count:3} ({m.pass_count/m.total_photos:.0%})")
    print(f"  PARTIAL: {m.partial_count:3} ({m.partial_count/m.total_photos:.0%})")
    print(f"  MISS:    {m.miss_count:3} ({m.miss_count/m.total_photos:.0%})")

    # Tag breakdown if verbose
    if verbose and any(r.tags for r in run.photo_results):
        print(f"\nBy tag:")
        tag_stats: dict[str, dict] = {}
        for r in run.photo_results:
            for tag in r.tags:
                if tag not in tag_stats:
                    tag_stats[tag] = {"tp": 0, "fp": 0, "fn": 0, "count": 0}
                tag_stats[tag]["tp"] += r.tp
                tag_stats[tag]["fp"] += r.fp
                tag_stats[tag]["fn"] += r.fn
                tag_stats[tag]["count"] += 1

        for tag, s in sorted(tag_stats.items()):
            tp, fp, fn = s["tp"], s["fp"], s["fn"]
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0
            print(f"  {tag}: {s['count']} photos, P={prec:.0%} R={rec:.0%}")

    # Baseline comparison (only for full split)
    exit_code = 0
    if split == "full":
        baseline = load_baseline()
        if baseline:
            judgement, details = compare_to_baseline(run, BENCHMARK_REGRESSION_TOLERANCE)

            print(f"\n" + "-" * 60)
            print("BASELINE COMPARISON")
            print("-" * 60)
            print(f"Baseline: {details['baseline_commit']} ({details['baseline_timestamp'][:10]})")
            print(f"Tolerance: {BENCHMARK_REGRESSION_TOLERANCE:.1%}")

            print(f"\nDeltas:")
            print(f"  Precision: {details['precision_delta']:+.1%} (was {details['baseline_precision']:.1%})")
            print(f"  Recall:    {details['recall_delta']:+.1%} (was {details['baseline_recall']:.1%})")
            print(f"  F1:        {details['f1_delta']:+.1%} (was {details['baseline_f1']:.1%})")

            # Judgement with color/emphasis
            print(f"\n{'=' * 60}")
            if judgement == "REGRESSED":
                print(f"JUDGEMENT: ❌ REGRESSED")
                exit_code = 1
            elif judgement == "IMPROVED":
                print(f"JUDGEMENT: ✅ IMPROVED")
            else:
                print(f"JUDGEMENT: ➖ NO CHANGE")
            print("=" * 60)
        else:
            print(f"\nNo baseline exists. Run 'bnr benchmark set-baseline' to create one.")
    else:
        print(f"\n(Baseline comparison only available for 'full' split)")

    return exit_code


def cmd_benchmark_inspect(args: argparse.Namespace) -> int:
    """Launch visual inspection UI for a benchmark run."""
    from benchmarking.runner import get_run, get_latest_run

    # Get the run
    if args.run_id:
        run = get_run(args.run_id)
        if not run:
            print(f"Error: Run not found: {args.run_id}")
            return 1
        run_id = run.metadata.run_id
    else:
        run = get_latest_run()
        if not run:
            print("Error: No benchmark runs found.")
            print("Run 'benchmark' to create one.")
            return 1
        run_id = run.metadata.run_id

    print(f"Open http://localhost:30002/benchmark/{run_id}/ in your browser")
    print(f"Or run 'python -m benchmarking.cli ui' to start the server")
    return 0


def cmd_benchmark_list(args: argparse.Namespace) -> int:
    """List all saved benchmark runs."""
    from benchmarking.runner import list_runs

    runs = list_runs()

    if not runs:
        print("No benchmark runs found.")
        print("Run 'benchmark' to create one.")
        return 0

    # Print header
    print(f"{'ID':<10} {'Date':<12} {'Split':<10} {'P':>6} {'R':>6} {'F1':>6} {'Commit':<10} {'Pipeline':<20}")
    print("-" * 90)

    for run in runs:
        baseline_marker = " (baseline)" if run.get("is_baseline") else ""
        date = run["timestamp"][:10]
        pipeline = run.get("pipeline", "unknown")
        print(
            f"{run['run_id']:<10} {date:<12} {run['split']:<10} "
            f"{run['precision']:>5.1%} {run['recall']:>5.1%} {run['f1']:>5.1%} "
            f"{run['git_commit']:<10} {pipeline}{baseline_marker}"
        )

    print(f"\nTotal: {len(runs)} runs")
    return 0


def cmd_benchmark_clean(args: argparse.Namespace) -> int:
    """Clean up old benchmark runs."""
    from benchmarking.runner import list_runs, clean_runs, load_baseline

    runs = list_runs()

    if not runs:
        print("No benchmark runs to clean.")
        return 0

    # Determine what to keep
    keep_count = args.keep_latest or 5
    baseline = load_baseline()
    baseline_id = baseline.metadata.run_id if baseline else None

    # Calculate what would be deleted
    to_delete = clean_runs(keep_count=keep_count, dry_run=True)

    # Filter out baseline if --keep-baseline
    if args.keep_baseline and baseline_id:
        to_delete = [r for r in to_delete if r["run_id"] != baseline_id]

    # Filter by age if --older-than
    if args.older_than:
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(days=args.older_than)
        to_delete = [
            r for r in to_delete
            if datetime.fromisoformat(r["timestamp"]) < cutoff
        ]

    if not to_delete:
        print(f"Nothing to clean. Keeping {min(keep_count, len(runs))} most recent runs.")
        return 0

    # Show what will be deleted
    print(f"The following {len(to_delete)} run(s) will be deleted:\n")
    total_size = 0
    for run_info in to_delete:
        size_str = f"{run_info['size_mb']:.1f}MB"
        baseline_marker = " (baseline)" if run_info["run_id"] == baseline_id else ""
        print(f"  {run_info['run_id']}  {run_info['timestamp'][:10]}  {run_info['split']:<10}  {size_str}{baseline_marker}")
        total_size += run_info["size_mb"]

    print(f"\nTotal: {total_size:.1f}MB")

    # Confirm unless --force
    if not args.force:
        response = input("\nProceed with deletion? [y/N] ").strip().lower()
        if response != "y":
            print("Aborted.")
            return 0

    # Actually delete
    import shutil
    from pathlib import Path
    deleted_count = 0
    for run_info in to_delete:
        run_dir = Path(run_info["path"])
        if run_dir.exists():
            shutil.rmtree(run_dir)
            deleted_count += 1
            print(f"  Deleted: {run_info['run_id']}")

    print(f"\n✅ Cleaned up {deleted_count} run(s), freed {total_size:.1f}MB")
    return 0


def cmd_set_baseline(args: argparse.Namespace) -> int:
    """Set a specific run as the baseline."""
    from benchmarking.runner import (
        get_run,
        get_latest_run,
        load_baseline,
        save_baseline,
    )

    # Get the run to set as baseline
    if args.run_id:
        run = get_run(args.run_id)
        if not run:
            print(f"Error: Run not found: {args.run_id}")
            return 1
    else:
        # Default to latest run
        run = get_latest_run()
        if not run:
            print("Error: No benchmark runs found.")
            print("Run 'bnr benchmark run --split full' first.")
            return 1

    # Check if it's a full split run
    if run.metadata.split != "full":
        print(f"Warning: Run {run.metadata.run_id} is from '{run.metadata.split}' split, not 'full'.")
        if not args.force:
            response = input("Set as baseline anyway? [y/N] ").strip().lower()
            if response != "y":
                print("Aborted.")
                return 0

    # Show current baseline if exists
    current_baseline = load_baseline()
    if current_baseline:
        print(f"Current baseline: {current_baseline.metadata.run_id}")
        print(f"  Precision: {current_baseline.metrics.precision:.1%}")
        print(f"  Recall:    {current_baseline.metrics.recall:.1%}")
        print(f"  F1:        {current_baseline.metrics.f1:.1%}")
        print()

    # Show new baseline info
    print(f"New baseline: {run.metadata.run_id}")
    print(f"  Split:     {run.metadata.split}")
    print(f"  Precision: {run.metrics.precision:.1%}")
    print(f"  Recall:    {run.metrics.recall:.1%}")
    print(f"  F1:        {run.metrics.f1:.1%}")
    if run.metadata.pipeline_config:
        print(f"  Pipeline:  {run.metadata.pipeline_config.summary()}")

    # Confirm unless --force
    if not args.force:
        response = input("\nSet this run as baseline? [y/N] ").strip().lower()
        if response != "y":
            print("Aborted.")
            return 0

    save_baseline(run)
    print(f"\n✅ Baseline set to {run.metadata.run_id}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark ground truth management"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # scan command
    scan_parser = subparsers.add_parser("scan", help="Scan photos directory")

    # ui command
    ui_parser = subparsers.add_parser("ui", help="Launch web UI (labels + benchmark inspection)")

    # benchmark command
    benchmark_parser = subparsers.add_parser("benchmark", help="Run benchmark")
    benchmark_parser.add_argument(
        "-s", "--split", choices=["iteration", "full"],
        default="iteration",
        help="Which split to run: 'full' = all photos, 'iteration' = subset for quick feedback (default: iteration)"
    )
    benchmark_parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="Suppress per-photo output"
    )

    # set-baseline command
    set_baseline_parser = subparsers.add_parser(
        "set-baseline", help="Set a specific run as the baseline"
    )
    set_baseline_parser.add_argument(
        "run_id", nargs="?", default=None,
        help="Run ID to set as baseline (defaults to latest)"
    )
    set_baseline_parser.add_argument(
        "-f", "--force", action="store_true",
        help="Skip confirmation prompts"
    )

    # benchmark-list command
    benchmark_list_parser = subparsers.add_parser(
        "benchmark-list", help="List saved benchmark runs"
    )

    # benchmark-inspect command
    benchmark_inspect_parser = subparsers.add_parser(
        "benchmark-inspect", help="Show URL to inspect a benchmark run (use 'ui' command to start server)"
    )
    benchmark_inspect_parser.add_argument(
        "run_id", nargs="?", default=None,
        help="Run ID to inspect (defaults to latest)"
    )

    # benchmark-clean command
    benchmark_clean_parser = subparsers.add_parser(
        "benchmark-clean", help="Remove old benchmark runs (like docker system prune)"
    )
    benchmark_clean_parser.add_argument(
        "--keep-latest", type=int, default=5,
        metavar="N",
        help="Keep the N most recent runs (default: 5)"
    )
    benchmark_clean_parser.add_argument(
        "--keep-baseline", action="store_true",
        help="Never delete the baseline run"
    )
    benchmark_clean_parser.add_argument(
        "--older-than", type=int,
        metavar="DAYS",
        help="Only delete runs older than N days"
    )
    benchmark_clean_parser.add_argument(
        "-f", "--force", action="store_true",
        help="Skip confirmation prompt"
    )

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
        "benchmark": cmd_benchmark,
        "set-baseline": cmd_set_baseline,
        "benchmark-list": cmd_benchmark_list,
        "benchmark-inspect": cmd_benchmark_inspect,
        "benchmark-clean": cmd_benchmark_clean,
        "stats": cmd_stats,
        "unlabeled": cmd_unlabeled,
        "show": cmd_show,
        "label": cmd_label,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())

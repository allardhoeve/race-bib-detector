"""Benchmark management CLI commands."""
from __future__ import annotations

import argparse

from benchmarking.photo_index import load_photo_index


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Run benchmark and report results."""
    from benchmarking.runner import (
        run_benchmark,
        compare_to_baseline,
        load_baseline,
    )
    from config import BENCHMARK_REGRESSION_TOLERANCE

    split = args.split or "iteration"
    verbose = not args.quiet

    try:
        run = run_benchmark(split=split, verbose=verbose, note=args.note)
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
    if run.metadata.note:
        print(f"Note: {run.metadata.note}")

    print("\nMetrics:")
    print(f"  Precision: {m.precision:.1%}")
    print(f"  Recall:    {m.recall:.1%}")
    print(f"  F1:        {m.f1:.1%}")

    print("\nDetection counts:")
    print(f"  TP: {m.total_tp}  FP: {m.total_fp}  FN: {m.total_fn}")

    print("\nPhoto status:")
    print(f"  PASS:    {m.pass_count:3} ({m.pass_count/m.total_photos:.0%})")
    print(f"  PARTIAL: {m.partial_count:3} ({m.partial_count/m.total_photos:.0%})")
    print(f"  MISS:    {m.miss_count:3} ({m.miss_count/m.total_photos:.0%})")

    # IoU scorecard
    if run.bib_scorecard:
        from benchmarking.scoring import format_scorecard
        sc = run.bib_scorecard
        has_iou_data = (sc.detection_tp + sc.detection_fp + sc.detection_fn) > 0
        if has_iou_data:
            print(f"\n{format_scorecard(bib=sc)}")
        else:
            print("\nIoU Scorecard: no GT boxes with coordinates yet")

    if run.link_scorecard and run.link_scorecard.gt_link_count > 0:
        from benchmarking.scoring import format_scorecard
        print(f"\n{format_scorecard(link=run.link_scorecard)}")

    # Tag breakdown if verbose
    if verbose and any(r.tags for r in run.photo_results):
        print("\nBy tag:")
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

            print("\n" + "-" * 60)
            print("BASELINE COMPARISON")
            print("-" * 60)
            print(f"Baseline: {details['baseline_commit']} ({details['baseline_timestamp'][:10]})")
            print(f"Tolerance: {BENCHMARK_REGRESSION_TOLERANCE:.1%}")

            print("\nDeltas:")
            print(f"  Precision: {details['precision_delta']:+.1%} (was {details['baseline_precision']:.1%})")
            print(f"  Recall:    {details['recall_delta']:+.1%} (was {details['baseline_recall']:.1%})")
            print(f"  F1:        {details['f1_delta']:+.1%} (was {details['baseline_f1']:.1%})")

            # Judgement with color/emphasis
            print(f"\n{'=' * 60}")
            if judgement == "REGRESSED":
                print("JUDGEMENT: ❌ REGRESSED")
                exit_code = 1
            elif judgement == "IMPROVED":
                print("JUDGEMENT: ✅ IMPROVED")
            else:
                print("JUDGEMENT: ➖ NO CHANGE")
            print("=" * 60)
        else:
            print("\nNo baseline exists. Run 'bnr benchmark set-baseline' to create one.")
    else:
        print("\n(Baseline comparison only available for 'full' split)")

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
    print("Or run 'python -m benchmarking.cli ui' to start the server")
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
    print(f"{'ID':<10} {'Date':<12} {'Split':<10} {'P':>6} {'R':>6} {'F1':>6} {'Commit':<10} {'Pipeline':<20} {'Passes':<25} {'Note'}")
    print("-" * 145)

    for run in runs:
        baseline_marker = " (baseline)" if run.get("is_baseline") else ""
        date = run["timestamp"][:10]
        pipeline = run.get("pipeline", "unknown")
        passes = run.get("passes", "unknown")
        note = run.get("note") or ""
        print(
            f"{run['run_id']:<10} {date:<12} {run['split']:<10} "
            f"{run['precision']:>5.1%} {run['recall']:>5.1%} {run['f1']:>5.1%} "
            f"{run['git_commit']:<10} {pipeline:<20} {passes:<25}{baseline_marker} {note}"
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


def cmd_freeze(args: argparse.Namespace) -> int:
    """Create a frozen snapshot of the current benchmark photo set."""
    import re
    from benchmarking.sets import freeze
    from benchmarking.completeness import get_all_completeness

    name = args.name
    description = args.description or ""

    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        print(f"Error: name must be alphanumeric with hyphens/underscores: {name!r}")
        return 1

    index = load_photo_index()
    if not index:
        print("Error: no photos in index. Run 'bnr benchmark scan' first.")
        return 1

    # Flatten list-of-paths to single path per hash
    flat_index = {h: (paths[0] if isinstance(paths, list) else paths)
                  for h, paths in index.items()}

    if args.all:
        hashes = sorted(flat_index.keys())
    else:
        rows = get_all_completeness()
        complete = [r for r in rows if r.is_complete or r.is_known_negative]
        incomplete = [r for r in rows if not r.is_complete and not r.is_known_negative]

        if incomplete and not args.include_incomplete:
            print(f"Warning: {len(incomplete)} photos are not fully labeled:")
            for r in incomplete[:10]:
                dims = []
                if not r.bib_labeled:
                    dims.append("bib")
                if not r.face_labeled:
                    dims.append("face")
                if not r.links_labeled:
                    dims.append("links")
                print(f"  {r.content_hash[:8]}  missing: {', '.join(dims)}")
            if len(incomplete) > 10:
                print(f"  ... and {len(incomplete) - 10} more")
            print("Use --include-incomplete to freeze anyway.")
            return 1

        if args.include_incomplete:
            hashes = sorted(r.content_hash for r in rows)
        else:
            hashes = sorted(r.content_hash for r in complete)

        if not hashes:
            print("No labeled photos to freeze. Use --all to include all photos.")
            return 1

    try:
        snapshot = freeze(
            name=name,
            hashes=hashes,
            index={h: flat_index[h] for h in hashes if h in flat_index},
            description=description,
        )
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    print(f"Snapshot '{name}' created:")
    print(f"  Photos: {snapshot.metadata.photo_count}")
    print(f"  Path:   {snapshot.path}")
    return 0


def cmd_frozen_list(args: argparse.Namespace) -> int:
    """List all frozen benchmark snapshots."""
    from benchmarking.sets import list_snapshots

    snapshots = list_snapshots()
    if not snapshots:
        print("No snapshots yet. Use 'bnr benchmark freeze --name <name>'.")
        return 0
    print(f"{'Name':<30} {'Photos':>8} {'Created':<12} Description")
    print("-" * 70)
    for m in snapshots:
        print(f"{m.name:<30} {m.photo_count:>8} {m.created_at[:10]:<12} {m.description}")
    return 0


# Alias for bnr.py backward compat
cmd_update_baseline = cmd_set_baseline

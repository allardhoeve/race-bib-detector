# Benchmarking System Design

## Problem Statement

When tuning detection parameters or adding preprocessing steps like CLAHE, we risk:
1. Regression: Fixing one photo breaks detection on others
2. False improvements: A change helps one edge case but hurts the common case
3. Unmeasured tradeoffs: Better recall but worse precision (or vice versa)

We need an objective way to measure detection quality across a representative set of photos.

## Decisions Summary

This section reflects the current agreed requirements.

Ground truth approach:
- Manual labeling of a fixed test set (Approach A)
- Start with 200 photos
- Store bibs per photo as integers, with no duplicates
- Key photos by a content hash for dedupe and idempotency
- Optionally store the 8-character photo hash for integration with existing code

Tagging:
- Tags are checkbox-style, configurable, and stored per photo
- Initial tag list: dark_bib, no_bib, blurry_bib, light_bib, light_faces, other_banners

Split and usage:
- Photos are assigned to a fixed split per photo
- Split ratio is configurable, initial ratio is flexible
- Use the iteration subset for rapid tuning
- Use the full set for overall performance reporting

Success criteria:
- No automatic pass/fail thresholds yet
- Focus on comparison and regression detection across runs

Output format:
- Use the detailed metrics table (Option B) as the default view

## Ground Truth: How We Define "Correct"

We use manual labeling as the source of truth.

Each photo entry contains:
- `bibs`: list of integer bib numbers, no duplicates
- `tags`: list of zero or more tags from the configured tag list
- `split`: fixed per-photo label to support iteration vs full set
- `content_hash`: required, used as canonical identity
- `photo_hash`: optional, for linking to existing URL/path-based hashing

A future extension is to support advanced labeling with locations per bib. This remains compatible with the current schema by adding optional fields later.

## Test Set: Which Photos to Include

Target size: 200 photos. The set should include a range of conditions such as:
- Clear, well-lit bibs
- Dark or shadowy bibs
- Gray or off-white bibs
- Multiple bibs in one photo
- Small bibs relative to the image
- No bibs (false-positive control)
- Partial or obscured bibs

## Metrics: What We Measure

Per-photo metrics:
- True Positives (TP): Correctly detected bibs
- False Positives (FP): Detected bibs that do not exist in ground truth
- False Negatives (FN): Missed bibs that should be detected

Aggregate metrics:
- Precision = TP / (TP + FP)
- Recall = TP / (TP + FN)
- F1 Score = 2 * (Precision * Recall) / (Precision + Recall)

Additional useful metrics:
- Detection count per photo
- Confidence distribution
- Processing time

## Output Format

Default output is the detailed metrics table view.

Example:
```
| Photo    | Expected | Detected | TP | FP | FN | Status |
|----------|----------|----------|----|----|----|--------|
| ae7dc104 | 600      | -        | 0  | 0  | 1  | MISS   |
| b54bd347 | 21,405   | 21,405   | 2  | 0  | 0  | PASS   |
...
Precision: 85.2%  Recall: 78.4%  F1: 81.6%
```

## Comparison Mode

Benchmarking should support comparing two configurations or runs.

Example:
```
Comparing: baseline vs clahe_pipeline

| Photo    | Baseline      | CLAHE         | Change |
|----------|---------------|---------------|--------|
| ae7dc104 | [] (miss)     | [600] (hit)   | +1 TP  |
| b54bd347 | [21,405]      | [21,405]      | no change |
...
Net change: +5 TP, -2 FP, +3 recall
```

## Data Layout

Benchmark data will live under `benchmarking/` and be referenced by the benchmark code. See `benchmarking/README.md` for concrete file layout and schemas.

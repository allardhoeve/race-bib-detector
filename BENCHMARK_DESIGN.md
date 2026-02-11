# Benchmark System Design

This document captures the design for the benchmark system: repeatable evaluation of the bib detection, face detection, and clustering pipeline against labeled reference data.

Project-wide conventions and invariants live in `STANDARDS.md`.

## Glossary

| Abbreviation | Meaning |
|---|---|
| GT | Ground truth — the human-labeled reference data |
| TP | True positive — a correct detection (prediction matches a GT box) |
| FP | False positive — a spurious detection (prediction without matching GT box) |
| FN | False negative — a missed detection (GT box without matching prediction) |
| IoU | Intersection over Union — overlap metric (0–1) for comparing two boxes |
| OCR | Optical character recognition — reading the bib number from a detected region |
| P / R / F1 | Precision / Recall / F1-score — standard detection quality metrics |

## Problem Statement

The current feedback loop is slow and expensive. Frequent parameter tuning across different backends and preprocessing options (e.g., CLAHE) increases micromanagement without guaranteed progress. Development needs to shift from "knob tweaking" to objective, repeatable evaluation.

Progress is measured by the scorecard, not by parameter changes. Improvements are accepted when the scorecard improves on the reference set without regressing critical metrics.

## Goals

- Make benchmark preparation repeatable and low-touch.
- Precompute "ghost labels" so the UI is fast.
- Separate bib and face labeling flows.
- Separate bib and face ground truth into independent files with independent freeze/staging lifecycles.
- Enable refresh/rebuild of the reference set.

## Pipeline Model

The benchmark evaluates three pipeline stages:

1. Detect bibs (localize bib boxes).
2. Detect faces (localize face boxes).
3. Link faces to bibs when possible.

Geometric priors (bibs sit below faces) belong in stage 3 as a pipeline heuristic, not in the ground truth. The benchmark stores bib-face links as plain facts so the pipeline can be evaluated on whether it discovers them.

## Ground Truth Schema

Split into two files with independent freeze/staging lifecycles (schema version 3):

- `bib_ground_truth.json` -- bib bounding boxes, bib numbers, bib tags, split assignment.
- `face_ground_truth.json` -- face bounding boxes, scope tags, identity labels.
- `suggestions.json` -- precomputed detection suggestions (ghost labels), separate from human labels. Each photo entry carries provenance metadata (backend, version, config).

The photo index remains shared (`photo_index.json`, photo identity via SHA256 content hash).

`face_count` is not stored; it is derived from the `keep`-scoped face box list.

Bounding box coordinates are normalised to `[0, 1]` image space. Legacy migrated entries have zero-area coordinates (`has_coords == False`) until boxes are drawn in the labeling UI.

### Bib Labels

- Bib labels: `bib`, `not_bib`, `bib_obscured` (real bib, too obscured to read — excluded from scoring), `bib_clipped` (readable but clipped at edge — scored).
- Allow manual bib box drawing with optional partial number entry (e.g., `62?` when `621` is obscured).
- Bib bounding boxes enable separating detection failure (region not found) from recognition failure (wrong OCR output).

### Face Labels

- Face labeling is manual-first: the user draws boxes for faces that should be recognized.
- Auto-detected faces appear as faint suggestion boxes to accept, adjust, or ignore.
- Scope tags: `keep` (should be recognized), `ignore` (blurry/obscured/background), `unknown`.
- No `maybe` tag -- it adds metric ambiguity without clear scoring semantics.
- Identity labels (person name/ID) per face, accumulated via the labeling UI.

### Bib-Face Associations

- Links between bibs and faces stored as plain facts in ground truth.
- Geometric priors belong in the pipeline, not the ground truth.
- Optional auto-suggestions for links to speed labeling.

### Identity Constraints

- Must-link / cannot-link constraints as hard ground truth (never overridden by clustering).
- Suggestion queues for likely matches based on similarity and proximity.

## Reference Set Lifecycle

### Concepts

- **Staging set:** mutable, for ongoing labeling before freezing.
- **Frozen sets:** immutable once frozen. Metrics stay comparable across runs because the dataset does not change.
- Multiple frozen sets can exist (e.g., `benchmark_v1`, `benchmark_v2`).
- Deduplication by photo hash. One copy per photo in benchmark storage.

### Workflow

1. Run `bnr benchmark prepare <path>` to copy photos from a local directory into the benchmark set. This deduplicates by content hash and runs ghost labeling (precomputed bib/face suggestions).
2. Use the labeling UI (`bnr benchmark ui`) to confirm or correct ghost labels. Bib and face labeling are separate flows.
3. Run benchmarks (`bnr benchmark run`) to evaluate the pipeline against labeled data.
4. *(Future)* Freeze into a named benchmark set when labeling is complete. Frozen sets are immutable.
5. *(Future)* If a label needs correction, update in the staging set and re-freeze as a new version.

`--refresh` re-runs ghost labeling on existing photos. `--reset-labels` clears human labels without removing photos. Refresh runs apply only to the mutable set; frozen sets (once implemented) remain immutable.

## Scorecard

Two scoring systems run in parallel:

**Number-based metrics** (works now, on all 225+ labeled photos):
- Set-intersection of expected vs detected bib numbers per photo.
- Precision, recall, F1, plus per-photo PASS/PARTIAL/MISS status.
- Baseline comparison with regression detection.

**IoU scorecard** (activates once GT boxes have coordinates, i.e. after Step 4 labeling):
- **Bib localization:** detection precision/recall using greedy IoU matching vs GT bib boxes.
- **Bib OCR:** accuracy conditioned on correct localization (exact string match on matched pairs).
- **Face detection:** precision/recall using IoU vs GT face boxes (scoped to `keep` only; `ignore`/`unknown` excluded).

Both scorecards are implemented in `benchmarking/scoring.py` (`BibScorecard`, `FaceScorecard`) and printed by `bnr benchmark run`.

### Future scorecard extensions

- **Bib-face linking:** link accuracy (correct pairings vs ground-truth links). Requires Step 5.
- **Face clustering:** pairwise F1 or NMI. Requires identity labels.
- **Retrieval quality:** percentage of "wanted images" found (top-k recall).

Every run is archived with metadata (timestamp, git commit, config, runtime, metrics) in `benchmarking/results/<run_id>/run.json`.

## CLI Commands

Implemented:

- `bnr benchmark prepare <path> [--refresh] [--reset-labels]`
  - Copies photos from a local directory into the benchmark folder (dedup by content hash).
  - Runs ghost labeling (face + bib suggestions) on new photos.
  - `--refresh` re-runs ghost labeling on all photos.
  - `--reset-labels` clears all human labels (keeps photos and GT entries).
- `bnr benchmark run [--full] [--note "..."]`
  - Runs detection on iteration split (default) or full split.
  - Prints number-based metrics and IoU scorecard.
  - Archives results to `benchmarking/results/<run_id>/run.json`.
- `bnr benchmark ui`
  - Opens the labeling + benchmark inspection web UI.
- `bnr benchmark list`
  - Shows saved benchmark runs with metrics summary.
- `bnr benchmark baseline [-f]`
  - Sets a run as the regression baseline.
- `bnr benchmark scan`
  - Rescans the photos directory and updates the index.
- `bnr benchmark stats`
  - Shows ground truth labeling statistics.
- `bnr benchmark clean [--keep-latest N] [--keep-baseline] [-f]`
  - Removes old benchmark runs.

Planned (deferred):

- `bnr benchmark freeze --name <name>`
  - Freezes the current staging set into a named immutable benchmark set.
- `bnr benchmark label faces` / `bnr benchmark label bibs`
  - Dedicated labeling commands (currently labeling is via `bnr benchmark ui`).

## Future Work

### Preset-Driven Execution

Define `fast` / `balanced` / `best` presets to reduce the configuration surface. The benchmark system enables this because presets can be validated by the scorecard.

### Experiment Harness (Agent-Driven Search)

Create an `experiments/` area for automated parameter searches. Harness runs bounded search across parameter combinations or alternative backends, reports top results by the scorecard. Must not modify production defaults or data.

## Resolved Questions

- **Storage:** Photos stay in `photos/`. Ground truth, suggestions, index, and run results all live under `benchmarking/`. Frozen sets (Step 1) will be named snapshots of the same data.
- **Scale:** Current set has 468 photos (225 labeled). Sufficient for the milestone; `bnr benchmark prepare` makes it easy to grow.

## Open Questions

- **Identity bootstrap:** Identity labels don't exist yet. The plan is to accumulate them via the face labeling UI. Is a dedicated identity labeling pass needed?
- **CI integration:** Should `bnr benchmark run` gate PRs, or is it advisory-only?
- **Frozen set naming:** Frozen sets should have explicit human-readable names (e.g. `benchmark_v1`, `clubkamp_2024`). Exact on-disk layout TBD in Step 1.

# Benchmark System Design

This document captures the design for the benchmark system: repeatable evaluation of the bib detection, face detection, and clustering pipeline against labeled reference data.

Project-wide conventions and invariants live in `STANDARDS.md`.

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

Split into two files with independent freeze/staging lifecycles:

- `bib_ground_truth.json` -- bib bounding boxes, bib numbers, bib tags.
- `face_ground_truth.json` -- face bounding boxes, scope tags, identity labels.

The photo index remains shared (photo identity via content hash).

`face_count` is not stored; it is derived from the `keep`-scoped face box list.

### Bib Labels

- Bib labels: `bib`, `not bib`, `bib partial` (visible but incomplete number).
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

1. Mark an album as part of the test suite. Copy photos into the reference set and run ghost labeling (precomputed bib/face suggestions).
2. Use the labeling UI to confirm or correct ghost labels. Bib and face labeling are separate flows.
3. Freeze staging into a named benchmark set when labeling is complete.
4. Run benchmarks against frozen sets.
5. If a label needs correction, move the photo back to staging, relabel, and re-freeze as a new version.

Refresh runs apply only to staging; frozen sets remain immutable.

## Scorecard

### Phase 1 (boxes + links -- no identity labels required)

- **Bib localization:** detection precision/recall using IoU vs ground-truth bib boxes.
- **Bib OCR:** accuracy conditioned on correct localization (exact and partial handling).
- **Face detection:** precision/recall using IoU vs ground-truth face boxes (scoped to `keep`).
- **Bib-face linking:** link accuracy (correct pairings vs ground-truth links).

### Phase 2 (activates once identity labels exist)

- **Face clustering:** pairwise F1 or NMI.
- **Retrieval quality:** percentage of "wanted images" found (and top-k recall).

Every run is archived with metadata: timestamp, git commit hash, config, runtime, and metrics.

## CLI Commands

- `bnr benchmark prepare [--album <id>] [--refresh] [--reset-labels]`
  - Copies photos into the benchmark folder.
  - Runs ghost labeling (face + bib suggestions).
  - Writes or updates the staging set metadata.
- `bnr benchmark freeze --name <name>`
  - Freezes the current staging set into an immutable benchmark set version.
- `bnr benchmark label faces`
  - Opens the face labeling UI with faint suggestions and face scope tags.
- `bnr benchmark label bibs`
  - Opens the bib labeling UI.
- `bnr benchmark run [--set <name>|--all] [--split iteration|full]`
  - Runs metrics and writes a scorecard artifact.
- `bnr benchmark list`
  - Shows frozen sets and run history.

## Future Work

### Preset-Driven Execution

Define `fast` / `balanced` / `best` presets to reduce the configuration surface. The benchmark system enables this because presets can be validated by the scorecard.

### Experiment Harness (Agent-Driven Search)

Create an `experiments/` area for automated parameter searches. Harness runs bounded search across parameter combinations or alternative backends, reports top results by the scorecard. Must not modify production defaults or data.

## Open Questions

- **Storage:** Where do frozen benchmark sets live? Git LFS? A separate directory? The current `photos/` folder?
- **Scale:** The architecture targets 200-1000 images. Is the current set sufficient?
- **Identity bootstrap:** Identity labels don't exist yet. The plan is to accumulate them via the face labeling UI. Is a dedicated identity labeling pass needed?
- **CI integration:** Should `bnr benchmark run` gate PRs, or is it advisory-only?

# Benchmark System Design

This document captures the design for the benchmark system: repeatable evaluation of the bib detection, face detection, and clustering pipeline against labeled reference data.

Project-wide conventions and invariants live in `STANDARDS.md`.
UI layout and keyboard conventions live in `BENCHMARK_UI_DESIGN.md`.

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
- Scope tags: `keep` (should be recognized), `exclude` (blurry/obscured/background), `uncertain` (labeler unsure).
- Backward compat: old `ignore`→`exclude`, `unknown`→`uncertain` via `_FACE_SCOPE_COMPAT`.
- No `maybe` tag -- it adds metric ambiguity without clear scoring semantics.
- Per-box tags: `tiny`, `blurry`, `occluded`, `profile`, `looking_down`.
- Per-photo tags: `no_faces`, `light_faces`.
- Identity labels (person name/ID) per face, accumulated via the labeling UI. Currently 137 named + 7 anonymous identities in `face_identities.json`.

### Bib-Face Associations

- Links stored in `bib_face_links.json` as index pairs `[bib_index, face_index]`
  referencing positions in the photo's `bib_label.boxes` and `face_label.boxes` lists.
- Geometric priors belong in the pipeline, not the ground truth.
- Saving an empty list (`[]`) explicitly marks a photo as processed with no links.
- Optional auto-suggestions for links to speed labeling (not yet implemented).

### Identity Constraints *(future)*

- Must-link / cannot-link constraints as hard ground truth (never overridden by clustering).
- Suggestion queues for likely matches based on similarity and proximity.
- Not yet implemented; tracked as future work.

## Reference Set Lifecycle

### Concepts

- **Staging set:** mutable, for ongoing labeling before freezing.
- **Frozen sets:** immutable once frozen. Metrics stay comparable across runs because the dataset does not change.
- Multiple frozen sets can exist (e.g., `benchmark_v1`, `benchmark_v2`).
- Deduplication by photo hash. One copy per photo in benchmark storage.

### Workflow

1. Run `bnr benchmark prepare <path>` to copy photos from a local directory into the benchmark set. This deduplicates by content hash and runs ghost labeling (precomputed bib/face suggestions).
2. Use the labeling UI (`bnr benchmark ui`) to confirm or correct ghost labels. Three independent steps:
   - **Bib labeling** (`/labels/`): draw bib boxes, assign scopes, assign split.
   - **Face labeling** (`/faces/labels/`): draw face boxes, assign scopes and identity.
   - **Link labeling** (`/links/`): associate each bib box with the face of its wearer. Only available for photos with both bib and face labels.
3. Review completeness at `/staging/`. Photos are complete when all three dimensions are labeled (or trivially N/A — see Completeness below).
4. Freeze into a named snapshot: `bnr benchmark freeze --name <name>` or via `POST /api/freeze` in the web UI. Frozen sets are immutable.
5. Run benchmarks (`bnr benchmark run`) to evaluate the pipeline against labeled data.
6. If a label needs correction, update in the staging set and re-freeze as a new version.

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
- **Face detection:** precision/recall using IoU vs GT face boxes (scoped to `keep` only; `exclude`/`uncertain` excluded).

All scorecards are implemented in `benchmarking/scoring.py` and printed by `bnr benchmark run`.

**Link scorecard** (`LinkScorecard`): implemented in `scoring.py`, stub in `runner.py`.
A predicted pair `(bib_box, face_box)` is TP only if both boxes match GT boxes at
IoU ≥ threshold and the GT link between those indices exists. Currently TP/FP = 0 because
the detection pipeline does not yet output link predictions.

### Future scorecard extensions

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

- `bnr benchmark freeze --name <name> [--all] [--include-incomplete]`
  - Freezes labeled photos into a named immutable snapshot.
  - Default: only photos that are complete or known-negative.
  - `--all`: freeze every photo in the index regardless of labeling status.
  - `--include-incomplete`: include partially-labeled photos with a warning.
- `bnr benchmark frozen-list`
  - Lists all frozen snapshots with metadata.

## Future Work

### Preset-Driven Execution

Define `fast` / `balanced` / `best` presets to reduce the configuration surface. The benchmark system enables this because presets can be validated by the scorecard.

### Experiment Harness (Agent-Driven Search)

Create an `experiments/` area for automated parameter searches. Harness runs bounded search across parameter combinations or alternative backends, reports top results by the scorecard. Must not modify production defaults or data.

## Completeness Model

Completeness is **derived at query time** — no separate JSON file, no staleness risk.
Implemented in `benchmarking/completeness.py`.

A photo is complete when all three dimensions are done:

| Dimension | "Done" definition |
|---|---|
| `bib_labeled` | `bib_label.labeled == True` |
| `face_labeled` | `is_face_labeled(label)` — boxes or tags present |
| `links_labeled` | `content_hash in link_gt.photos`, OR trivially True when `bib_box_count == 0` or `face_box_count == 0` |

**Known negative:** both `bib_labeled` and `face_labeled` are True, and both box counts
are 0. No link step is needed. Counts as complete and is visually distinguished from
"Ready" in the staging UI.

The staging page (`/staging/`) shows all touched photos with their completeness status
and a freeze form. `POST /api/freeze` creates a named snapshot from selected hashes.

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Completeness derived at query time | No separate JSON | Avoids staleness; GT files are the single source of truth |
| `links_labeled` trivially True when 0 boxes | Shortcut | No link step needed if one dimension has no boxes |
| Known negatives counted as complete | Yes | Correctly labeled with 0 boxes is not an error; distinguished from Ready in staging UI |
| CLI freeze default | Complete + known-negative photos only | Prevents accidentally freezing unlabeled data; `--include-incomplete` available as escape hatch |
| Link GT format | Index pairs `[bib_index, face_index]` | Simple, compact; indices reference the GT box list directly |
| Blueprint ownership | `routes_bib.py` owns link routes | Links are created during bib labeling; no separate blueprint needed |
| `not_bib` / `bib_obscured` excluded from scoring | `_BIB_BOX_UNSCORED = {"not_bib", "bib_obscured"}` | These regions are not valid detection targets; including them would inflate FN count |
| Geometric priors not in GT | Pipeline responsibility | GT stores plain facts; the pipeline decides how to use spatial relationships |
| Face scope compat mapping | `ignore`→`exclude`, `unknown`→`uncertain` | Preserves older labeled data without a migration script |

## Resolved Questions

- **Storage:** Photos stay in `photos/`. Ground truth, suggestions, index, and run results all live under `benchmarking/`. Frozen sets (Step 1) will be named snapshots of the same data.
- **Scale:** Current set has 468 photos (225 labeled). Sufficient for the milestone; `bnr benchmark prepare` makes it easy to grow.
- **Identity bootstrap:** Identities are accumulated via the face labeling UI with embedding-based suggestions. Currently 137 named + 7 anonymous identities. No dedicated identity labeling pass needed.

## Open Questions

- **CI integration:** Should `bnr benchmark run` gate PRs, or is it advisory-only?
- **Link suggestions:** Auto-suggest likely bib-face pairs (e.g. bibs below faces, spatial proximity) to speed link labeling. Not yet implemented.
- **Frozen set use in runner:** `run_benchmark()` currently runs against the full staging set. Using a named frozen set as input is deferred.

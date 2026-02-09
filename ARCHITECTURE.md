# Architecture and Product Direction

This document captures the results-based development approach for the photo ingest, bib detection, face detection, and clustering system. It is intended to reduce tuning churn, shorten feedback loops, and improve measurable outcomes while preserving code quality.

Project-wide conventions and invariants live in `STANDARDS.md`. This document does not restate those rules; it references them where relevant.

## Current Pipeline (Baseline)

- Ingest: photos are saved locally, then scanned with `bnr`.
- Bib detection: candidate bibs are detected, extracted, and numbers are recognized and stored.
- Face detection: faces are detected and saved, with notable false positives and false negatives.
- Clustering: faces are clustered and associated with numbers.
- Tagging/measurement: tagging and evaluation drive progress toward “wanted images.”

## Problem Statement

The current feedback loop is slow and expensive. Frequent parameter tuning across different backends and preprocessing options (e.g., CLAHE) increases micromanagement without guaranteed progress. Development needs to shift from “knob tweaking” to objective, repeatable evaluation.

## Results-Based Development Strategy

### 1) Golden Reference Set

Create and maintain a small, high-signal benchmark set (e.g., 200–1000 images) with:

- Face bounding boxes.
- Identity labels or cluster IDs.
- Bib bounding boxes and bib numbers.
- Known-hard cases and known-bad cases.

This set becomes the primary compass for pipeline changes. It must be versioned and remain stable so results can be compared over time. The intended model is multiple frozen benchmark sets that can be added over time (e.g., `benchmark_v1`, `benchmark_v2`). Each set is immutable once frozen; if a label needs to change, move the image into a new (not-yet-frozen) set and create a new frozen set version. This keeps comparisons fair even when newer photos have no historical benchmark runs.

#### Snapshot vs Living Sets (Concepts)

- Frozen snapshots are immutable: metrics stay comparable across runs because the dataset does not change.
- Living sets evolve: they reflect the latest reality, but scores can drift when labels or photos change.
- The recommended hybrid is to keep a living “staging” set for ongoing labeling, then freeze it into a new benchmark set version when it is stable.
- If a frozen label is corrected, move that image to the staging set and re-freeze as a new version.
- Staging is explicit: it is the only mutable set. Frozen benchmark sets are read-only and used for comparisons.
- Deduplication is by photo hash. Only one copy of a photo exists in benchmark storage; relabeling requires moving the photo back to staging.
- Relabeling should be accessible from the UI: a “move to staging” action that removes the photo from the frozen set, re-adds it to staging, and re-runs ghost labeling.

#### Reference Set Workflow

The intended flow for building and maintaining the reference set is:

1. Mark an album as part of the test suite. The system copies the photos into the reference set and runs a “ghost labeling” pass (precomputed bib/face suggestions).
2. Use the labeling UI to confirm or correct the ghost labels. Bib and face labeling are separate flows because the UI affordances differ.
3. Run benchmarks against the completed reference set.
4. Support re-running the entire process to refresh the reference set (e.g., after model changes or new album additions) via a command like `bnr benchmark prepare --refresh`.

To keep labeling fast, precompute suggestion boxes during reference set ingestion and cache them for the UI. If suggestions are missing for a photo, compute them asynchronously and update the UI when they are ready. Refresh runs apply only to staging; frozen benchmark sets remain immutable.

### Requirements (Labeling and Workflow)

The reference set must reflect “faces that matter,” not every background face. The workflow should prioritize fast human labeling, with automatic suggestions as a helper layer.

- Face labeling should be manual-first: the user draws face boxes for the faces that should be recognized.
- Auto-detected faces appear as faint suggestion boxes that can be accepted, adjusted, or ignored.
- Each face label supports a scope tag: `keep` (should be recognized), `ignore` (blurry/obscured/background), or `unknown`.
- Metrics should treat `ignore` as out-of-scope to reduce “partial” hit noise.

Cluster refinement is required to correct identity grouping over time:

- Provide a way to link or separate faces (same person vs different person).
- Support suggestion queues for likely matches based on similarity and proximity.
- Store must-link / cannot-link constraints as hard ground-truth (never overridden by clustering). If the definition of “acceptable misses” shifts over time, treat that as a new labeling policy and freeze a new benchmark set version.

#### Hard vs Soft Constraints (Concepts)

- Hard constraints are absolute: a must-link or cannot-link is never violated by clustering.
- Soft constraints are guidance: the algorithm can override them if similarity is extremely strong.
- For this system, constraints are hard ground-truth so manual corrections never get undone.

Bib labeling should support ambiguity and linkage to faces:

- Bib labels: `bib`, `not bib`, `bib partial` (visible but incomplete number).
- Allow manual bib box drawing, with optional partial number entry.
- Allow linking a bib to a face; enforce the geometric prior that bibs sit below faces with a configurable skew.



### 2) Fixed Metrics and Scorecard

Define a minimal set of hard metrics and produce them for every run:

- Face detection: precision/recall or F1.
- Face clustering: pairwise F1 or NMI.
- Retrieval quality: percentage of “wanted images” found (and top-k recall when relevant).

Every run should output a stable “scorecard” artifact. This scorecard is the first thing reviewed when deciding whether changes are an improvement.

### 3) Preset-Driven Execution

Reduce the configuration surface by defining a small number of presets, for example:

- `fast`: fastest acceptable quality.
- `balanced`: default.
- `best`: highest quality.

Most work should occur inside these presets. Avoid exposing every parameter in regular iteration.

### 4) Automated Evaluation Loop

Provide a single command that runs:

- Ingest subset.
- Run pipeline end-to-end.
- Evaluate metrics.
- Produce scorecard.

Outputs should be archived with metadata (timestamp, git commit hash, preset/config, runtime, and metrics).

### 5) Agent-Driven Search

Create an experiment harness that can run bounded search across parameter combinations or alternative backends, then report top results by the scorecard. The agent should only surface the top candidates and should not modify production defaults or data.

## Data and Traceability

All results must be traceable to inputs and settings. Follow the logging and traceability guidance in `STANDARDS.md`.

## Quality Guardrails

- Use `config.py` for all tunables.
- Preserve idempotency when re-running scans.
- Keep sensitive data local.

(See `STANDARDS.md` for required details.)

## Suggested Next Steps

- Define the golden reference set schema and storage location.
- Implement the first scorecard output format.
- Add a simple `evaluate` CLI command to compute metrics for the golden set.
- Create an `experiments/` area for automated parameter searches.

## Design Concerns and Open Questions

The following concerns were raised during review and should be addressed as the benchmark system evolves.

### Incremental migration, not greenfield

A working benchmark pipeline already exists: `ground_truth.json`, `photo_index.json`, a labeling web UI, `bnr benchmark run`, baseline tracking, and multiple saved runs. The new benchmark flow should build on this foundation rather than replace it. As a first step, freeze the current ground truth as `benchmark_v1` so that all future work has a comparable baseline from day one.

### Separate bib and face ground truth

Bib and face evaluation are at different maturity levels, have different labeling cadences, use different scoring logic, and target different tuning parameters. Coupling them into one `PhotoLabel` forces one domain to wait for the other and requires workaround flags like `bib_labeled`.

**Decision:** Split ground truth into two files with independent freeze/staging lifecycles:

- `bib_ground_truth.json` — bib numbers, bib tags, bib bounding boxes.
- `face_ground_truth.json` — face bounding boxes, scope tags, identity labels.

The photo index remains shared (one photo identity via content hash). The unified scorecard reports both domains as separate sections so improvements and regressions are visible per domain.

### Bib localization + number matching are both required

The current bib benchmark compares expected numbers against detected numbers as flat sets. This collapses two distinct failure modes into one score:

1. **Detection failure** — the bib region was not found at all.
2. **Recognition failure** — the region was found but OCR produced the wrong number (e.g., "62" instead of "621" because the bib was split by a hand or crease).

Number-only comparison scores both cases identically as a miss. With bib bounding boxes in the ground truth, evaluation can separate these:

- **Detection recall (IoU):** did a predicted box overlap the ground-truth bib region?
- **Recognition accuracy:** given a correct detection, did OCR produce the right number?

This properly handles `bib partial` cases — the bib region is present and should be detected, but the full number may not be readable. It also surfaces whether tuning efforts should focus on the region detector or the OCR stage. Bibs must therefore be visually labeled so benchmarks can answer “was the bib found at the right location” in addition to “was the number read correctly.”

### Face count is derived, not stored

Once face ground truth contains bounding boxes with scope tags (`keep` / `ignore` / `unknown`), face count is simply the length of the `keep`-scoped box list. There is no need to store `face_count` as a separate field. The current `face_count` integer exists only because bounding box data does not exist yet; it should be removed when face bounding boxes are implemented.

### Face count alone is insufficient for detection metrics

A count-based face metric (expected N, detected N) cannot distinguish true positives from false positives. If the detector finds two artifacts instead of two real faces, count says 2/2 = perfect. Meaningful face detection evaluation requires spatial matching: ground-truth bounding boxes compared against predicted boxes using IoU, so that precision and recall reflect whether the *correct* faces were found. Face bounding box labeling is therefore not optional — it is a prerequisite for valid face detection metrics.

### Drop the `maybe` face scope tag

The `keep` / `ignore` / `unknown` scope tags cover the required space. Adding `maybe` introduces ambiguity in a system whose purpose is to be definitive. How should a detection of a `maybe` face be scored? If it cannot be clearly answered, the tag will add noise to metrics rather than signal.

### Separate geometric priors from ground truth

Bib-face linking is a pipeline concern: (1) detect bibs, (2) detect faces, (3) link faces to bibs when possible. Geometric priors (bibs are below faces) belong in step 3 as a heuristic, not in the ground truth. In the benchmark, store bib-face links as plain facts so the pipeline can be evaluated on whether it discovers them, including cases where the geometric assumption doesn't hold.

### Open questions to resolve

- **Storage:** Where do frozen benchmark sets live? Git LFS? A separate directory? The current `photos/` folder?
- **Scale:** The architecture targets 200–1000 images. How large is the current ground truth set, and is it sufficient?
- **Migration:** How do existing labels in `ground_truth.json` map to the new schema (staging, frozen sets, face bounding boxes)?
- **Identity bootstrap:** The architecture mentions identity labels for clustering evaluation, but current ground truth has no identity data. What is the plan to bootstrap this?
- **CI integration:** Should `bnr benchmark run` gate PRs, or is it advisory-only?

## Success Definition

Progress is measured by the scorecard, not by parameter changes. Improvements are accepted when the scorecard improves on the golden reference set without regressing critical metrics.

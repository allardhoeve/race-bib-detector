# New Benchmark Flow TODO

## Goals

- Make benchmark preparation repeatable and low-touch.
- Precompute "ghost labels" so the UI is fast.
- Separate bib and face labeling flows.
- Separate bib and face ground truth into independent files with independent freeze/staging lifecycles.
- Enable refresh/rebuild of the reference set.

## Proposed Steps

### 0. Delete old benchmarks and start fresh

- Delete existing `ground_truth.json`, old benchmark data, and old benchmark cache files.
- The new staging/sets structure replaces the old flat layout.
- Start fresh with the new schema:
  - `bib_ground_truth.json` — bib bounding boxes, bib numbers, bib tags.
  - `face_ground_truth.json` — face bounding boxes, scope tags, identity labels.
- The photo index remains shared (photo identity via content hash).
- `face_count` is not carried forward; it is derived from the `keep`-scoped face box list.
- Tagging a fresh set takes ~5 minutes, so migration complexity is not justified.

### 1. Define reference set selection

- Store benchmark album selection in the DB (single benchmark set for now).
- Use multiple frozen benchmark sets that can be added over time (immutable once frozen).
- Maintain an explicit staging set (mutable) for ongoing labeling before freezing.
- If a label needs to change, move the image into staging and re-freeze as a new version.

### 2. Implement preparation command

- Add a CLI command for preparation, e.g. `bnr benchmark prepare`.
- Inputs: default to the single benchmark album (explicit album ID optional).
- Outputs: copied photos into a dedicated benchmark folder, cached suggestion boxes, metadata for UI.
- Dedup policy: single copy per photo hash; photo hash is the identity.
- If a photo needs relabeling, remove it from a frozen set and re-add to staging.

### 3. Ghost labeling pass

- Precompute face and bib suggestions during preparation.
- Persist suggestion boxes and provenance metadata (backend, version, config).

### 4. Labeling UI flows

- Separate bib labeling and face labeling UI paths.
- Face labeling: manual-first boxes with faint suggestions to accept/adjust/ignore.
- Face scope tags: `keep` / `ignore` / `unknown` (no `maybe` — it adds metric ambiguity).
- Support identity assignment per face (person name/ID) from the start, so clustering data accumulates naturally.
- Bib labeling: manual boxes with `bib` / `not bib` / `bib partial` labels.
- Allow partial bib digits to be captured (e.g., `62?` when `621` is obscured).

### 5. Association + constraints

- Allow linking bibs to faces as plain facts in ground truth.
- Geometric priors (bibs sit below faces) belong in the pipeline, not in the ground truth. The benchmark evaluates whether the pipeline discovers correct links.
- Provide optional auto-suggestions for links to speed labeling.
- Store face identity constraints (must-link / cannot-link) as hard ground-truth.

### 6. Benchmark evaluation

- Define scorecard output format.
- Add CLI command to run metrics against the reference set.
- Add localization metrics (IoU-based bib detection + OCR accuracy).
- Archive every run with metadata: timestamp, git commit hash, config, runtime, and metrics.

### 7. Refresh workflow

- Add a refresh command, e.g. `bnr benchmark prepare --refresh`.
- Preserve existing labels by default, allow `--reset-labels`.
- Re-run ghost labeling for all photos on refresh (explicit request).
- Refresh only updates staging; frozen sets remain immutable.
- Provide a UI action to move a photo from a frozen set back into staging for relabeling.

### 8. Experiment harness (agent-driven search)

- Create an `experiments/` area for automated parameter searches.
- Harness runs bounded search across parameter combinations or alternative backends.
- Reports top results by the scorecard.
- Must not modify production defaults or data.

## Pipeline Model (for benchmarking)

1. Detect bibs (localize bib boxes).
2. Detect faces (localize face boxes).
3. Link faces to bibs when possible (geometric priors belong here, not in ground truth).

## Scorecard Sections

### Phase 1 (boxes + links — no identity labels required)

- Bib localization: detection precision/recall using IoU vs ground-truth bib boxes.
- Bib OCR: accuracy conditioned on correct localization (exact and partial handling).
- Face detection: precision/recall using IoU vs ground-truth face boxes (scoped to `keep`).
- Bib-face linking: link accuracy (correct pairings vs ground truth links).

### Phase 2 (activates once identity labels exist)

- Face clustering: pairwise F1 or NMI.
- Retrieval quality: percentage of "wanted images" found (and top-k recall).

## Follow-up Goals (after benchmark system is working)

- **Preset-driven execution**: Define `fast` / `balanced` / `best` presets to reduce the configuration surface. The benchmark system enables this because presets can be validated by the scorecard.

## Command Drafts (bnr -> benchmarking.cli)

- `bnr benchmark prepare [--album <id>] [--refresh] [--reset-labels]`
  - Copies photos into the benchmark folder.
  - Runs ghost labeling (face + bib suggestions).
  - Writes or updates the staging set metadata.
- `bnr benchmark freeze --name <name>`
  - Freezes the current staging set into an immutable benchmark set version.
- `bnr benchmark label faces`
  - Opens the face labeling UI with faint suggestions and face scope tags.
- `bnr benchmark label bibs`
  - Opens the bib labeling UI with `bib` / `not bib` / `bib partial` labels.
- `bnr benchmark run [--set <name>|--all] [--split iteration|full]`
  - Runs metrics and writes a scorecard artifact.
  - Archives results with metadata (timestamp, git hash, config, runtime).
- `bnr benchmark list`
  - Shows frozen sets and run history.

## Open Questions

- **Storage:** Where do frozen benchmark sets live? Git LFS? A separate directory? The current `photos/` folder?
- **Scale:** The architecture targets 200–1000 images. Is the current set sufficient?
- **Identity bootstrap:** Identity labels for clustering evaluation don't exist yet. The plan is to accumulate them via the face labeling UI (step 4). Is this sufficient or do we need a dedicated identity labeling pass?
- **CI integration:** Should `bnr benchmark run` gate PRs, or is it advisory-only?

# Benchmark TODO

Design rationale: see `BENCHMARK_DESIGN.md`.

## Milestone: labeling UI + first scorecard

Critical path: **0 → 2 → 3 → 4**, with **0.5** running in parallel after step 0.

Step 1 (staging/frozen sets) is deferred — not needed for labeling or scoring.

---

## Step 0: Delete old ground truth, create new schema

- [x] Delete `benchmarking/ground_truth.json`
- [x] Delete `benchmarking/baseline.json`
- [x] Remove `PhotoLabel` and `GroundTruth` classes from `benchmarking/ground_truth.py`
- [x] Define `BibGroundTruth` schema (photo hash -> bib boxes, bib numbers, bib tags)
- [x] Define `FaceGroundTruth` schema (photo hash -> face boxes, scope tags, identity labels)
- [x] Write `bib_ground_truth.json` and `face_ground_truth.json` (migrated from legacy data)
- [x] Remove `face_count` field (derived from `keep`-scoped face boxes going forward)
- [x] Update `benchmarking/cli.py` to load/save the new schemas
- [x] Update `benchmarking/web_app.py` to use new schemas

## Step 0.5: First scorecard (parallel track, start after step 0)

Minimal scoring against the new schema so labeling effort pays off immediately.
Number-based metrics work now on all labeled photos. IoU scorecard activates
once GT boxes have coordinates (drawn in step 4 labeling UI).

- [x] Add `compute_iou(box_a, box_b)` utility
- [x] Add `match_boxes(predicted, ground_truth, iou_threshold=0.5)` — greedy IoU matching, returns TP/FP/FN
- [x] Bib scorecard: detection precision/recall (IoU) + OCR accuracy on matched boxes
- [x] Face scorecard: detection precision/recall (IoU), scoped to `keep` boxes
- [x] Wire into `bnr benchmark run` so it works with the new ground truth files
- [x] Print scorecard summary to terminal (no archive/metadata yet — that's step 6)

## Step 2: Prepare command

- [x] Implement `bnr benchmark prepare <path>` (accepts source directory)
  - [x] Copy photos from source into benchmark folder (dedup by hash)
  - [x] Build/update photo index for benchmark photos
  - [x] Run ghost labeling (step 3) on all new photos
- [x] Implement `--refresh` flag (re-run ghost labeling on existing photos)
- [x] Implement `--reset-labels` flag (clear labels, keep photos)

## Step 3: Ghost labeling

- [x] Run face detection on each benchmark photo, save suggestion boxes
- [x] Run bib detection on each benchmark photo, save suggestion boxes
- [x] Store provenance metadata per suggestion (backend, version, config)
- [x] Persist suggestions alongside ground truth (separate from human labels)

## Step 3.9: Cleanup (tests)

- [ ] Remove dataclass/accessor-only tests in `tests/test_photo.py`, keeping behavior like `get_paths` errors.
- [ ] Prune round-trip and field-mirroring tests in `tests/test_ground_truth.py`, keeping tag/split validation and `bib_numbers_int` logic.
- [ ] Trim `tests/test_ghost.py` to store semantics and one serialization snapshot; drop per-dataclass accessor tests.
- [ ] Simplify `tests/test_bib_detection.py` by keeping `scale_bbox` and `from_dict` compat checks, dropping basic constructor/accessor tests.
- [ ] Reduce `tests/test_preprocessing.py` property alias checks to conditional behavior only (e.g., `resized` when scaled).

## Step 4: Labeling UI

Depends on steps 0, 2, 3.

### Shared: canvas box drawing

- [ ] Add HTML5 canvas overlay on photo for click-drag rectangle drawing
- [ ] Support resize handles (drag corners/edges to adjust existing boxes)
- [ ] Support delete (click box + Delete key or X button)
- [ ] Show ghost suggestions as dashed outlines; click to accept (turns solid), drag to adjust
- [ ] Keyboard shortcut to cycle through unreviewed ghost suggestions

### Face labeling (`bnr benchmark label faces`)

- [ ] Render accepted face boxes as solid outlines with scope tag badge
- [ ] Scope tag selector per box: `keep` / `ignore` / `unknown` (default `keep`)
- [ ] Identity dropdown per face box: autocomplete from previously entered identities
- [ ] Allow adding new identity (free-text) that gets added to the known list
- [ ] Store identity list in a persistent file (e.g., `face_identities.json`)
- [ ] Show identity name on box label when assigned

### Bib labeling (`bnr benchmark label bibs`)

- [ ] Same canvas box drawing as face labeling
- [ ] Label selector per box: `bib` / `not bib` / `bib partial`
- [ ] Number input field per bib box (supports `?` for unreadable digits, e.g., `62?`)
- [ ] Show bib number on box label when entered

---

## Deferred (after milestone)

### Step 1: Staging and frozen sets

- [ ] Define on-disk layout for staging set and frozen sets
- [ ] Add `StagingSet` and `FrozenSet` data structures
- [ ] Implement `bnr benchmark freeze --name <name>`
- [ ] Implement `bnr benchmark list` (frozen sets + run history)

### Step 5: Bib-face associations

### Step 6: Full scorecard with archiving

- [x] Archive every run with metadata (timestamp, git hash, config, runtime) *(already works — runner saves to results/\<run_id\>/run.json)*
- [x] Baseline comparison (regression detection) *(already works — `bnr benchmark baseline` + compare_to_baseline)*
- [ ] Bib-face link accuracy metric *(requires step 5)*

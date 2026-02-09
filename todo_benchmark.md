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
Even 10 hand-labeled photos give useful signal.

- [ ] Add `compute_iou(box_a, box_b)` utility 
- [ ] Add `match_boxes(predicted, ground_truth, iou_threshold=0.5)` — greedy IoU matching, returns TP/FP/FN
- [ ] Bib scorecard: detection precision/recall (IoU) + OCR accuracy on matched boxes
- [ ] Face scorecard: detection precision/recall (IoU), scoped to `keep` boxes
- [ ] Wire into `bnr benchmark run` so it works with the new ground truth files
- [ ] Print scorecard summary to terminal (no archive/metadata yet — that's step 6)

## Step 2: Prepare command

- [ ] Implement `bnr benchmark prepare [--album <id>]`
  - [ ] Copy photos from album into benchmark folder (dedup by hash)
  - [ ] Build/update photo index for benchmark photos
  - [ ] Run ghost labeling (step 3) on all new photos
- [ ] Implement `--refresh` flag (re-run ghost labeling on existing photos)
- [ ] Implement `--reset-labels` flag (clear labels, keep photos)

## Step 3: Ghost labeling

- [ ] Run face detection on each benchmark photo, save suggestion boxes
- [ ] Run bib detection on each benchmark photo, save suggestion boxes
- [ ] Store provenance metadata per suggestion (backend, version, config)
- [ ] Persist suggestions alongside ground truth (separate from human labels)

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

- [ ] Archive every run with metadata (timestamp, git hash, config, runtime)
- [ ] Baseline comparison (regression detection)
- [ ] Bib-face link accuracy metric

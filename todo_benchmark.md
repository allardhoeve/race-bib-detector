# Benchmark TODO

Design rationale: see `docs/BENCHMARK_DESIGN.md`. Tasks: see `todo/tasks/`.

---

## Completed milestone: labeling UI + first scorecard

Steps 0 → 0.5 → 2 → 3 → 3.9 → 4 are **done**. Summary:

- **Step 0**: New GT schema (v3) — split into `bib_ground_truth.json` + `face_ground_truth.json`, 468 photos migrated.
- **Step 0.5**: IoU scorecard — `compute_iou`, `match_boxes`, `BibScorecard`, `FaceScorecard` in `scoring.py`.
- **Step 2**: `bnr benchmark prepare <path>` — photo import with dedup, ghost labeling, `--refresh`/`--reset-labels`.
- **Step 3**: Ghost labeling — precomputed bib/face suggestions with provenance metadata.
- **Step 3.9**: Test cleanup — pruned trivial tests; 245 tests pass.
- **Step 4**: Canvas-based labeling UI — box drawing, resize, delete, ghost suggestion acceptance, face scopes/identities, bib scopes/numbers.

### Architecture patterns (reference for future steps)

- **JS split**: `LabelingCore` (pure logic) vs `LabelingUI` (DOM/canvas). New interactions should follow this split.
- **API convention**: `PUT /api/{bib,face}_boxes/<hash>` saves full box list per photo. Step 5 should add `PUT /api/bib_face_links/<hash>`.
- **Ghost suggestion filtering**: IoU > 0.3 against existing boxes → hidden. Tab cycles unreviewed.

---

## Deferred work

### Step 1: Staging and frozen sets

- [ ] Define on-disk layout for staging set and frozen sets
- [ ] Add `StagingSet` and `FrozenSet` data structures
- [ ] Implement `bnr benchmark freeze --name <name>`

### Step 5: Bib-face associations

Open questions (decide before implementation):

- **GT representation**: how to store links — list of `(bib_index, face_index)` pairs per photo? Separate JSON file or nested inside existing GT?
- **Labeling UX**: how to draw links in the canvas — click bib then click face? Drag a line? Show both box types simultaneously?
- **Scoring**: match predicted links against GT links. Define what counts as a correct link (both boxes matched by IoU + correct pairing).
- **Design note**: links are pure associations, not spatial rules. Geometric priors belong in the pipeline.

Tasks:

- [ ] Design GT representation for bib-face links
- [ ] Add link drawing interaction to labeling UI
- [ ] Add link scorecard (TP/FP/FN on `(bib_box, face_box)` pairs)
- [ ] Wire link scoring into `bnr benchmark run`

### Step 6: Full scorecard with archiving

- [x] Archive every run with metadata *(already works — `results/<run_id>/run.json`)*
- [x] Baseline comparison with regression detection *(already works — `bnr benchmark baseline`)*
- [ ] Bib-face link accuracy metric *(requires step 5)*

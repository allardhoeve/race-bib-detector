# Facial Recognition Plan (Preliminary)

Date: 2026-02-06

## Goals
- Support local-only face detection and grouping for photos with missing/obscured bibs.
- Allow browsing photos by person clusters and by bibs.
- Autolink person clusters to bibs when confidence is high and evidence is traceable.
- Prioritize fewer false negatives (avoid missing matches), with later correction/learning paths.

## Non-Goals (Initial)
- No automatic training from user corrections (yet).
- No fully automated multi-person bib attribution (start conservative).

## Constraints / Assumptions
- No cloud services or external APIs.
- Photo identification follows `STANDARDS.md`.
- All data remains local.
- Batch/background processing is acceptable.
- Data volume: ~1000 photos per album.
- Bib detection remains stage 1 in the pipeline.
- Absolute thresholds are acceptable.
- CPU-only processing (no GPU assumed).
- Target batch time: ~10 minutes for ~1000 photos.
- Clustering is scoped per race/event (no cross-event identity tracking).
- Face recognition uses original RGB images (no CLAHE), with optional mild normalization
  for detection only.

## Pipeline Stages
1. Bib Scan
   - Existing bib detection per photo.
   - Store bib candidates with confidence and bounding boxes.

2. Face Scan
   - Detect faces.
   - Generate embeddings for each face.
   - Store face bounding boxes, embeddings, and model metadata.

3. Clustering
   - Cluster embeddings into person groups.
   - Store cluster id, centroid, and similarity stats.

4. Linking (Autolink + Evidence)
   - If exactly one face and a bib candidate with confidence >= threshold:
     - Autolink cluster <-> bib.
   - If multiple faces:
     - Store candidate links.
     - Allow autolink when a face belongs to a strongly linked cluster (inherit bib).
   - Persist evidence: photo hash, face box, bib box, confidences, model info.

5. Serving
   - Browse by bib and by person cluster.
   - Show numeric similarity and label (high/medium/low).
   - Traceability visible in UI (why a link exists).
   - Inspection/debug UI may be complex.
   - Customer UI should stay minimal (enter bib -> get photos), without face cluster exposure.

## Face Backend (Swappable)
- Define a FaceBackend interface:
  - detect_faces(image) -> [boxes]
  - embed_faces(image, boxes) -> [vectors]
  - model_info() -> {name, dims, version}
- Configure backend via config.py (no code changes to swap).
- Start with 1 backend for v1, expand later.
- Consider optional two-pass approach:
  - Pass 1: fast model for quick clustering and early results.
  - Pass 2: slower model for refinement (if it materially improves quality).

## Storage Strategy
- Production: SQLite for core relations and indices.
- Benchmarking: JSON for heavy artifacts (embeddings, per-face data).
- Embeddings stored as blobs or sidecar JSON, referenced by photo hash.
- Maintain model/version fields to avoid mixing embeddings from different models.

## Confidence Strategy
- Absolute thresholds for:
  - Bib detection confidence (for autolink eligibility).
  - Face similarity (cluster membership / link quality).
- Also compute a label derived from numeric similarity:
  - High / Medium / Low (thresholds configurable).

## Merge/Split (UI)
- Merge: combine two clusters if same person.
- Split: separate one cluster into two if mixed persons.
- Planned as a UI capability, primarily for offline tuning/learning.

## Learning From Corrections (Future)
- Store corrections as explicit labels (cluster equivalence/inequivalence).
- Use these for offline evaluation and threshold calibration.
- Avoid online training unless a clear, stable approach emerges.

## Open Questions (Next Pass)
- Select initial face model and detection backend.
- Confirm UI surfaces for cluster browsing and correction flow.

## Decisions (V1)
- Clustering: agglomerative with fixed distance threshold.
- UI: admin-only cluster browsing; customer UI stays bib-only.
- Autolink: allow inheritance from strongly linked clusters (with provenance).
- Face artifacts: store face snippets as files; precompute boxed previews.
- Storage: SQLite blobs (production) + JSON for benchmarking artifacts.

## Grouped TODOs
### Group 1: Core Face Backend + Storage Plumbing
- [x] Define FaceBackend interface and config wiring (swappable).
- [x] Implement one local backend (detect, embed, model_info).
- [x] Add schema/JSON structures for face detections, embeddings, model metadata.
- [x] Store embeddings in SQLite blobs (production) and JSON (benchmarking).

### Group 2: Face Artifacts + Evidence Assets
- [x] Persist face bounding boxes per photo.
- [x] Save face snippets as files (keyed by photo hash + face id).
- [x] Precompute boxed preview images for admin inspection.
- [x] Store evidence records linking face box + bib box + confidence.

### Group 3: Clustering + Similarity Labels
- [x] Implement agglomerative clustering with fixed distance threshold.
- [x] Store cluster id, centroid, and similarity stats.
- [x] Compute similarity labels (High/Medium/Low) from numeric thresholds.

### Group 4: Autolink + Provenance
- [ ] Autolink rule: single face + high bib confidence.
- [ ] Autolink rule: inherit bib from strongly linked cluster (multi-face OK).
- [ ] Autolink refinement: prefer largest bib candidate in expected torso region and
  ignore tiny/partial detections when linking faces to bibs.
- [ ] Persist provenance (`bib-detection` vs `face-inherited`) + evidence trail.

### Group 5: Admin UI (Read-Only)
- [x] Add admin-only cluster browsing view.
- [ ] Show bib tags with provenance badge.
- [x] Click-through to evidence photo and face snippets (with boxes).

### Group 6: Benchmarking + Tuning

**Phase 0 — Freeze & baseline (no code changes)**
- [ ] `bnr benchmark freeze --name v1-labeled` — create immutable snapshot of labeled set.
- [ ] `bnr benchmark -s full --note "baseline before tuning"` — establish current metrics.
- [ ] `bnr benchmark set-baseline` — record as regression baseline.

**Phase 1 — Wire face detection into runner** (task-027)
- [ ] Load `face_ground_truth.json` in `run_benchmark()`.
- [ ] Instantiate face backend via `get_face_backend()` (pattern: ghost.py lines 320–376).
- [ ] Extend `_run_detection_loop()` to run `detect_face_candidates()` per photo.
- [ ] Accumulate `FaceScorecard` (TP/FP/FN) using `score_faces()` from scoring.py.
- [ ] Assign `face_scorecard` to `BenchmarkRun` and print in CLI output.

**Phase 2 — Wire autolink predictions into runner** (tasks 030–031)
- [ ] Implement `faces/autolink.py` — rule-based predictor: 1 face + 1 high-confidence bib → link;
      inherit bib from strongly-linked cluster when multiple faces present.
- [ ] Extend `run_benchmark()` to call autolink predictor per photo and pass predicted pairs to
      `score_links()`, replacing the stub `LinkScorecard(link_tp=0, ...)` with real values.

**Phase 3 — Parameter tuning** (tasks 028, 029)
- [ ] Add `get_face_backend_with_overrides(**kwargs)` to `faces/backend.py`.
- [ ] Create `benchmarking/tuner.py` with `run_face_sweep()`.
- [ ] Add `bnr benchmark tune --config YAML` CLI subcommand; prints ranked table.
- [ ] Add `benchmarking/tune_configs/face_default.yaml` and `bib_default.yaml`.
- [ ] (Later) OCR candidate caching for fast bib sweeps — task-029.

**Phase 4 — Cluster quality evaluation** (deferred)
- [ ] Optional: evaluation report for cluster purity / silhouette score.
- [ ] Optional: JSON export of embeddings for offline experiments.

## Tasks

| Task | Title | Depends on |
|------|-------|------------|
| task-027 | Wire face detection into benchmark runner | — |
| task-028 | Add face backend override factory | — |
| task-029 | Face parameter sweep (bnr benchmark tune) | 027, 028 |
| task-030 | Implement face-bib autolink predictor | — |
| task-031 | Wire autolink into benchmark runner | 027, 030 |

See `todo/tasks/task-027-*.md` through `task-031-*.md` for details.

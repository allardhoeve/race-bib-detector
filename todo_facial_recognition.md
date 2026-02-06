# Facial Recognition Plan (Preliminary)

Date: 2026-02-06

## Goals
- Support local-only face detection and grouping for photos with missing/obscured bibs.
- Allow browsing photos by person clusters and by bibs.
- Autolink person clusters to bibs when confidence is high and evidence is traceable.
- Prioritize fewer false negatives (avoid missing matches), with later correction/learning paths.

## Non-Goals (Initial)
- No cloud services or external APIs.
- No automatic training from user corrections (yet).
- No fully automated multi-person bib attribution (start conservative).

## Constraints / Assumptions
- Photo identification follows `STANDARDS.md`.
- All data remains local.
- Batch/background processing is acceptable.
- Data volume: ~1000 photos per album.
- Bib detection remains stage 1 in the pipeline.
- Absolute thresholds are acceptable.
- CPU-only processing (no GPU assumed).
- Target batch time: ~10 minutes for ~1000 photos.
- Clustering is scoped per race/event (no cross-event identity tracking).

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
   - If multiple faces: store candidate links, do not autolink (v1).
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
- Start with 1-2 backends for benchmarking, expand later.
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
- Select initial face model(s) and detection backend(s).
- Confirm embedding storage format (SQLite blob vs JSON sidecar).
- Decide on clustering algorithm (e.g., DBSCAN/HDBSCAN).
- Define UI surfaces for cluster browsing and correction flow.

## Next Steps
1. Prototype face backend interface and a single local implementation.
2. Add schema/JSON structures for face detections and clusters.
3. Implement clustering stage and store outputs.
4. Implement autolink logic with evidence trail.
5. Expose cluster browsing in UI (read-only initially).

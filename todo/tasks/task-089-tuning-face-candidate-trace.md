# Task 089: Face candidate trace — complete the trace-based pipeline output

Part of the tuning series (085-094). Parallel to task-088 (bib trace).

**Depends on:** task-088 (establishes the trace pattern + SinglePhotoResult restructure)

## Goal

Create `FaceCandidateTrace` in `pipeline/types.py` and replace the remaining separate face fields on `SinglePhotoResult` with `face_trace`. After this task, `SinglePhotoResult` carries only traces — symmetric for bibs and faces.

## Background

After task-088, `SinglePhotoResult` has `bib_trace` but still carries three face representations:
- `face_candidates_all: list[FaceCandidate]` — all candidates (passed + rejected)
- `face_boxes: list[FaceBox]` — normalised boxes for accepted faces only
- `face_pixel_bboxes: list[Bbox]` — pixel-space bboxes for embedding

The trace unifies these. `face_trace` records every candidate's detection journey. Need accepted faces? Filter. Need pixel bboxes? The trace carries them.

### SinglePhotoResult after this task

```python
@dataclass
class SinglePhotoResult:
    image_dims: tuple[int, int]
    bib_trace: list[BibCandidateTrace]       # from task-088
    face_trace: list[FaceCandidateTrace]      # THIS TASK
    autolink: AutolinkResult | None
    image_rgb: np.ndarray | None
    bib_detect_time_ms: float
    face_detect_time_ms: float
```

Symmetric. Clean.

## Design decisions

| Question | Decision |
|----------|----------|
| Where does FaceCandidateTrace live? | `pipeline/types.py` — parallel to BibCandidateTrace |
| Pixel bboxes | Stored on trace as `pixel_bbox: tuple[int,int,int,int] | None` for accepted faces |
| `accepted` vs `passed` | Separate fields. `passed` = backend threshold. `accepted` = final verdict after fallback chain. Today identical; future refinement may change `accepted`. |
| Clustering/embedding fields | Defined with `None` defaults. Populated by later tasks (090, 091). |

## Context

- `pipeline/single_photo.py` — `run_single_photo()`, builds traces
- `pipeline/types.py` — where `FaceCandidateTrace` will live
- `detection/face/types.py` — `FaceCandidate` (bbox, confidence, passed, rejection_reason, model)
- `detection/face/backend.py` — `detect_face_candidates()` returns all candidates
- `benchmarking/runner.py` — `_run_detection_loop()` reads `sp_result.face_boxes`, `sp_result.face_candidates_all`
- `scan/persist.py` — reads `sp.face_pixel_bboxes`, `sp.face_boxes`, `sp.face_candidates_all`

## Changes

### New: `pipeline/types.py` — FaceCandidateTrace

```python
class FaceCandidateTrace(BaseModel):
    """Complete journey of one face candidate through the pipeline."""
    # Geometry (normalised [0,1])
    x: float
    y: float
    w: float
    h: float
    # Detection stage
    confidence: float | None = None  # None for Haar backend
    passed: bool
    rejection_reason: str | None = None  # "confidence", "nms", "eyes"
    # Pipeline verdict
    accepted: bool = False
    # Pixel bbox for embedding/artifacts (accepted faces only)
    pixel_bbox: tuple[int, int, int, int] | None = None  # (x1, y1, x2, y2)
    # Populated by later tasks:
    embedding: list[float] | None = None              # task-090
    cluster_id: int | None = None                     # task-091
    cluster_distance: float | None = None             # task-091
    nearest_other_distance: float | None = None       # task-091
```

### Modified: `pipeline/single_photo.py`

Build face traces alongside existing face detection:

```python
face_trace: list[FaceCandidateTrace] = []
for cand in face_candidates_all:
    x1, y1, x2, y2 = bbox_to_rect(cand.bbox)
    is_accepted = cand.bbox in passed_bboxes_set
    face_trace.append(FaceCandidateTrace(
        x=x1 / img_w, y=y1 / img_h,
        w=(x2 - x1) / img_w, h=(y2 - y1) / img_h,
        confidence=cand.confidence,
        passed=cand.passed,
        rejection_reason=cand.rejection_reason,
        accepted=is_accepted,
        pixel_bbox=(x1, y1, x2, y2) if is_accepted else None,
    ))
```

Remove `face_boxes`, `face_candidates_all`, `face_pixel_bboxes` from `SinglePhotoResult`.

### Modified: consumers

**`benchmarking/runner.py`:**
- `PhotoResult.face_trace: list[FaceCandidateTrace] | None = None`
- `_run_detection_loop()`: read accepted faces from `sp_result.face_trace`
- For scoring: build `list[FaceBox]` from accepted traces for `score_faces()`
- For autolink: `sp_result.autolink` already uses `BibBox`/`FaceBox` — project from traces at call site
- `_assign_face_clusters()`: iterate `face_trace` for embedding instead of `pred_face_boxes`

**`scan/persist.py`:**
- Embedding: use `[t.pixel_bbox for t in sp.face_trace if t.accepted]` for bboxes
- Artifact saving: same pixel_bbox for face snippets
- `face_candidates_all` → `[t for t in sp.face_trace]` (or project FaceCandidate if needed for `save_face_candidates_preview`)

## Tests

In `tests/test_runner_models.py`:

```python
class TestFaceCandidateTrace:
    def test_round_trip(self): ...
    def test_rejected_by_confidence(self): ...
    def test_rejected_by_nms(self): ...
    def test_no_confidence_haar(self): ...
    def test_accepted_has_pixel_bbox(self): ...
    def test_clustering_fields_default_none(self): ...
    def test_photo_result_with_face_trace(self): ...
    def test_backward_compat_no_face_trace(self): ...
```

## Verification

```bash
venv/bin/python -m pytest tests/test_runner_models.py -v
venv/bin/python -m pytest
```

## Pitfalls

- **Coordinate normalisation for rejected candidates**: All candidates get normalised, not just passed ones. The fallback chain may promote rejected candidates — their normalised coords must already be on the trace.
- **Haar backend `confidence=None`**: Must be `float | None`, not defaulting to 0.0.
- **`pixel_bbox` for artifact saving**: `scan/persist.py` needs pixel bboxes for face snippets. Store on trace for accepted faces.
- **Autolink uses BibBox/FaceBox objects**: `predict_links()` takes lists of BibBox and FaceBox. Project from traces at the call site in `run_single_photo()`.

## Acceptance criteria

- [ ] `FaceCandidateTrace` exists in `pipeline/types.py`
- [ ] `SinglePhotoResult` uses `face_trace` — no more `face_boxes`, `face_candidates_all`, `face_pixel_bboxes`
- [ ] `SinglePhotoResult` is now symmetric: `bib_trace` + `face_trace`
- [ ] Rejected candidates preserved in trace with `rejection_reason`
- [ ] All consumers updated
- [ ] Backward compat for old JSON
- [ ] All tests pass

## Scope boundaries

- **In scope**: trace type, SinglePhotoResult cleanup, consumer updates
- **Out of scope**: embedding (task-090), clustering diagnostics (task-091)
- **Do not** change detection or backend behavior

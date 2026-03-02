# Task 073: Face candidate trace — capture detection pipeline journey

Part of the tuning series (071–077). Parallel to task-072 (bib candidate trace).

**Depends on:** task-072 (establishes the trace pattern)

## Goal

Store all face candidates (passed and rejected) from `detect_face_candidates()` on `PhotoResult` as `face_trace`. Currently, `_run_face_detection()` silently discards rejected candidates. This captures the detection stage of the face pipeline for diagnostics and future tuning.

## Background

The face backend already returns full diagnostic data via `detect_face_candidates()`:

```
DNN forward pass → raw detection (confidence)
  → confidence threshold → pass/reject (rejection_reason="confidence")
  → NMS dedup → pass/reject (rejection_reason="nms")
```

Or for Haar:

```
Haar cascade → raw detection
  → eye validation → pass/reject (rejection_reason="eyes")
```

The runner calls `detect_face_candidates()` but only keeps passed candidates:

```python
for cand in face_candidates:
    if not cand.passed:
        continue  # DISCARDED — confidence, rejection_reason lost
```

The fix is simple: store all candidates in a trace, mirroring the bib trace pattern.

## Design decisions

| Question | Decision |
|----------|----------|
| Model name | `FaceCandidateTrace` — parallel to `BibCandidateTrace` |
| PhotoResult field | `face_trace` — parallel to `bib_trace` |
| Clustering fields | Out of scope — this task covers detection stage only. Clustering diagnostics are a separate task. |
| Backend model info | Not stored per-candidate. Already captured in `FacePipelineConfig` on `RunMetadata`. |

## Context

- `faces/backend.py:154-232` — `OpenCVDnnSsdFaceBackend.detect_face_candidates()` returns all candidates with `passed`, `rejection_reason`, `confidence`
- `faces/backend.py:34-113` — `OpenCVHaarFaceBackend.detect_face_candidates()` same contract
- `faces/types.py:98-115` — `FaceCandidate` (Pydantic BaseModel): bbox, confidence, passed, rejection_reason, model
- `benchmarking/runner.py:461-493` — `_run_face_detection()` where rejected candidates are discarded
- `benchmarking/runner.py:103` — `PhotoResult.pred_face_boxes` (only passed candidates today)
- `benchmarking/runner.py:73-85` — `BibCandidateTrace` (task-072, the pattern to follow)

## Test-first approach

### New tests in `tests/test_runner_models.py`

```python
# FaceCandidateTrace — round-trip and PhotoResult integration

def _face_candidate_dict(**overrides):
    base = dict(x=0.1, y=0.2, w=0.15, h=0.2, confidence=0.85, passed=True,
                rejection_reason=None, accepted=True)
    base.update(overrides)
    return base

class TestFaceCandidateTrace:
    def test_round_trip(self):
        """FaceCandidateTrace serialises and deserialises correctly."""

    def test_rejected_by_confidence(self):
        """Trace with passed=False, rejection_reason='confidence' preserves fields."""

    def test_rejected_by_nms(self):
        """Trace with passed=False, rejection_reason='nms' preserves fields."""

    def test_no_confidence_haar(self):
        """Trace with confidence=None (Haar backend) round-trips correctly."""

    def test_photo_result_with_face_trace(self):
        """PhotoResult with face_trace populated serialises and deserialises."""

    def test_photo_result_without_face_trace_backward_compat(self):
        """Old PhotoResult JSON without face_trace loads with None."""
```

## Changes

### Modified: `benchmarking/runner.py`

Add `FaceCandidateTrace` model (parallel to `BibCandidateTrace`):

```python
class FaceCandidateTrace(BaseModel):
    """Record of one face candidate's journey through the detection pipeline."""
    # Geometry (normalised [0,1])
    x: float
    y: float
    w: float
    h: float

    # Detection stage
    confidence: float | None = None  # Backend confidence (None for Haar)

    # Filtering outcome
    passed: bool
    rejection_reason: str | None = None  # "confidence", "nms", "eyes"

    # Final verdict
    accepted: bool = False
```

Add field on `PhotoResult`:

```python
class PhotoResult(BaseModel):
    ...
    face_trace: list[FaceCandidateTrace] | None = None
```

Update `_run_face_detection()` to store all candidates:

```python
def _run_face_detection(face_backend, image_data):
    ...
    face_candidates = face_backend.detect_face_candidates(image_rgb)

    pred_face_boxes = []
    face_trace = []

    for cand in face_candidates:
        # Normalise bbox to [0,1]
        x1, y1, x2, y2 = bbox_to_rect(cand.bbox)
        nx, ny = x1 / face_w, y1 / face_h
        nw, nh = (x2 - x1) / face_w, (y2 - y1) / face_h

        is_accepted = cand.passed  # today these are identical
        face_trace.append(FaceCandidateTrace(
            x=nx, y=ny, w=nw, h=nh,
            confidence=cand.confidence,
            passed=cand.passed,
            rejection_reason=cand.rejection_reason,
            accepted=is_accepted,
        ))

        if cand.passed:
            pred_face_boxes.append(FaceBox(
                x=nx, y=ny, w=nw, h=nh,
                confidence=cand.confidence,
            ))

    return pred_face_boxes, face_trace, elapsed_ms
```

Update `_run_detection_loop()` to store `face_trace` on `PhotoResult`.

### Return type change for `_run_face_detection()`

Currently returns `tuple[list[FaceBox], float]`. Changes to `tuple[list[FaceBox], list[FaceCandidateTrace], float]`.

## Verification

```bash
# TDD: write tests first, verify they fail
venv/bin/python -m pytest tests/test_runner_models.py::TestFaceCandidateTrace -v

# Make changes, verify tests pass
venv/bin/python -m pytest tests/test_runner_models.py -v

# Full suite
venv/bin/python -m pytest
```

## Pitfalls

- **Coordinate normalisation for rejected candidates**: Currently only passed candidates get normalised. Rejected candidates still have `FaceCandidate.bbox` in polygon format. The normalisation must apply to all candidates uniformly.
- **Haar backend returns `confidence=None`**: `FaceCandidateTrace.confidence` must be `float | None`. Don't accidentally default to 0.0.
- **`accepted` vs `passed`**: Today they're identical (the runner adds no filtering beyond the backend). Keep them as separate fields for forward-compatibility — the runner or clustering stage could add its own filtering later.

## Acceptance criteria

- [ ] `FaceCandidateTrace` model exists, parallel to `BibCandidateTrace`
- [ ] `PhotoResult.face_trace` field exists, defaults to `None`
- [ ] `_run_face_detection()` stores all candidates (passed + rejected) in the trace
- [ ] Rejected candidates have `rejection_reason` preserved
- [ ] Backward compat: old JSON without `face_trace` loads with `None`
- [ ] TDD tests pass
- [ ] All existing tests pass (`venv/bin/python -m pytest`)

## Scope boundaries

- **In scope**: trace model, store all candidates, tests
- **Out of scope**: clustering diagnostics (separate task), consuming traces for tuning (task-076), face fallback backend cleanup
- **Do not** change backend behavior or detection logic

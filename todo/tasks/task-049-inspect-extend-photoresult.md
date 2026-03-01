# Task 049: Add prediction fields to PhotoResult

Independent of other open tasks. No prerequisites.

## Goal

Extend `PhotoResult` with optional fields to carry per-photo predicted bounding boxes (bib + face) and ground-truth boxes through the benchmark run, so they can be serialised into the run JSON and consumed by the inspect page.

## Background

Today `PhotoResult` stores only bib *numbers* (as ints) and aggregate TP/FP/FN counts. The actual predicted `BibBox` and `FaceBox` objects are computed inside `_run_detection_loop` as local variables, scored, and discarded. To render an overlay in the inspect page (task-053), the boxes must survive into `BenchmarkRun.photo_results` and be persisted in the run JSON.

## Context

- `benchmarking/runner.py:71` — `PhotoResult(BaseModel)` with current fields
- `benchmarking/ground_truth.py:76` — `BibBox(BaseModel)` (x, y, w, h, number, scope)
- `benchmarking/ground_truth.py:200` — `FaceBox(BaseModel)` (x, y, w, h, scope, identity, tags)
- `benchmarking/runner.py:187` — `BenchmarkRun(BaseModel)` serialises to JSON via `model_dump()`
- `tests/test_runner_models.py` — existing model tests

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Store predictions or re-run on inspect? | Store in `PhotoResult`; re-running is slow (~30s) and needs GPU |
| Store GT boxes too? | Yes — bib GT boxes and face GT boxes. Avoids inspect route needing to load separate GT files |
| Field names | `pred_bib_boxes`, `pred_face_boxes`, `gt_bib_boxes`, `gt_face_boxes` |
| Default value | `None` (backward-compat with existing run JSONs that lack these fields) |
| Serialisation cost | BibBox/FaceBox are small Pydantic models; 250 photos × ~5 boxes = ~1250 objects — negligible |

## Changes

### Modified: `benchmarking/runner.py`

Add four optional fields to `PhotoResult`:

```python
class PhotoResult(BaseModel):
    """Result of running detection on a single photo."""
    content_hash: str
    expected_bibs: list[int]
    detected_bibs: list[int]
    tp: int
    fp: int
    fn: int
    status: Status
    detection_time_ms: float
    tags: list[str] = Field(default_factory=list)
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    preprocess_metadata: dict[str, Any] = Field(default_factory=dict)
    # Prediction + GT boxes for inspect overlay (task-049)
    pred_bib_boxes: list[BibBox] | None = None
    pred_face_boxes: list[FaceBox] | None = None
    gt_bib_boxes: list[BibBox] | None = None
    gt_face_boxes: list[FaceBox] | None = None
```

## Tests

Extend `tests/test_runner_models.py`:

- `test_photo_result_box_fields_default_none()` — new fields default to `None`
- `test_photo_result_with_boxes_roundtrip()` — construct with `BibBox`/`FaceBox` lists, `model_dump()` → `PhotoResult(**data)` roundtrip
- `test_photo_result_backward_compat()` — `PhotoResult(**old_dict)` where old_dict lacks the new fields → fields are `None`

## Verification

```bash
venv/bin/python -m pytest tests/test_runner_models.py -v
```

## Acceptance criteria

- [x] All existing tests still pass (`venv/bin/python -m pytest`)
- [x] New tests pass
- [x] `PhotoResult` accepts `None` (default) or `list[BibBox]`/`list[FaceBox]` for the four new fields
- [x] Existing run JSON files load without error (backward compatibility)

## Scope boundaries

- **In scope**: adding fields to `PhotoResult`, tests
- **Out of scope**: populating the fields (task-050), UI rendering (task-053)
- **Do not** change `BibBox`, `FaceBox`, `BenchmarkRun`, or any other model

# Task 079: Remove dead face fallback backend config

Small cleanup task.

## Goal

Remove the unused face fallback backend configuration that is stored but never used during detection.

## Background

These config values exist in `config.py` and are recorded in `FacePipelineConfig` on every benchmark run, but no code ever reads them to influence detection behavior:

- `FACE_FALLBACK_BACKEND = "opencv_haar"`
- `FACE_FALLBACK_MIN_FACE_COUNT = 2`
- `FACE_FALLBACK_MAX = 3`
- `FACE_FALLBACK_IOU_THRESHOLD = 0.3`

The DNN backend also has `fallback_confidence_min` as a field, stored but unused.

These create the illusion of a fallback mechanism that doesn't exist.

## Changes

- Remove the four `FACE_FALLBACK_*` constants from `config.py`
- Remove `FACE_DNN_FALLBACK_CONFIDENCE_MIN` and `FACE_DNN_FALLBACK_MAX` from `config.py`
- Remove `fallback_confidence_min` from `OpenCVDnnSsdFaceBackend`
- Remove fallback fields from `FacePipelineConfig` in `runner.py`
- Update `FacePipelineConfig.summary()` and `summary_passes()`
- Update `_build_run_metadata()` to stop passing fallback values
- Update `tests/test_runner_models.py` fixtures

## Test-first approach

```python
def test_no_fallback_config_exists():
    """config module has no FACE_FALLBACK_* or FACE_DNN_FALLBACK_* attributes."""

def test_face_pipeline_config_has_no_fallback_fields():
    """FacePipelineConfig has no fallback_* fields."""

def test_old_json_with_fallback_fields_loads():
    """Backward compat: old FacePipelineConfig JSON with fallback fields loads."""
```

## Acceptance criteria

- [ ] No `FALLBACK` constants in `config.py` for faces
- [ ] `FacePipelineConfig` has no fallback fields
- [ ] Old benchmark JSON with fallback fields loads without error
- [ ] TDD tests pass
- [ ] All existing tests pass

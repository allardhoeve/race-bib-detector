# task-028: Add face backend override factory

**Status:** pending

## Goal

Allow the tuner to instantiate a face backend with non-default confidence/NMS thresholds
without mutating module-level config.

## Changes

### `faces/backend.py`

Add `get_face_backend_with_overrides(backend_name: str | None = None, **kwargs) -> FaceBackend`:
- If `backend_name` is None, use `config.FACE_BACKEND`.
- Merge `kwargs` into the dataclass constructor kwargs for the selected backend class.
- Unknown kwargs raise `ValueError`.

Expose relevant constructor params in `OpenCVDnnSsdFaceBackend.__init__` (currently reads from
config in `__post_init__`):
- `confidence_min: float | None = None`
- `nms_iou: float | None = None`
- `fallback_confidence_min: float | None = None`

If a param is None, fall back to the config value.

Same pattern for `OpenCVHaarFaceBackend`:
- `min_neighbors: int | None = None`
- `scale_factor: float | None = None`
- `min_size: tuple[int, int] | None = None`

## Tests

File: `tests/test_face_backend_overrides.py`

- `test_dnn_backend_override_confidence()` — assert returned backend uses the overridden
  `confidence_min` value, not the config default.
- `test_haar_backend_override_neighbors()` — same for Haar `min_neighbors`.
- `test_unknown_kwarg_raises()` — `get_face_backend_with_overrides(foo=1)` raises `ValueError`.

## Scope boundary

- Do **not** change `get_face_backend()` (the no-override path).
- Do not touch scoring or runner.
- This task is a prerequisite for task-029 (face sweep).

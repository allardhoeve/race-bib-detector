# Task 068: Reduce monkeypatch — context object for tuner functions

## Problem

`test_tuners_grid.py` has 50+ patch calls. Every test that exercises `run_face_sweep`,
`_evaluate_single_combo`, or `validate_on_full` requires a 5-7 deep `with patch(...)`
stack to mock data-loading functions:

```python
with patch(f"{P}.load_bib_ground_truth", return_value=bib_gt), \
     patch(f"{P}.load_face_ground_truth", return_value=face_gt), \
     patch(f"{P}.load_photo_index", return_value=index), \
     patch(f"{P}.load_photo_metadata") as mock_meta, \
     patch(f"{P}.PHOTOS_DIR", tmp_path), \
     patch(f"{P}.get_face_backend_with_overrides", return_value=backend):
```

This block repeats 8 times with minor variations. It's the single worst patching
offender in the codebase.

## Solution

Introduce a context dataclass that holds pre-loaded data:

```python
@dataclass
class TunerContext:
    bib_gt: BibGroundTruth
    face_gt: FaceGroundTruth
    index: dict
    meta_store: PhotoMetadata
    photos_dir: Path
```

Make `run_face_sweep`, `_evaluate_single_combo`, and internal helpers accept an
optional `ctx: TunerContext | None = None` parameter. When `None` (production),
they load data as before. When provided (tests), they use the pre-loaded data.

Tests then pass the context directly — zero patches needed for data loading.

## Prior art

This is exactly how the zero-patch test files already work. `test_autolink.py`,
`test_ghost.py`, `test_scoring.py` all construct data objects directly and pass
them to pure functions. The tuner functions just need the same treatment.

## Scope

- Small production change: add `TunerContext` dataclass and optional parameter
- Large test simplification: ~50 patch calls eliminated
- `get_face_backend_with_overrides` is still called per-combo and may still need
  patching in tests that want a stub backend — but the data-loading patches vanish

## Acceptance criteria

- [ ] `TunerContext` dataclass exists
- [ ] `run_face_sweep` and `_evaluate_single_combo` accept optional context
- [ ] Production code path unchanged (context is loaded when not provided)
- [ ] `test_tuners_grid.py` tests rewritten without data-loading patches
- [ ] No test has more than 2 concurrent `patch()` calls for tuner functions
- [ ] All tests pass (`venv/bin/python -m pytest`)

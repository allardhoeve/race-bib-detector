# Task 069: Reduce monkeypatch — inject detect_fn and paths in runner

## Problem

`test_runner.py` patches `detect_bib_numbers` 12 times and `PHOTOS_DIR` 9 times.
Nearly every test of `_run_detection_loop` starts with:

```python
with patch("benchmarking.runner.detect_bib_numbers") as mock_det, \
     patch("benchmarking.runner.PHOTOS_DIR", tmp_path):
    mock_det.return_value = _fake_bib_result()
```

Meanwhile, `face_backend` is already injected as a parameter — proving the pattern
works. The bib detector and path constants just haven't been updated yet.

`RESULTS_DIR` and `BASELINE_PATH` are also module-level constants that require
patching in tests.

## Solution

1. **`detect_fn` parameter**: Make `_run_bib_detection` (or `_run_detection_loop`)
   accept `detect_fn: Callable = detect_bib_numbers`. Tests pass a fake directly.

2. **`photos_dir` parameter**: Make `run_benchmark` and detection helpers accept
   `photos_dir: Path = PHOTOS_DIR`. Tests pass `tmp_path` directly.

3. **`results_dir` / `baseline_path`**: Same pattern — optional parameters with
   production defaults.

## Dependency

Benefits from task-035 (split detection loop into `_run_bib_detection` +
`_run_face_detection`), which is the natural place to add these parameters.
Can be done independently but is easier alongside that refactor.

## Scope

- Production change: add optional parameters with defaults (backwards compatible)
- Test simplification: ~14 `with patch(...)` blocks eliminated in `test_runner.py`
  and `test_runner_links.py`
- Module-level constants remain as defaults — no behaviour change

## Acceptance criteria

- [ ] `_run_bib_detection` (or detection loop) accepts `detect_fn` parameter
- [ ] `run_benchmark` accepts `photos_dir` parameter
- [ ] `test_runner.py` tests call functions directly without patching detect/paths
- [ ] No `patch("benchmarking.runner.detect_bib_numbers")` remains in tests
- [ ] All tests pass (`venv/bin/python -m pytest`)

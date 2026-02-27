# Task 036: Add docstrings and inline comments to runner.py

Extracted from task-033 sub-task C. Depends on task-034 and task-035 being complete.

## Goal

After the Pydantic migration (task-034) and loop split (task-035), add targeted
docstrings and inline comments to the parts of `runner.py` that remain opaque to a
reader who doesn't already know the domain.

## What to document

### `_build_run_metadata`

Add a docstring explaining:
- What it captures: git state, environment, pipeline config snapshot.
- Why `fallback_backend` needs normalisation from `""` to `None` (the config layer leaks
  empty strings when no fallback is set; normalise here at the boundary).

### `_run_detection_loop` (post task-035)

Add a docstring explaining the three phases:
1. Bib OCR + normalised BibBox conversion + IoU scoring.
2. Face detection + normalised FaceBox conversion + face IoU scoring (optional, skipped
   when `face_backend` is `None`).
3. Scorecard accumulation: counters are summed across all photos, then wrapped in
   `BibScorecard` / `FaceScorecard` at the end.

### `run_benchmark`

Document the face backend fallback strategy: `get_face_backend()` is called inside a
try/except; if it raises for any reason (model not installed, config error), `face_backend`
is set to `None` and face scoring is silently skipped for the entire run.

### `compare_to_baseline`

Document:
- What "tolerance" means: a symmetric band around zero; improvement and regression are
  both defined by exceeding this band in either direction.
- The asymmetry in the judgement: *any* single metric regressing (precision OR recall)
  triggers `"REGRESSED"`, but *any* single metric improving triggers `"IMPROVED"`.
  If metrics move in opposite directions, regression wins.

### `compute_photo_result`

Comment the two special-case branches:
- Zero expected bibs: a photo with no bibs is `PASS` only if also no FP detections;
  otherwise `PARTIAL` (false positives on a clean photo).
- `tp == 0 and expected > 0`: hard miss — detected nothing that was there.

## No tests needed

Documentation-only changes. Run `pytest` after to confirm nothing regressed.

## Files

- `benchmarking/runner.py` — docstrings and inline comments only

# Task 086: Reorganize `detection/` into `detection/{bib,face,link}`

Structural prerequisite for the tuning series (085-094). Can be done in parallel with task-085.

## Goal

Both bib detection and face detection are "detection." The current layout has bib detection in `detection/` and face detection in `faces/` — a misnomer. Reorganize into `detection/bib/`, `detection/face/`, and `detection/link/`.

## Background

Current layout and what moves:

```
detection/           → detection/bib/
  types.py             types.py    (BibCandidate, Detection, PipelineResult)
  detector.py          detector.py (detect_bib_numbers)
  regions.py           regions.py
  filtering.py         filtering.py
  validation.py        validation.py
  bbox.py              bbox.py
  __init__.py          __init__.py (re-exports detect_bib_numbers)

faces/               → detection/face/
  backend.py           backend.py  (FaceBackend, DNN, Haar, get_face_backend)
  embedder.py          embedder.py (FaceEmbedder, FaceNetEmbedder)
  types.py             types.py    (FaceCandidate, FaceModelInfo)
  artifacts.py         artifacts.py

pipeline_types.py    → detection/link/   (partial)
  predict_links          predictor.py
  _torso_region          predictor.py
  AutolinkResult         types.py
  BibFaceLink            stays in pipeline/types.py (used everywhere)
```

What stays in `faces/` (or a renamed package — see note):
- `clustering.py` — moves to `pipeline/cluster.py` in task-091
- `types.py:FaceDetection` — production DB type, stays near DB layer

What stays in `pipeline/types.py`:
- `BibBox`, `FaceBox` — pipeline-level normalised boxes
- `BibFaceLink` — used by scoring, GT, everywhere
- Scope constants

## Bib artifacts

Currently bib artifact saving is inline in `scan/pipeline.py` (`save_detection_artifacts()`). Extract to `detection/bib/artifacts.py` for symmetry with `detection/face/artifacts.py`.

## `detection/__init__.py`

Keep backward-compat re-exports:

```python
# detection/__init__.py
from detection.bib.detector import detect_bib_numbers  # noqa: F401
```

## `faces/__init__.py`

Keep backward-compat re-exports during transition:

```python
# faces/__init__.py
from detection.face.backend import FaceBackend, get_face_backend  # noqa: F401
```

Or update all consumers directly. Either approach is fine — the key metric is all tests pass.

## Import updates

Major consumers to update:

- `pipeline/single_photo.py` — imports `detect_bib_numbers`, `FaceCandidate`, `FaceBackend`
- `pipeline/types.py` — imports autolink constants from `config`
- `benchmarking/runner.py` — imports `FaceBackend`, `get_face_backend`
- `benchmarking/tuners/grid.py` — imports `get_face_backend_with_overrides`
- `scan/persist.py` — imports face artifacts, `FaceDetection`
- `config.py` — no change (constants only)
- Test files throughout

## Test-first approach

```python
def test_detection_bib_importable():
    from detection.bib.detector import detect_bib_numbers
    from detection.bib.types import BibCandidate, Detection, PipelineResult

def test_detection_face_importable():
    from detection.face.backend import FaceBackend, get_face_backend
    from detection.face.embedder import get_face_embedder
    from detection.face.types import FaceCandidate

def test_detection_link_importable():
    from detection.link.predictor import predict_links
```

## Verification

```bash
venv/bin/python -m pytest  # all tests pass
```

## Acceptance criteria

- [ ] `detection/bib/` contains all former `detection/*.py` files
- [ ] `detection/face/` contains `backend.py`, `embedder.py`, `types.py`, `artifacts.py`
- [ ] `detection/link/` contains `predictor.py` with `predict_links`
- [ ] `detection/bib/artifacts.py` exists with bib artifact saving
- [ ] Backward-compat re-exports in `detection/__init__.py` and/or `faces/__init__.py`
- [ ] All imports updated
- [ ] All existing tests pass

## Scope boundaries

- **In scope**: file moves, import updates, bib artifact extraction
- **Out of scope**: behavioral changes, new types, clustering moves (that's task-091)
- **Do not** change any detection logic

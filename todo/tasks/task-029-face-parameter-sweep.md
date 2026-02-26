# task-029: Face parameter sweep (bnr benchmark tune)

**Status:** pending
**Depends on:** task-027 (face detection in runner), task-028 (backend overrides)

## Goal

`bnr benchmark tune --config face_default.yaml` sweeps face detection parameters and
prints a ranked results table without saving benchmark runs.

## Changes

### `benchmarking/tuner.py` (new file)

```python
def run_face_sweep(
    param_grid: dict[str, list],   # e.g. {"FACE_DNN_CONFIDENCE_MIN": [0.2, 0.3, 0.4]}
    split: str,
    metric: str,                   # "face_f1" | "face_recall" | "face_precision"
    verbose: bool = True,
) -> list[dict]: ...

def load_tune_config(path: Path) -> dict: ...

def print_sweep_results(results: list[dict], metric: str) -> None: ...
```

`run_face_sweep()` implementation:
- Uses `itertools.product` over param_grid values.
- For each combo calls `get_face_backend_with_overrides(**combo)`.
- Runs face detection on all photos in split.
- Scores via `score_faces()`, collects `FaceScorecard`.
- Returns list of `{params, face_f1, face_precision, face_recall}` dicts sorted descending
  by metric.

### `benchmarking/tune_configs/face_default.yaml` (new file)

```yaml
params:
  FACE_DNN_CONFIDENCE_MIN: [0.2, 0.25, 0.3, 0.35, 0.4]
  FACE_DNN_NMS_IOU: [0.3, 0.4, 0.5]
split: iteration
metric: face_f1
```

### `benchmarking/cli/commands/tune.py` (new file)

Register `tune` subcommand in CLI parser.

CLI interface:
```
bnr benchmark tune --config benchmarking/tune_configs/face_default.yaml
bnr benchmark tune --params FACE_DNN_CONFIDENCE_MIN=0.2,0.3,0.4 --split iteration
```

Expected output:
```
Rank  FACE_DNN_CONFIDENCE_MIN  FACE_DNN_NMS_IOU  face_f1  face_P  face_R
   1  0.30                     0.40              78.5%    82.1%   75.2%
   2  0.25                     0.40              77.8%    79.3%   76.4%
Best: FACE_DNN_CONFIDENCE_MIN=0.30, FACE_DNN_NMS_IOU=0.40  (face_f1=78.5%)
```

## Tests

File: `tests/benchmarking/test_tuner.py`

- `test_face_sweep_returns_ranked_results()` — stub backend; assert results are sorted
  descending by the target metric.
- `test_load_tune_config_valid()` — parse a valid YAML; assert params/split/metric fields
  are present.
- `test_load_tune_config_missing_params()` — YAML without `params` key → assert `ValueError`.

## Scope boundary

- Face sweep only. No OCR caching. No bib sweep in this task.
- `bib_default.yaml` can be added as a later extension.

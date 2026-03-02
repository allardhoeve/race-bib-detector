# Task 063: Tuners package — shared protocol + GridTuner refactor

## Status: DONE

## Goal

Reorganise `benchmarking/tuner.py` into a `benchmarking/tuners/` package with a `Tuner` Protocol so that the grid sweep and future auto-tuner (task-066) share a common interface.

## What changed

| Action | File | What |
|--------|------|------|
| New | `benchmarking/tuners/__init__.py` | Re-exports: `Tuner`, `TunerResult`, `GridTuner`, `load_tune_config`, `print_sweep_results` |
| New | `benchmarking/tuners/protocol.py` | `Tuner` Protocol (runtime_checkable) + `TunerResult` (Pydantic BaseModel) |
| New | `benchmarking/tuners/grid.py` | `GridTuner` class + `load_tune_config` + `print_sweep_results` + `run_face_sweep` + `validate_on_full` (moved from `tuner.py`) |
| Deleted | `benchmarking/tuner.py` | Replaced by `tuners/grid.py` |
| Modified | `benchmarking/cli/commands/tune.py` | Import from `benchmarking.tuners.grid` |
| Moved | `tests/benchmarking/test_tuner.py` → `tests/benchmarking/test_tuners_grid.py` | Updated imports + patch paths |
| New | `tests/benchmarking/test_tuners_protocol.py` | Protocol + TunerResult tests |
| Modified | `todo/tasks/task-066-auto-tuner.md` | `auto_tuner.py` → `tuners/auto.py`, Tuner protocol conformance |

## Protocol

```python
class TunerResult(BaseModel):
    params: dict[str, Any]
    metrics: dict[str, float]

class Tuner(Protocol):
    def tune(self, *, split: str = ..., metric: str = ..., verbose: bool = ...) -> list[TunerResult]: ...
```

## Verification

```bash
venv/bin/python -m pytest tests/benchmarking/test_tuners_protocol.py tests/benchmarking/test_tuners_grid.py -v
venv/bin/python -m pytest  # full suite: 542 passed
```

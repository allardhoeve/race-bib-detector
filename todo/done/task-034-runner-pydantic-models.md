# Task 034: Migrate runner.py dataclasses to Pydantic

Extracted from task-033 sub-task A. Standalone.

## Goal

Remove ~300 lines of manual `to_dict` / `from_dict` boilerplate from the six dataclasses
in `benchmarking/runner.py` by converting them to `pydantic.BaseModel`.

## Background

The project already uses Pydantic (FastAPI + `benchmarking/schemas.py` +
`benchmarking/ground_truth.py`). These runner classes repeat the same serialization
pattern but are plain `@dataclass`. Converting them gives `.model_validate()` and
`.model_dump()` for free and removes hundreds of lines of mechanical code.

## Classes in scope

| Class | Lines | Notes |
|---|---|---|
| `PhotoResult` | 60–104 | Simple fields + defaults |
| `BenchmarkMetrics` | 107–148 | All required fields, no defaults |
| `PipelineConfig` | 151–187 | Has `summary()` method; `clahe_tile_size` tuple↔list |
| `FacePipelineConfig` | 190–245 | Has `summary()` + `summary_passes()`; empty-string fallback |
| `RunMetadata` | 248–308 | Nested optional configs |
| `BenchmarkRun` | 311–380 | Aggregates metadata + scorecards; has `save()` / `load()` |

## Approach

1. Replace `@dataclass` with `class Foo(BaseModel)`.
2. Replace every `cls.from_dict(data)` call-site with `Foo.model_validate(data)`.
3. Replace every `.to_dict()` call-site with `.model_dump()`.
4. Keep non-serialization methods (`summary()`, `summary_passes()`, `save()`, `load()`)
   — they remain as instance/class methods.

## Custom logic that needs explicit handling

These cases are not covered by Pydantic defaults; each needs a red test first:

**`PipelineConfig.clahe_tile_size`**
- Memory: `tuple[int, int] | None`
- JSON: list (JSON has no tuple type)
- Add `@field_serializer("clahe_tile_size")` to emit a list.
- Add `@field_validator("clahe_tile_size", mode="before")` to coerce a list → tuple on load.

**`FacePipelineConfig.fallback_backend`**
- Config layer can provide `""` (empty string) where `None` is semantically intended.
- Add `@field_validator("fallback_backend", mode="before")` to normalise `""` → `None`.

**`RunMetadata` nested configs**
- `pipeline_config: PipelineConfig | None` and `face_pipeline_config: FacePipelineConfig | None`
- Pydantic handles nested model validation automatically; no special logic needed.
- Verify with a round-trip test.

**`BenchmarkRun` scorecards**
- `bib_scorecard`, `face_scorecard`, `link_scorecard` come from `scoring.py`.
- If `scoring.py` classes are still plain dataclasses at this point, keep the manual
  construction in `BenchmarkRun.from_dict` / replace with a helper until task-037 lands.
- Document with a `# TODO task-037` comment.

## TDD constraint

- **Do not change existing tests** in `tests/test_runner.py`.
- Write red tests first in `tests/test_runner_models.py` (new file) for every custom
  serialization case listed above.
- Minimum required test cases:
  - `PipelineConfig` round-trips `clahe_tile_size` via `model_dump()` (list) and
    `model_validate()` (tuple).
  - `PipelineConfig` with `clahe_tile_size=None` round-trips cleanly.
  - `FacePipelineConfig` normalises `fallback_backend=""` → `None`.
  - `FacePipelineConfig` with a real `fallback_backend` value passes through unchanged.
  - `RunMetadata` with nested `pipeline_config` round-trips (dict → model → dict).
  - `RunMetadata` without optional fields round-trips cleanly.

## Files

- `benchmarking/runner.py` — convert dataclasses
- `tests/test_runner_models.py` — new, TDD tests only

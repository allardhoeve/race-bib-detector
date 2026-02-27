# Task status overview

_Last updated: 2026-02-27_

## Done

| Task | What |
|------|------|
| **027** | Wire face detection into benchmark runner (`runner.py` — `face_backend`, `FaceScorecard`, `face_gt` all wired) |

## Pending — feature pipeline

028 and 030 are unblocked leaf tasks. 029 and 031 follow them.

| Task | What | Blocked by |
|------|------|-----------|
| **028** | `get_face_backend_with_overrides()` in `faces/backend.py` | — |
| **029** | Face parameter sweep (`bnr benchmark tune`) + `benchmarking/tuner.py` | 028 |
| **030** | `faces/autolink.py` — rule-based bib-face pair predictor | — |
| **031** | Wire autolink into runner (replace stub `LinkScorecard(link_tp=0)`) | 030 |

## Pending — refactoring cluster

034 and 035 are independent of each other and can be parallelised. 037 should not run
concurrently with 034 (same Pydantic migration patterns — risk of conflicting approach).

| Task | What | Blocked by |
|------|------|-----------|
| **032** | Type clarity: replace `list[dict]` with domain types in service + schema layers | — |
| **034** | Migrate `runner.py` dataclasses to Pydantic | — |
| **035** | Split `_run_detection_loop` into `_run_bib_detection` + `_run_face_detection` (TDD) | — |
| **036** | Docstrings + inline comments for `runner.py` | 034, 035 |
| **037** | Pydantic migration across codebase (scoring, ghost, sets, face_embeddings, faces/types, detection/types) | after 034 |

## Dependency graph

```
028 → 029
030 → 031

034 ┐
035 ┤→ 036 → 037

032  (fully independent)
```

## Key gap

`LinkScorecard` is still stub (`link_tp=0`). Cleared by task-031, which requires task-030 first.

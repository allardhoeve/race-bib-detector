# Task 099: Promote private functions to public API

## Context

Many `_`-prefixed functions have outgrown their private status. They are imported cross-module, tested directly in external test files, or re-exported in `__all__` — contradicting the underscore convention. This task renames them to match their actual role and fills test gaps.

Dead code (`_candidates_to_face_boxes`) is also cleaned up.

---

## Step 1 — Constants & helpers already re-exported publicly

These have underscore names but are explicitly in `pipeline/__init__.py` `__all__` and imported by multiple modules. Pure naming contradiction.

| Symbol | File | Importers |
|--------|------|-----------|
| `_BIB_BOX_UNSCORED` → `BIB_BOX_UNSCORED` | `pipeline/types.py:23` | `pipeline/__init__.py`, `benchmarking/scoring.py`, `benchmarking/ground_truth.py`, `tests/test_pipeline_types.py`, `docs/BENCHMARK_DESIGN.md` |
| `_FACE_SCOPE_COMPAT` → `FACE_SCOPE_COMPAT` | `pipeline/types.py:30` | `pipeline/__init__.py`, `benchmarking/ground_truth.py`, `tests/test_pipeline_types.py`, `docs/BENCHMARK_DESIGN.md` |
| `_torso_region` → `torso_region` | `pipeline/types.py:287` | `benchmarking/link_analysis.py`, `tests/test_pipeline_types.py`, `docs/TUNING.md` |

**Action**: Rename (drop `_`). Update all import sites, `__all__`, docs, and internal call sites. Add `torso_region` to `pipeline/__init__.py` exports.

Internal call site in `pipeline/types.py:356` (`predict_links`) also uses `_torso_region` — update.

Internal reference in `pipeline/types.py:225` (`FaceBox._migrate_scope_compat`) uses `_FACE_SCOPE_COMPAT` — update.

## Step 2 — Runner functions tested externally

Only called from `run_benchmark()` but imported directly by test files — de facto public API.

| Function | File | Tests |
|----------|------|-------|
| `_run_detection_loop` → `run_detection_loop` | `benchmarking/runner.py:452` | `tests/test_runner.py`, `tests/benchmarking/test_runner_links.py` |
| `_select_photo_hashes` → `select_photo_hashes` | `benchmarking/runner.py:687` | `tests/test_photo_ordering.py` |
| `_assign_face_clusters` → `assign_face_clusters` | `benchmarking/runner.py:398` | `tests/test_face_clustering_runner.py` |
| `_evaluate_single_combo` → `evaluate_single_combo` | `benchmarking/tuners/grid.py:268` | `tests/benchmarking/test_tuners_grid.py` |

**Action**: Rename (drop `_`). Update test imports and internal call sites.

Internal call sites:
- `runner.py:601` calls `_assign_face_clusters`
- `runner.py:746` calls `_select_photo_hashes`
- `runner.py:771` calls `_run_detection_loop`
- `tuners/grid.py:402,405` calls `_evaluate_single_combo`
- `tuners/grid.py:505` mock patch reference `f"{_PATCH_PREFIX}._evaluate_single_combo"`

**Note on task-091 overlap**: Task-091 plans to delete `_assign_face_clusters` and move `_cluster_embeddings` to `pipeline/cluster.py`. If task-091 runs first, those items are absorbed. If this task runs first, just rename in place.

## Step 3 — Cross-module import of private clustering code

| Symbol | File | Cross-module importer |
|--------|------|-----------------------|
| `_cluster_embeddings` → `cluster_embeddings` | `faces/clustering.py:59` | `benchmarking/runner.py:405` |

`_UnionFind` stays private, no separate tests needed.

**Action**: Rename `_cluster_embeddings` → `cluster_embeddings`. Add docstring. Update internal call site at `faces/clustering.py:132`. Update cross-module import at `benchmarking/runner.py:405`.

Add unit tests in new file `tests/test_clustering.py`:
- Empty input → empty result
- Single embedding → one cluster of size 1
- Two identical embeddings → same cluster
- Two orthogonal embeddings → separate clusters
- Threshold boundary (distance exactly at threshold)

## Step 4 — Test gaps for functions being promoted

### `torso_region` — **undertested** (import test only, no value assertions)
Current coverage: one test (`test_pipeline_types.py:66`) confirms it's importable and returns positive w/h. No tests verify actual coordinate math.

Add tests in `tests/test_pipeline_types.py`:
- Face centered in image → torso region below face at expected offset
- Face near top edge → torso extends downward correctly
- Verify returned (x, y, w, h) against config constants `AUTOLINK_TORSO_TOP`, `AUTOLINK_TORSO_BOTTOM`, `AUTOLINK_TORSO_HALF_WIDTH`

### `_run_face_fallback_chain` — **undertested** (2 basic tests, 62 lines of two-phase logic)
Current tests: `test_pipeline.py:TestFaceFallbackChain` has two integration tests (full pipeline). No unit tests of `_run_face_fallback_chain` directly.

Add tests in `tests/test_pipeline.py`:
- Phase 1 (DNN low-confidence): candidates below `FACE_DNN_FALLBACK_CONFIDENCE_MIN` rejected, sorted by confidence, `FACE_DNN_FALLBACK_MAX` limit applied
- Phase 2 (backend fallback): IoU dedup filters overlapping detections, `FACE_FALLBACK_MAX` limit applied
- `fallback_face_backend=None` skips phase 2
- Both phases in sequence (phase 1 finds some, phase 2 adds more)

### `_build_bib_trace` — **adequately tested** (4 tests)
Add one gap:
- `img_w=0` or `img_h=0` returns empty (the guard clause at `single_photo.py:75`)

### `_evaluate_single_combo` — **undertested** (3 direct tests)
Add tests in `tests/benchmarking/test_tuners_grid.py`:
- Empty split (no photos) → still returns a result dict
- All GT faces have zero predicted faces → precision=0, recall=0

### `_run_detection_loop` — **adequate** (12 tests). No blocking gaps.
### `_select_photo_hashes` — **well-tested** (7 tests). No gaps.
### `_assign_face_clusters` — **adequate** (6 tests). No gaps.

## Step 5 — Dead code removal

| Function | File | Evidence |
|----------|------|----------|
| `_candidates_to_face_boxes` | `pipeline/single_photo.py:142` | Grep: only the definition at lines 142-160, zero call sites |

**Action**: Delete lines 142-160.

## Files to modify

| File | Changes |
|------|---------|
| `pipeline/types.py` | Rename 3 symbols (`_BIB_BOX_UNSCORED`, `_FACE_SCOPE_COMPAT`, `_torso_region`), update internal refs |
| `pipeline/__init__.py` | Update imports and `__all__`, add `torso_region` |
| `pipeline/single_photo.py` | Delete `_candidates_to_face_boxes` (lines 142-160) |
| `benchmarking/runner.py` | Rename 3 functions, update internal calls, update `_cluster_embeddings` import |
| `benchmarking/tuners/grid.py` | Rename 1 function, update internal calls + mock patch string |
| `benchmarking/scoring.py` | Update `_BIB_BOX_UNSCORED` → `BIB_BOX_UNSCORED` (line 18, 334) |
| `benchmarking/ground_truth.py` | Update 2 imports and 1 usage (lines 24, 26, 92) |
| `benchmarking/link_analysis.py` | Update `_torso_region` import + docstring + print string (lines 4, 23, 32, 33, 137) |
| `faces/clustering.py` | Rename `_cluster_embeddings` → `cluster_embeddings`, add docstring (line 59), update internal call (line 132) |
| `tests/test_runner.py` | `_run_detection_loop` → `run_detection_loop` (line 21) |
| `tests/test_runner_models.py` | Check/update — currently no private symbol imports |
| `tests/benchmarking/test_runner_links.py` | `_run_detection_loop` → `run_detection_loop` (lines 1, 18, 88, 118, 140) |
| `tests/test_photo_ordering.py` | `_select_photo_hashes` → `select_photo_hashes` (lines 5, 17, 74, 85, 100, 114, 134, 144) |
| `tests/test_face_clustering_runner.py` | `_assign_face_clusters` → `assign_face_clusters` (lines 1, 12, 54, 59, 67, 79, 90, 96) |
| `tests/benchmarking/test_tuners_grid.py` | `_evaluate_single_combo` → `evaluate_single_combo` (lines 14, 199, 203, 204, 210, 219, 226, 472, 473, 484, 497, 505) |
| `tests/test_pipeline_types.py` | Update 3 imports + add `torso_region` value tests |
| `tests/test_pipeline.py` | Add `_build_bib_trace` zero-dimensions test, add `_run_face_fallback_chain` unit tests |
| `tests/test_clustering.py` | **New** — 5 unit tests for `cluster_embeddings` |
| `docs/BENCHMARK_DESIGN.md` | Update 3 name references |
| `docs/TUNING.md` | Update `_torso_region` reference |
| `todo/tasks/` | Update references in task-086, 089, 090, 091 |

## Verification

```bash
# Run full test suite
venv/bin/python -m pytest

# Grep for any remaining underscore references to renamed symbols
grep -rn '_BIB_BOX_UNSCORED\|_FACE_SCOPE_COMPAT\|_torso_region\|_run_detection_loop\|_select_photo_hashes\|_assign_face_clusters\|_evaluate_single_combo\|_cluster_embeddings\|_candidates_to_face_boxes' --include='*.py' .
```

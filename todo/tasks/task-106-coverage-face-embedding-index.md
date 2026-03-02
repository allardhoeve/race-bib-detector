# Task 106: Test coverage for face embedding index assembly

Depends on nothing. Deferred priority — tackle after tasks 100-105.

**TDD approach: `tdd: test-wrap`**

## Goal

Cover `benchmarking/face_embeddings.py` `build_embedding_index` assembly logic (57% coverage). The coordinate conversion and index construction can be tested with a mock embedder, without requiring real ML models or photos.

## Background

Coverage analysis (2026-03-02) found `build_embedding_index` (lines 64-119) untested. While it loads photos and calls an embedder, the index assembly logic (normalised-coord-to-pixel conversion, stacking embeddings, handling empty case) is testable with a simple mock.

## Context

- `benchmarking/face_embeddings.py` — `build_embedding_index()`, `EmbeddingIndex`
- `benchmarking/ground_truth.py` — `FaceGroundTruth`, `FaceBox` (test fixtures needed)
- `faces/types.py` — `FaceModelInfo` (mock embedder returns this)
- `find_top_k` is already well-tested at lines 127-180

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Mock embedder? | Create a simple object with `embed(image, bboxes)` returning random vectors and `model_info()` returning a FaceModelInfo |
| Test images? | Write small JPEG files to `tmp_path` |

## Tests

### New: `tests/benchmarking/test_face_embeddings_index.py`

- `test_build_index_with_labeled_faces()` — builds index from GT with identities, returns correct size
- `test_build_index_skips_non_keep_scope()` — boxes with scope != "keep" excluded
- `test_build_index_skips_no_identity()` — boxes without identity excluded
- `test_build_index_empty_gt()` — no labeled faces returns empty index with correct dim
- `test_build_index_missing_photo()` — photo not on disk is skipped gracefully

## Acceptance criteria

- [ ] All existing tests still pass (`venv/bin/python -m pytest`)
- [ ] `build_embedding_index` coverage >= 80%
- [ ] Mock embedder used — no real ML model required
- [ ] Empty-index edge case covered

## Scope boundaries

- **In scope**: `build_embedding_index` assembly and edge cases
- **Out of scope**: `find_top_k` (already covered), actual embedding quality
- **Do not** require real model files or GPU

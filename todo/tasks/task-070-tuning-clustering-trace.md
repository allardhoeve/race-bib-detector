# Task 070: Clustering trace — per-face diagnostic distances

Part of the tuning series. Prerequisite for task-068 (refinement loop).

**Depends on:** task-069 (split embedding from clustering)

## Goal

Write clustering diagnostic fields back onto `FaceCandidateTrace` so each face records how well it fits its cluster and how ambiguous its assignment was. This completes the face trace from detection through clustering.

## Background

After task-069, `cluster_with_diagnostics()` returns a `ClusterResult` with per-face `ClusterAssignment` (cluster_id, cluster_distance, nearest_other_distance). This task writes those values onto `FaceCandidateTrace` and stores them in the benchmark JSON.

This closes the diagnostic gap: you can now look at any face in a benchmark run and see its complete journey — detection confidence, filtering outcome, embedding, cluster assignment, and how confident that assignment was.

## Design decisions

| Question | Decision |
|----------|----------|
| Where to store? | On `FaceCandidateTrace` — keeps the full journey in one place |
| Which fields? | `cluster_id`, `cluster_distance`, `nearest_other_distance` |
| Rejected faces? | All three fields remain `None` — they were never embedded or clustered |
| Singleton clusters? | `cluster_distance = 0.0`, `nearest_other_distance` = distance to nearest other centroid (or `None` if only one cluster exists) |

## Context

- `faces/clustering.py` — `ClusterResult`, `ClusterAssignment` (from task-069)
- `benchmarking/runner.py` — `FaceCandidateTrace`, `_assign_face_clusters()`
- `benchmarking/runner.py:675-677` — where `_assign_face_clusters()` is called in the detection loop

## Test-first approach

### Extend `tests/test_runner_models.py`

```python
class TestFaceCandidateTraceClustering:
    def test_cluster_fields_round_trip(self):
        """Trace with cluster_id, cluster_distance, nearest_other_distance serialises."""

    def test_cluster_fields_default_none(self):
        """Trace without clustering fields loads with None defaults."""

    def test_rejected_face_has_no_cluster_fields(self):
        """Rejected face trace has all cluster fields as None."""
```

### Extend `tests/test_face_embedding_trace.py` (from task-069)

```python
def test_assign_clusters_writes_diagnostics_to_trace():
    """After clustering, accepted face traces have cluster_id and distances."""

def test_singleton_cluster_distance_is_zero():
    """A face alone in its cluster has cluster_distance=0.0."""

def test_ambiguous_face_has_small_nearest_other_distance():
    """A face equidistant between two clusters has small nearest_other_distance."""
```

## Changes

### Modified: `benchmarking/runner.py`

Add clustering fields to `FaceCandidateTrace`:

```python
class FaceCandidateTrace(BaseModel):
    ...existing fields...

    # Clustering stage (None if not embedded/clustered)
    cluster_id: int | None = None
    cluster_distance: float | None = None
    nearest_other_distance: float | None = None
```

Update `_assign_face_clusters()` to write diagnostics from `ClusterResult`:

```python
cluster_result = cluster_with_diagnostics(emb_matrix, threshold)
for (p_idx, f_idx), assignment in zip(face_refs, cluster_result.assignments):
    trace = photo_results[p_idx].face_trace[f_idx]
    trace.cluster_id = assignment.cluster_id
    trace.cluster_distance = assignment.cluster_distance
    trace.nearest_other_distance = assignment.nearest_other_distance
    # Also update pred_face_boxes for backward compat
    photo_results[p_idx].pred_face_boxes[f_idx].cluster_id = assignment.cluster_id
```

## Verification

```bash
venv/bin/python -m pytest tests/test_runner_models.py::TestFaceCandidateTraceClustering -v
venv/bin/python -m pytest tests/test_face_embedding_trace.py -v
venv/bin/python -m pytest  # full suite
```

## Acceptance criteria

- [ ] `FaceCandidateTrace` has `cluster_id`, `cluster_distance`, `nearest_other_distance`
- [ ] `_assign_face_clusters()` writes all three from `ClusterResult`
- [ ] Rejected/unembedded faces have `None` for all cluster fields
- [ ] Backward compat: old JSON without cluster fields loads with `None`
- [ ] TDD tests pass
- [ ] All existing tests pass

## Scope boundaries

- **In scope**: trace fields, write-back from ClusterResult, tests
- **Out of scope**: changing clustering algorithm, refinement loop (task-068), scaling
- **Do not** change clustering behavior — only capture its output

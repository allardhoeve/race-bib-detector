# Task 091: `pipeline/cluster.py` — unified clustering with trace enrichment

Part of the tuning series (085-094). Replaces the earlier clustering-trace task and absorbs parts of the earlier embedding-split task.

**Depends on:** task-090 (embedding in pipeline)

## Goal

Create `pipeline/cluster.py` with a single `cluster()` function that both production and benchmarking call. Move the clustering algorithm out of `faces/clustering.py` into the pipeline layer. Write cluster diagnostics onto `FaceCandidateTrace` in-place.

## Background

Currently clustering exists in two places:
- **Benchmarking**: `_assign_face_clusters()` in `runner.py` — reads embeddings (post-074: from traces), calls `_cluster_embeddings()`, writes `cluster_id` onto `pred_face_boxes`
- **Production**: `cluster_album_faces()` in `faces/clustering.py` — loads from DB, clusters, computes centroid/similarity, writes to DB

Same algorithm, different wrappers, different capabilities (production computes diagnostics, benchmark doesn't). After this task: one `cluster()` function with full diagnostics always.

## Design decisions

| Question | Decision |
|----------|----------|
| Function name | `cluster()` — no "with_diagnostics" suffix. Everything always returns full results. |
| Where | `pipeline/cluster.py` — clustering is a pipeline phase, not a detection concern |
| Input | `list[FaceCandidateTrace]` — reads embeddings from traces |
| Output | Mutates traces in-place: writes `cluster_id`, `cluster_distance`, `nearest_other_distance` |
| Algorithm | Same union-find single-linkage as today. `_cluster_embeddings()` and `_UnionFind` move here. |
| `cluster_album_faces()`? | Becomes a thin wrapper: load from DB → build traces → call `cluster()` → persist to DB |

## Context

- `faces/clustering.py` — `_cluster_embeddings()`, `_UnionFind`, `_normalize_embeddings()`, `cluster_album_faces()`
- `benchmarking/runner.py:_assign_face_clusters()` — to be replaced by `cluster()` call
- `pipeline/types.py:FaceCandidateTrace` — has `cluster_id`, `cluster_distance`, `nearest_other_distance` fields (None defaults)
- `config.py:FACE_CLUSTER_DISTANCE_THRESHOLD`

## Changes

### New: `pipeline/cluster.py`

```python
"""Phase 2: Cross-photo face clustering.

Reads embeddings from face traces, clusters by cosine distance,
and writes diagnostic fields back onto traces.
"""

from dataclasses import dataclass
import numpy as np
import config
from pipeline.types import FaceCandidateTrace

@dataclass
class ClusterResult:
    """Summary of a clustering run."""
    cluster_count: int
    face_count: int
    centroids: np.ndarray  # (K, D)

def cluster(
    face_traces: list[FaceCandidateTrace],
    distance_threshold: float | None = None,
) -> ClusterResult:
    """Cluster face embeddings and enrich traces in-place.

    Reads embedding from each trace, clusters by cosine distance,
    and writes cluster_id, cluster_distance, nearest_other_distance
    back onto each embedded trace.

    Both production and benchmarking call this function.
    """
    threshold = distance_threshold or config.FACE_CLUSTER_DISTANCE_THRESHOLD
    embedded = [(i, t) for i, t in enumerate(face_traces) if t.embedding is not None]
    if not embedded:
        return ClusterResult(cluster_count=0, face_count=0, centroids=np.empty((0, 0)))

    indices, traces = zip(*embedded)
    embeddings = np.stack([np.array(t.embedding, dtype=np.float32) for t in traces])

    # Cluster
    clusters = _cluster_embeddings(embeddings, threshold)
    normed = _normalize_embeddings(embeddings)

    # Compute centroids
    centroids = []
    for group in clusters:
        c = normed[group].mean(axis=0)
        c /= max(np.linalg.norm(c), 1e-8)
        centroids.append(c)
    centroid_matrix = np.stack(centroids) if centroids else np.empty((0, normed.shape[1]))

    # Write diagnostics onto traces
    for cluster_id, group in enumerate(clusters):
        own_dists = 1.0 - (normed[group] @ centroids[cluster_id])
        if len(centroids) > 1:
            other_mask = [i for i in range(len(centroids)) if i != cluster_id]
            other_dists = 1.0 - (normed[group] @ centroid_matrix[other_mask].T)
            nearest_other = other_dists.min(axis=1)
        else:
            nearest_other = np.full(len(group), float('inf'))

        for local_i, emb_i in enumerate(group):
            trace = face_traces[indices[emb_i]]
            trace.cluster_id = cluster_id
            trace.cluster_distance = float(own_dists[local_i])
            trace.nearest_other_distance = float(nearest_other[local_i])

    return ClusterResult(
        cluster_count=len(clusters),
        face_count=len(embedded),
        centroids=centroid_matrix,
    )

# --- Internal helpers (moved from faces/clustering.py) ---

class _UnionFind: ...
def _normalize_embeddings(embeddings): ...
def _cluster_embeddings(embeddings, threshold): ...
```

### Modified: `benchmarking/runner.py`

Replace `_assign_face_clusters()` with:

```python
from pipeline.cluster import cluster

# In _run_detection_loop, after the photo loop:
if face_backend is not None:
    all_face_traces = []
    for result in photo_results:
        if result.face_trace:
            all_face_traces.extend(result.face_trace)
    cluster(all_face_traces)
```

Delete `_assign_face_clusters()`.

### Modified: `faces/clustering.py`

`cluster_album_faces()` becomes a thin DB wrapper:

```python
from pipeline.cluster import cluster
from pipeline.types import FaceCandidateTrace

def cluster_album_faces(conn, album_id, distance_threshold=None):
    # Load embeddings from DB
    rows = db.list_face_embeddings_for_album(conn, album_id)
    # Build FaceCandidateTrace objects from DB records
    traces = [_db_row_to_trace(row) for row in rows]
    # Call shared cluster()
    result = cluster(traces, distance_threshold)
    # Persist cluster assignments back to DB
    _save_clusters_to_db(conn, album_id, traces, result)
```

Remove `_cluster_embeddings`, `_UnionFind`, `_normalize_embeddings` (moved to pipeline/cluster.py).

### Modified: `pipeline/__init__.py`

Add `cluster` to re-exports.

## Tests

New: `tests/test_pipeline_cluster.py`

```python
def test_cluster_writes_diagnostics_to_traces():
    """cluster() populates cluster_id, cluster_distance, nearest_other_distance."""

def test_cluster_empty_traces():
    """cluster() with no embedded traces returns empty result."""

def test_cluster_singleton():
    """Single face gets cluster_id=0, cluster_distance=0.0."""

def test_cluster_two_groups():
    """Two distinct embedding groups get separate cluster_ids."""

def test_nearest_other_distance_meaningful():
    """A face equidistant between clusters has small nearest_other_distance."""

def test_unembedded_traces_unchanged():
    """Traces without embeddings keep None cluster fields."""

def test_cluster_result_summary():
    """ClusterResult has correct cluster_count and face_count."""
```

## Verification

```bash
venv/bin/python -m pytest tests/test_pipeline_cluster.py -v
venv/bin/python -m pytest
```

## Pitfalls

- **Production `cluster_album_faces` divergence**: The DB wrapper needs to build `FaceCandidateTrace` from DB rows (face_id, embedding bytes, model info). This is a new conversion path. Keep it thin — only populate the fields `cluster()` reads (embedding) and writes (cluster_id, distances).
- **DB similarity fields**: Production stores `avg_similarity`, `min_similarity`, `max_similarity` per cluster and `distance` per member. These can be derived from `ClusterResult` + trace diagnostics.
- **Import cycle risk**: `pipeline/cluster.py` imports from `pipeline/types.py`. `faces/clustering.py` imports from `pipeline/cluster.py`. No cycle as long as `pipeline/` doesn't import from `faces/`.

## Acceptance criteria

- [ ] `pipeline/cluster.py` exists with `cluster()` function
- [ ] `cluster()` writes `cluster_id`, `cluster_distance`, `nearest_other_distance` onto traces
- [ ] `_assign_face_clusters()` deleted from runner.py
- [ ] `cluster_album_faces()` uses `cluster()` internally
- [ ] Clustering internals (`_UnionFind`, `_cluster_embeddings`) moved to `pipeline/cluster.py`
- [ ] Both production and benchmarking call the same `cluster()` function
- [ ] TDD tests pass
- [ ] All existing tests pass

## Scope boundaries

- **In scope**: pipeline/cluster.py, consumer migration, production wrapper update
- **Out of scope**: changing clustering algorithm, refinement loop (task-093)
- **Do not** change clustering behavior — only restructure where the code lives

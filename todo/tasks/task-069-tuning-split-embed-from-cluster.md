# Task 069: Split embedding (single-photo) from clustering (cross-photo)

Part of the tuning series. Structural prerequisite for task-068 (refinement loop) and task-070 (clustering trace).

**Depends on:** task-067 (face candidate trace)

## Goal

Move face embedding into the single-photo pipeline and make clustering a pure cross-photo function that reads embeddings from traces. Unify the benchmark and production clustering paths around a shared core.

## Background

Today `_assign_face_clusters()` in `runner.py` does three things in one function:

1. Decode images (3rd time per photo)
2. Crop and embed each accepted face
3. Cluster all embeddings and assign cluster IDs

Steps 1-2 are single-photo work. Step 3 is cross-photo work. They're tangled because embeddings aren't stored — they must be computed and clustered in one pass, then discarded.

Meanwhile, the production path (`cluster_album_faces()` in `clustering.py`) does the same clustering but loads embeddings from the database and computes richer diagnostics (centroid, avg/min/max similarity, per-member distance). The benchmark path computes none of this.

Two problems:
- **Structural**: embedding and clustering are conflated, preventing the refinement loop from re-clustering without re-embedding
- **Divergence**: benchmark and production use different code for the same operation, with different capabilities

## Design decisions

| Question | Decision |
|----------|----------|
| Where to embed? | In `_run_face_detection()`, right after detection. The image is already decoded. |
| Where to store embeddings? | On `FaceCandidateTrace` for accepted candidates. ~2KB per face (512 float32). |
| Serialize embeddings? | Yes, as list[float] in JSON. Needed for re-clustering in refinement loop. |
| Shared clustering core? | Extract `_cluster_embeddings()` + centroid/distance computation into a function both paths use. |
| What does clustering return? | A `ClusterResult` with assignments + per-face diagnostics. No in-place mutation. |

## Context

- `benchmarking/runner.py:496-547` — `_assign_face_clusters()` (to be split)
- `benchmarking/runner.py:461-493` — `_run_face_detection()` (embed here)
- `faces/clustering.py:59-78` — `_cluster_embeddings()` (shared core, keep)
- `faces/clustering.py:89-180` — `cluster_album_faces()` (production path, align)
- `faces/embedder.py` — `FaceEmbedder` protocol, `get_face_embedder()`
- `config.py:130` — `FACE_EMBEDDER = "facenet"`, `FACE_CLUSTER_DISTANCE_THRESHOLD = 0.30`

## Test-first approach

### New: `tests/test_face_embedding_trace.py`

```python
def test_accepted_face_has_embedding_on_trace():
    """After _run_face_detection, accepted faces in face_trace have embeddings."""

def test_rejected_face_has_no_embedding():
    """Rejected faces in face_trace have embedding=None."""

def test_embedding_round_trip():
    """Embedding serialises to JSON and deserialises back to equivalent array."""

def test_cluster_result_from_embeddings():
    """cluster_faces() takes embeddings, returns ClusterResult with diagnostics."""

def test_cluster_result_per_face_distances():
    """Each face in ClusterResult has cluster_distance and nearest_other_distance."""

def test_assign_face_clusters_uses_trace_embeddings():
    """_assign_face_clusters reads embeddings from traces, not images."""
```

Mark tests that need real embedder/images as `@pytest.mark.slow`.

## Changes

### Modified: `benchmarking/runner.py`

**Add embedding field to `FaceCandidateTrace`:**

```python
class FaceCandidateTrace(BaseModel):
    ...existing fields from task-067...

    # Embedding (None if rejected before embedding)
    embedding: list[float] | None = None
```

**Move embedding into `_run_face_detection()`:**

The image is already decoded here. After building `pred_face_boxes` and `face_trace`, embed accepted faces:

```python
embedder = get_face_embedder()
# ... crop accepted faces, embed them ...
for trace_entry, emb_vector in zip(accepted_traces, embeddings):
    trace_entry.embedding = emb_vector.tolist()
```

**Refactor `_assign_face_clusters()` to read from traces:**

```python
def _assign_face_clusters(photo_results, distance_threshold=None):
    """Cluster faces using embeddings from face traces. No image access needed."""
    all_embeddings = []
    face_refs = []
    for p_idx, result in enumerate(photo_results):
        if not result.face_trace:
            continue
        for f_idx, trace in enumerate(result.face_trace):
            if trace.embedding is not None:
                all_embeddings.append(np.array(trace.embedding, dtype=np.float32))
                face_refs.append((p_idx, f_idx))

    if not all_embeddings:
        return

    cluster_result = cluster_faces(np.stack(all_embeddings), threshold)
    # Write back cluster_id to traces and pred_face_boxes
```

**Remove `image_cache` parameter** — no longer needed.

### Modified: `faces/clustering.py`

**Extract shared clustering-with-diagnostics function:**

```python
@dataclass
class ClusterAssignment:
    """Per-face clustering result."""
    cluster_id: int
    cluster_distance: float          # cosine distance to own centroid
    nearest_other_distance: float    # distance to nearest other centroid

@dataclass
class ClusterResult:
    """Complete clustering output."""
    assignments: list[ClusterAssignment]  # one per input face
    cluster_count: int
    centroids: np.ndarray                 # (K, D) array of cluster centroids

def cluster_with_diagnostics(
    embeddings: np.ndarray,
    distance_threshold: float,
) -> ClusterResult:
    """Cluster embeddings and compute per-face diagnostic distances."""
    clusters = _cluster_embeddings(embeddings, distance_threshold)
    normed = _normalize_embeddings(embeddings)

    # Compute centroids
    centroids = []
    for indices in clusters:
        centroid = normed[indices].mean(axis=0)
        centroid /= max(np.linalg.norm(centroid), 1e-8)
        centroids.append(centroid)
    centroid_matrix = np.stack(centroids)

    # Per-face distances
    assignments = []
    for cluster_id, indices in enumerate(clusters):
        face_embeddings = normed[indices]
        own_distances = 1.0 - (face_embeddings @ centroids[cluster_id])

        # Distance to all other centroids
        if len(centroids) > 1:
            other_mask = [i for i in range(len(centroids)) if i != cluster_id]
            other_centroids = centroid_matrix[other_mask]
            other_distances = 1.0 - (face_embeddings @ other_centroids.T)
            nearest_other = other_distances.min(axis=1)
        else:
            nearest_other = np.full(len(indices), float('inf'))

        for i, idx in enumerate(indices):
            assignments.append((idx, ClusterAssignment(
                cluster_id=cluster_id,
                cluster_distance=float(own_distances[i]),
                nearest_other_distance=float(nearest_other[i]),
            )))

    # Sort by original index
    assignments.sort(key=lambda x: x[0])
    return ClusterResult(
        assignments=[a for _, a in assignments],
        cluster_count=len(clusters),
        centroids=centroid_matrix,
    )
```

**Update `cluster_album_faces()` to use `cluster_with_diagnostics()`** — replace the inline centroid/similarity computation with the shared function.

### Modified: `_run_detection_loop()`

Remove `image_cache` parameter from `_assign_face_clusters()` call. The function now reads embeddings from traces.

## Verification

```bash
venv/bin/python -m pytest tests/test_face_embedding_trace.py -v
venv/bin/python -m pytest  # full suite
```

## Pitfalls

- **Embedding serialization cost**: 512 floats as JSON list is verbose (~4KB). For a 100-photo benchmark run with 3 faces per photo, that's ~1.2MB extra in the JSON — acceptable. If it becomes a concern, consider base64 encoding.
- **Embedder initialization**: `get_face_embedder()` loads a model (FaceNet). Currently called once in `_assign_face_clusters()`. Moving it into per-photo detection means either passing the embedder in or initializing it once in the detection loop.
- **Image already decoded**: `_run_face_detection()` already decodes the image. Embedding needs the RGB image + pixel-space bounding boxes. Both are available — just need to crop and embed before the function returns.
- **Backward compat**: old benchmark JSON without `embedding` field loads fine (`None` default).

## Acceptance criteria

- [ ] Face embedding happens in `_run_face_detection()`, not `_assign_face_clusters()`
- [ ] `FaceCandidateTrace.embedding` stores the vector for accepted faces
- [ ] `_assign_face_clusters()` reads embeddings from traces, doesn't touch images
- [ ] `cluster_with_diagnostics()` is a shared function used by both benchmark and production paths
- [ ] `cluster_album_faces()` updated to use the shared function
- [ ] TDD tests pass
- [ ] All existing tests pass

## Scope boundaries

- **In scope**: move embedding, refactor clustering, shared core, trace field, tests
- **Out of scope**: clustering trace fields on `FaceCandidateTrace` (task-070), refinement loop (task-068), scaling optimizations
- **Do not** change detection behavior or clustering algorithm

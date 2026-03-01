# Task 051: Wire face embedding + clustering as benchmark post-processing

Depends on task-050. Can be deferred without blocking tasks 052/053.

## Goal

After face detection in the benchmark loop, compute face embeddings for predicted face boxes and cluster them, storing a `cluster_id` on each predicted `FaceBox`. This lets the inspect page colour-code faces that the system believes belong to the same person.

## Background

The project already has face embedding (`faces/embedder.py`) and clustering (`faces/clustering.py`) infrastructure, but these are wired to the production DB path (`cluster_album_faces`). For benchmark inspect, we need a lightweight in-memory version: embed all predicted faces across the run, cluster them, and annotate each `FaceBox` with its cluster assignment.

## Context

- `faces/embedder.py` — `FaceEmbedder` protocol, `PixelEmbedder`, `FaceNetEmbedder`, `get_face_embedder()`
- `faces/clustering.py` — `_cluster_embeddings(embeddings, distance_threshold)` returns `list[list[int]]` (list of index groups)
- `benchmarking/runner.py:444` — `_run_detection_loop()` — where predictions are accumulated
- `benchmarking/ground_truth.py:200` — `FaceBox(BaseModel)` — current fields: x, y, w, h, scope, identity, tags
- `config.py` — `FACE_CLUSTER_DISTANCE_THRESHOLD`, `FACE_EMBEDDER`

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Where to run clustering? | Post-processing step after the detection loop, before returning results. New helper `_assign_face_clusters()` in `runner.py` |
| Cluster ID storage | Add optional `cluster_id: int | None = None` field to `FaceBox`. Cluster IDs are run-scoped integers starting at 0 |
| Embedding model | Use the configured embedder (`get_face_embedder()`). Same model as production |
| Scope | Only predicted face boxes (`pred_face_boxes`), not GT boxes. GT faces already have `identity` |
| Performance | Embedding ~500 faces takes ~2-5s with FaceNet. Acceptable as a one-time post-processing step |
| Image access | Need to re-decode images for embedding. Pass `(content_hash, image_data)` pairs to the post-processor, or cache in the loop |

## Changes

### Modified: `benchmarking/ground_truth.py`

Add `cluster_id` field to `FaceBox`:

```python
class FaceBox(BaseModel):
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    scope: str = "keep"
    identity: str | None = None
    tags: list[str] = Field(default_factory=list)
    cluster_id: int | None = None  # assigned by benchmark clustering
```

### Modified: `benchmarking/runner.py`

Add helper function and call it after the detection loop:

```python
def _assign_face_clusters(
    photo_results: list[PhotoResult],
    image_cache: dict[str, bytes],
    distance_threshold: float | None = None,
) -> None:
    """Embed predicted faces and assign cluster IDs in-place."""
    from faces.embedder import get_face_embedder
    from faces.clustering import _cluster_embeddings

    embedder = get_face_embedder()
    # Collect all (photo_idx, face_idx, embedding) triples
    all_embeddings = []
    face_refs = []  # (photo_idx, face_idx) for mapping back

    for p_idx, result in enumerate(photo_results):
        if not result.pred_face_boxes:
            continue
        image_data = image_cache.get(result.content_hash)
        if not image_data:
            continue
        # Decode image for embedding
        img_array = cv2.imdecode(
            np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR
        )
        if img_array is None:
            continue
        image_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
        h, w = image_rgb.shape[:2]
        # Convert normalised FaceBox coords to FaceBbox polygons for embedder
        bboxes = []
        for f_idx, fbox in enumerate(result.pred_face_boxes):
            if fbox.x is None or fbox.w is None:
                continue
            x1 = int(fbox.x * w)
            y1 = int(fbox.y * h)
            x2 = int((fbox.x + fbox.w) * w)
            y2 = int((fbox.y + fbox.h) * h)
            bboxes.append(((x1, y1), (x2, y1), (x2, y2), (x1, y2)))
            face_refs.append((p_idx, f_idx))

        if bboxes:
            embeddings = embedder.embed(image_rgb, bboxes)
            all_embeddings.extend(embeddings)

    if not all_embeddings:
        return

    import numpy as np
    emb_matrix = np.stack(all_embeddings).astype(np.float32)
    threshold = distance_threshold or config.FACE_CLUSTER_DISTANCE_THRESHOLD
    clusters = _cluster_embeddings(emb_matrix, threshold)

    # Assign cluster IDs back to FaceBox objects
    for cluster_id, indices in enumerate(clusters):
        for idx in indices:
            p_idx, f_idx = face_refs[idx]
            photo_results[p_idx].pred_face_boxes[f_idx].cluster_id = cluster_id
```

In `_run_detection_loop`, cache image bytes and call `_assign_face_clusters` after the loop:

```python
# At top of loop: cache image data
image_cache: dict[str, bytes] = {}
# Inside loop, after reading image_data:
image_cache[label.content_hash] = image_data
# After loop, before returning:
if face_backend is not None:
    _assign_face_clusters(photo_results, image_cache)
```

## Tests

Add `tests/test_face_clustering_runner.py`:

- `test_assign_face_clusters_empty()` — no photos → no crash
- `test_assign_face_clusters_assigns_ids()` — mock embedder, verify cluster_id is set on FaceBox
- `test_assign_face_clusters_groups_similar()` — two identical embeddings → same cluster_id
- `test_cluster_id_none_without_clustering()` — FaceBox.cluster_id defaults to None

Extend `tests/test_pydantic_migration.py`:

- `test_facebox_cluster_id_field()` — FaceBox accepts and roundtrips cluster_id

## Verification

```bash
venv/bin/python -m pytest tests/test_face_clustering_runner.py tests/test_pydantic_migration.py -v
```

## Pitfalls

- `_cluster_embeddings` is currently a module-private function (leading underscore). Either make it public or import it explicitly — the leading underscore is a convention, not enforcement.
- Image cache holds all photos in memory during the loop. For 250 photos at ~5MB each, that's ~1.25GB. If this is too much, consider streaming or a bounded cache. For now, the benchmark set is small enough.
- Adding `cluster_id` to `FaceBox` affects GT serialisation too — but it defaults to `None` and existing GT JSON files omit it, so backward compatibility is preserved.

## Acceptance criteria

- [x] All existing tests still pass (`venv/bin/python -m pytest`)
- [x] New tests pass
- [x] `FaceBox` has optional `cluster_id` field (default `None`)
- [x] After a benchmark run with face detection, predicted face boxes have `cluster_id` set
- [x] Faces with similar embeddings share a `cluster_id`

## Scope boundaries

- **In scope**: embedding + clustering of predicted faces, cluster_id on FaceBox
- **Out of scope**: identity matching against known faces, UI rendering (task-053)
- **Do not** modify the existing `cluster_album_faces` function or production clustering path

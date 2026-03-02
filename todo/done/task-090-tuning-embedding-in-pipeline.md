# Task 090: Embedding in the single-photo pipeline

Part of the tuning series (085-094).

**Depends on:** task-089 (face candidate trace)

## Goal

Add an optional `face_embedder` parameter to `run_single_photo()`. When provided, accepted faces are embedded and their embeddings stored on `FaceCandidateTrace`. This eliminates the separate embedding step that re-decodes images, and makes embedding a per-photo pipeline concern.

## Background

Currently embedding happens outside the pipeline:
- **Benchmarking**: `_assign_face_clusters()` re-decodes images from `image_cache`, embeds, clusters — all in one tangled function
- **Production**: `scan/persist.py:process_image()` embeds using `sp.image_rgb` and `sp.face_pixel_bboxes`

Both do the same thing: take an image + face bboxes → compute embeddings. The image is already decoded in `run_single_photo()`. Embedding is a per-photo operation. It belongs in the pipeline.

After this task, both consumers call `run_single_photo(face_embedder=get_face_embedder())` and get embeddings back on the traces. No re-decoding. No separate embedding step.

## Design decisions

| Question | Decision |
|----------|----------|
| Where to embed? | In `run_single_photo()`, after face detection, before returning |
| How to pass embedder? | Optional `face_embedder: FaceEmbedder | None = None` parameter |
| Where to store? | `FaceCandidateTrace.embedding: list[float] | None` (field exists from task-089) |
| Only accepted faces? | Yes. Rejected faces have `embedding=None`. |
| Serialize how? | `list[float]` in JSON. ~4KB per face for 512-dim. Acceptable. |

## Context

- `pipeline/single_photo.py` — `run_single_photo()`, has `image_rgb` and traces
- `pipeline/types.py` — `FaceCandidateTrace.embedding` field (None default from task-089)
- `detection/face/embedder.py` — `FaceEmbedder` protocol, `get_face_embedder()`
- `benchmarking/runner.py:_assign_face_clusters()` — currently does decode + embed + cluster
- `scan/persist.py:process_image()` — currently embeds inline

## Changes

### Modified: `pipeline/single_photo.py`

Add embedder parameter and embed accepted faces:

```python
def run_single_photo(
    image_data: bytes,
    *,
    reader=None,
    face_backend=None,
    face_embedder=None,          # NEW
    fallback_face_backend=None,
    ...
) -> SinglePhotoResult:
    ...
    # After face detection, before return:
    if face_embedder is not None and image_rgb is not None:
        accepted_traces = [t for t in face_trace if t.accepted and t.pixel_bbox]
        if accepted_traces:
            bboxes = [_pixel_bbox_to_polygon(t.pixel_bbox) for t in accepted_traces]
            embeddings = face_embedder.embed(image_rgb, bboxes)
            for trace, emb in zip(accepted_traces, embeddings):
                trace.embedding = emb.tolist()
    ...
```

### Modified: `benchmarking/runner.py`

- Pass `face_embedder` to `run_single_photo()`:
  ```python
  embedder = get_face_embedder() if face_backend is not None else None
  # In loop:
  sp_result = run_single_photo(..., face_embedder=embedder, ...)
  ```
- Simplify `_assign_face_clusters()`: read embeddings from `face_trace` instead of re-decoding images. Remove `image_cache` parameter.
  ```python
  def _assign_face_clusters(photo_results, distance_threshold=None):
      all_embeddings = []
      face_refs = []
      for p_idx, result in enumerate(photo_results):
          if not result.face_trace:
              continue
          for f_idx, trace in enumerate(result.face_trace):
              if trace.embedding is not None:
                  all_embeddings.append(np.array(trace.embedding, dtype=np.float32))
                  face_refs.append((p_idx, f_idx))
      ...
  ```
- Remove `image_cache` dict from `_run_detection_loop()`.

### Modified: `scan/persist.py`

- Pass `face_embedder` to `run_single_photo()`
- Read embeddings from traces instead of calling embedder separately:
  ```python
  for trace in (t for t in sp.face_trace if t.accepted):
      embedding = np.array(trace.embedding, dtype=np.float32) if trace.embedding else None
      # Build FaceDetection with embedding from trace
  ```
- Remove inline embedding call

## Tests

New: `tests/test_pipeline_embedding.py`

```python
def test_accepted_face_has_embedding_on_trace():
    """run_single_photo with embedder populates embedding on accepted traces."""

def test_rejected_face_has_no_embedding():
    """Rejected faces have embedding=None."""

def test_no_embedder_means_no_embeddings():
    """Without face_embedder, all traces have embedding=None."""

def test_embedding_round_trip():
    """Embedding serialises to JSON list and deserialises back."""

def test_assign_face_clusters_uses_trace_embeddings():
    """_assign_face_clusters reads embeddings from traces, not images."""
```

Mark tests that need real embedder as `@pytest.mark.slow`.

## Verification

```bash
venv/bin/python -m pytest tests/test_pipeline_embedding.py -v
venv/bin/python -m pytest
```

## Pitfalls

- **Embedder initialization**: `get_face_embedder()` loads FaceNet. Initialize once in the detection loop / scan service, not per photo.
- **pixel_bbox format**: The embedder expects polygon bboxes `((x1,y1),(x2,y1),(x2,y2),(x1,y2))`. The trace stores `(x1,y1,x2,y2)`. Need a conversion helper.
- **Embedding serialization cost**: 512 floats × 4 bytes = 2KB per face, ~4KB as JSON list. For 100 photos × 3 faces = 1.2MB. Acceptable.
- **Backward compat**: old benchmark JSON without `embedding` loads fine (None default).

## Acceptance criteria

- [ ] `run_single_photo()` accepts optional `face_embedder` parameter
- [ ] Accepted faces have `embedding` populated on their traces
- [ ] `_assign_face_clusters()` reads embeddings from traces, not images
- [ ] `image_cache` removed from detection loop
- [ ] `scan/persist.py` reads embeddings from traces
- [ ] Both consumers pass `face_embedder` to the same function
- [ ] TDD tests pass
- [ ] All existing tests pass

## Scope boundaries

- **In scope**: embedder in pipeline, trace embedding field, consumer updates
- **Out of scope**: clustering changes (task-091), refinement loop (task-093)
- **Do not** change embedding algorithm or detection behavior

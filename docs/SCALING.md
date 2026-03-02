# Scaling Considerations

Notes on how the pipeline scales with album size, and where the bottlenecks are.

## Current scale

The benchmark dataset is ~100 photos with ~500 faces. At this scale, everything fits comfortably in memory and runs in minutes.

## Scaling walls

### Face clustering: N×N similarity matrix

`_cluster_embeddings()` computes a full pairwise cosine similarity matrix: `normed @ normed.T`. This is O(N²) in memory and compute.

| Faces | Matrix size | Memory (float32) |
|-------|-----------|-----------------|
| 500 | 500×500 | 1 MB |
| 2,000 | 2,000×2,000 | 16 MB |
| 5,000 | 5,000×5,000 | 100 MB |
| 10,000 | 10,000×10,000 | 400 MB |
| 50,000 | 50,000×50,000 | 10 GB |

For a race with 10,000 photos averaging 3 faces each (30,000 faces), the matrix alone is 3.6 GB. This is the first hard scaling wall.

**Mitigation strategies (not yet implemented):**

- **Batch clustering**: cluster in chunks (e.g., by time/sequence), then merge clusters across chunks. Reduces peak memory at the cost of some accuracy.
- **Approximate nearest neighbors**: use FAISS or Annoy to find near-neighbors without materializing the full matrix. Only compute exact distances for candidate pairs.
- **Sparse thresholding**: instead of a dense matrix, only store pairs below the distance threshold. For well-separated faces, this is much smaller than N².
- **Block-diagonal structure**: if photos are roughly chronological and runners appear in sequences, the similarity matrix is approximately block-diagonal. Exploit this with a sliding-window approach.

### Image decoding

Currently images are decoded up to 3 times per photo (bib detection, face detection, face embedding). After task-074, this reduces to 1 time. At 10,000 photos with 2MB average, the image cache holds ~20 GB. This exceeds RAM on most machines.

**Mitigation**: stream photos through the pipeline without caching. Each photo is decoded once, processed through all single-photo stages, then released. Only embeddings (2KB per face) are retained for cross-photo analysis.

### Benchmark JSON size

`PhotoResult` stores traces, boxes, scorecards, and (after task-074) embedding vectors per photo. At current scale this is ~10 MB. At 10,000 photos it could reach 500 MB-1 GB.

**Mitigation**: consider binary serialization (e.g., MessagePack, or separate the embedding matrix into a .npy sidecar file) for large runs. Keep JSON for readability at small scale.

## Target use case: 10,000-photo album

A large running race might have 10,000 photos with 1,000-2,000 unique runners, averaging 3-5 faces per photo. This means:

- ~35,000 face detections
- ~35,000 embeddings (512-dim float32 each = ~70 MB)
- Clustering: 35,000 faces → needs approximate methods
- Bib detection: per-photo, scales linearly, not a concern
- Autolink: per-photo, scales linearly, not a concern

The pipeline should handle this within 32 GB RAM and complete in under an hour. The clustering stage is the bottleneck — everything else scales linearly with photo count.

## Clustering algorithm quality: single-linkage chaining

`_cluster_embeddings()` uses single-linkage clustering via union-find: two faces are merged into the same cluster if there is *any* chain of faces connecting them where each adjacent pair is within the distance threshold.

This is vulnerable to **chaining**: one "bridge" face that is somewhat similar to two dissimilar people can merge their clusters. The result is a cluster containing faces of different people, connected through intermediaries.

Symptoms:
- A cluster with high average similarity but low minimum similarity (the bridge face drags the min down)
- Clusters that grow unexpectedly large
- Identity labels that don't match within a cluster

The production path (`cluster_album_faces()`) already computes `min_similarity` per cluster, which would reveal chaining. The benchmark path (task-075) will add per-face `cluster_distance` and `nearest_other_distance` which helps identify bridge faces.

**Potential improvements:**
- **Average-linkage or complete-linkage**: require all (or average of all) pairs within threshold, not just one. More conservative, avoids chaining.
- **DBSCAN**: density-based clustering that naturally handles noise points (faces that don't belong to any cluster). Requires a minimum cluster size parameter.
- **Two-pass**: single-linkage for initial clusters, then split any cluster where min similarity is below a secondary threshold.

At current scale (~500 faces, ~50 identities), single-linkage works well enough. Monitor cluster quality metrics as album size grows.

## Not a concern at current scale

- EasyOCR model loading (~500 MB GPU memory): loaded once, shared across photos
- FaceNet embedding model (~100 MB): loaded once, shared across photos
- Union-find in clustering: O(N·α(N)) ≈ O(N), negligible even at 50,000 faces
- Disk I/O for benchmark JSON: even at 1 GB, writes in seconds

## Design principle

Optimize for the 100-1,000 photo case (current). Keep the 10,000 photo case feasible without architectural changes. Don't optimize for 50,000+ until there's a real need — at that point, move to approximate nearest neighbors and streaming.

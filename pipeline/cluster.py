"""Phase 2: Cross-photo face clustering.

Reads embeddings from face traces, clusters by cosine distance,
and writes diagnostic fields back onto traces.
"""

from __future__ import annotations

from collections import defaultdict
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


class _UnionFind:
    def __init__(self, size: int) -> None:
        self._parent = list(range(size))
        self._rank = [0] * size

    def find(self, idx: int) -> int:
        parent = self._parent[idx]
        if parent != idx:
            self._parent[idx] = self.find(parent)
        return self._parent[idx]

    def union(self, a: int, b: int) -> None:
        root_a = self.find(a)
        root_b = self.find(b)
        if root_a == root_b:
            return
        rank_a = self._rank[root_a]
        rank_b = self._rank[root_b]
        if rank_a < rank_b:
            self._parent[root_a] = root_b
        elif rank_a > rank_b:
            self._parent[root_b] = root_a
        else:
            self._parent[root_b] = root_a
            self._rank[root_a] += 1


def _normalize_embeddings(embeddings: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return embeddings / norms


def _cluster_embeddings(
    embeddings: np.ndarray,
    distance_threshold: float,
) -> list[list[int]]:
    if embeddings.size == 0:
        return []
    normed = _normalize_embeddings(embeddings)
    similarity = normed @ normed.T
    distance = 1.0 - similarity
    mask = np.triu(distance <= distance_threshold, k=1)
    pairs = np.argwhere(mask)

    uf = _UnionFind(normed.shape[0])
    for idx_a, idx_b in pairs:
        uf.union(int(idx_a), int(idx_b))

    clusters: dict[int, list[int]] = defaultdict(list)
    for idx in range(normed.shape[0]):
        clusters[uf.find(idx)].append(idx)
    return list(clusters.values())


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
    threshold = distance_threshold if distance_threshold is not None else config.FACE_CLUSTER_DISTANCE_THRESHOLD

    embedded = [(i, t) for i, t in enumerate(face_traces) if t.embedding is not None]
    if not embedded:
        return ClusterResult(cluster_count=0, face_count=0, centroids=np.empty((0, 0)))

    indices, traces = zip(*embedded)
    embeddings = np.stack([np.array(t.embedding, dtype=np.float32) for t in traces])

    clusters = _cluster_embeddings(embeddings, threshold)
    normed = _normalize_embeddings(embeddings)

    # Compute centroids
    centroids: list[np.ndarray] = []
    for group in clusters:
        c = normed[group].mean(axis=0)
        norm = np.linalg.norm(c)
        if norm > 0:
            c = c / norm
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
            nearest_other = np.full(len(group), float("inf"))

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

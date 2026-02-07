"""Face embedding clustering helpers."""

from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
import logging

import numpy as np

import config
import db
from faces.types import embedding_from_bytes

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FaceEmbeddingRecord:
    face_id: int
    embedding: np.ndarray
    model_name: str
    model_version: str


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


def similarity_label(similarity: float) -> str:
    if similarity >= config.FACE_CLUSTER_SIMILARITY_HIGH:
        return "High"
    if similarity >= config.FACE_CLUSTER_SIMILARITY_MEDIUM:
        return "Medium"
    return "Low"


def cluster_album_faces(
    conn,
    album_id: str,
    distance_threshold: float | None = None,
) -> dict:
    if distance_threshold is None:
        distance_threshold = config.FACE_CLUSTER_DISTANCE_THRESHOLD

    rows = db.list_face_embeddings_for_album(conn, album_id)
    if not rows:
        logger.info("No face embeddings found for album %s", album_id)
        return {
            "album_id": album_id,
            "clusters_created": 0,
            "members_created": 0,
            "faces_seen": 0,
            "models": 0,
        }

    grouped: dict[tuple[str, str], list[FaceEmbeddingRecord]] = defaultdict(list)
    for row in rows:
        embedding = embedding_from_bytes(row["embedding"], int(row["embedding_dim"]))
        grouped[(row["model_name"], row["model_version"])].append(
            FaceEmbeddingRecord(
                face_id=int(row["id"]),
                embedding=embedding,
                model_name=row["model_name"],
                model_version=row["model_version"],
            )
        )

    clusters_created = 0
    members_created = 0
    faces_seen = 0

    for (model_name, model_version), records in grouped.items():
        if not records:
            continue

        db.delete_face_clusters_for_album_model(conn, album_id, model_name, model_version)

        embeddings = np.stack([record.embedding for record in records]).astype(np.float32)
        face_ids = [record.face_id for record in records]
        clusters = _cluster_embeddings(embeddings, distance_threshold)
        if not clusters:
            continue

        normed = _normalize_embeddings(embeddings)
        for cluster_indices in clusters:
            cluster_embeddings = normed[cluster_indices]
            centroid = cluster_embeddings.mean(axis=0)
            centroid_norm = np.linalg.norm(centroid)
            if centroid_norm > 0:
                centroid = centroid / centroid_norm
            similarities = cluster_embeddings @ centroid

            avg_similarity = float(np.mean(similarities))
            min_similarity = float(np.min(similarities))
            max_similarity = float(np.max(similarities))

            cluster_id = db.insert_face_cluster(
                conn,
                album_id=album_id,
                model_name=model_name,
                model_version=model_version,
                centroid=centroid.astype(np.float32),
                avg_similarity=avg_similarity,
                min_similarity=min_similarity,
                max_similarity=max_similarity,
                size=len(cluster_indices),
            )
            clusters_created += 1

            for face_idx, similarity in zip(cluster_indices, similarities):
                distance = float(1.0 - similarity)
                db.insert_face_cluster_member(
                    conn,
                    cluster_id=cluster_id,
                    face_id=face_ids[face_idx],
                    distance=distance,
                )
                members_created += 1

        faces_seen += len(records)

    return {
        "album_id": album_id,
        "clusters_created": clusters_created,
        "members_created": members_created,
        "faces_seen": faces_seen,
        "models": len(grouped),
    }

"""Face embedding clustering helpers.

The core clustering algorithm lives in ``pipeline.cluster``.  This module
provides the DB-backed ``cluster_album_faces()`` wrapper and the
``similarity_label()`` utility.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import logging

import numpy as np

import config
import db
from faces.types import embedding_from_bytes
from pipeline.cluster import cluster as _cluster
from pipeline.types import FaceCandidateTrace

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FaceEmbeddingRecord:
    face_id: int
    embedding: np.ndarray
    model_name: str
    model_version: str


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

        # Build lightweight traces for the shared cluster() function
        face_ids = [r.face_id for r in records]
        traces = [
            FaceCandidateTrace(
                x=0, y=0, w=0, h=0,
                confidence=None,
                passed=True,
                accepted=True,
                embedding=r.embedding.tolist(),
            )
            for r in records
        ]

        result = _cluster(traces, distance_threshold)
        if result.cluster_count == 0:
            continue

        # Persist clusters and members to DB
        for cid in range(result.cluster_count):
            centroid = result.centroids[cid].astype(np.float32)
            members = [
                (i, t) for i, t in enumerate(traces)
                if t.cluster_id == cid
            ]
            similarities = [1.0 - t.cluster_distance for _, t in members]

            avg_similarity = float(np.mean(similarities))
            min_similarity = float(np.min(similarities))
            max_similarity = float(np.max(similarities))

            db_cluster_id = db.insert_face_cluster(
                conn,
                album_id=album_id,
                model_name=model_name,
                model_version=model_version,
                centroid=centroid,
                avg_similarity=avg_similarity,
                min_similarity=min_similarity,
                max_similarity=max_similarity,
                size=len(members),
            )
            clusters_created += 1

            for trace_idx, trace in members:
                db.insert_face_cluster_member(
                    conn,
                    cluster_id=db_cluster_id,
                    face_id=face_ids[trace_idx],
                    distance=trace.cluster_distance,
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

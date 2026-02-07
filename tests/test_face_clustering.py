import sqlite3

import numpy as np

import db
from faces.clustering import cluster_album_faces
from faces.types import FaceModelInfo


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_database(conn)
    return conn


def _seed_face(
    conn: sqlite3.Connection,
    album_id: str,
    photo_url: str,
    embedding: np.ndarray,
    model_info: FaceModelInfo,
    face_index: int,
) -> int:
    photo_id = db.insert_photo(conn, album_id, photo_url, None, None)
    return db.insert_face_detection(
        conn,
        photo_id=photo_id,
        face_index=face_index,
        bbox=[[0, 0], [1, 0], [1, 1], [0, 1]],
        embedding=embedding,
        model_info=model_info,
        snippet_path=None,
        preview_path=None,
    )


def test_cluster_album_faces_creates_clusters_and_members():
    conn = _make_conn()
    try:
        album_id = "album1"
        model_info = FaceModelInfo(name="test_model", version="1", embedding_dim=3)

        embeddings = [
            np.array([1.0, 0.0, 0.0], dtype=np.float32),
            np.array([0.99, 0.01, 0.0], dtype=np.float32),
            np.array([0.0, 1.0, 0.0], dtype=np.float32),
        ]
        for idx, embedding in enumerate(embeddings):
            _seed_face(conn, album_id, f"photo://{idx}", embedding, model_info, idx)

        stats = cluster_album_faces(conn, album_id, distance_threshold=0.2)
        assert stats["clusters_created"] == 2
        assert stats["members_created"] == 3
        assert stats["faces_seen"] == 3
        assert stats["models"] == 1

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT size, avg_similarity, min_similarity, max_similarity, centroid_dim
            FROM face_clusters
            WHERE album_id = ?
            """,
            (album_id,),
        )
        rows = cursor.fetchall()
        assert len(rows) == 2
        for row in rows:
            assert row["centroid_dim"] == 3
            assert 0.0 <= row["avg_similarity"] <= 1.0
            assert 0.0 <= row["min_similarity"] <= 1.0
            assert 0.0 <= row["max_similarity"] <= 1.0

        cursor.execute(
            "SELECT COUNT(*) AS count FROM face_cluster_members"
        )
        assert cursor.fetchone()["count"] == 3
    finally:
        conn.close()


def test_cluster_album_faces_separates_models_and_replaces_clusters():
    conn = _make_conn()
    try:
        album_id = "album2"
        model_a = FaceModelInfo(name="model_a", version="1", embedding_dim=3)
        model_b = FaceModelInfo(name="model_b", version="1", embedding_dim=3)

        face_a = _seed_face(
            conn,
            album_id,
            "photo://a",
            np.array([1.0, 0.0, 0.0], dtype=np.float32),
            model_a,
            0,
        )
        _seed_face(
            conn,
            album_id,
            "photo://b",
            np.array([0.0, 1.0, 0.0], dtype=np.float32),
            model_b,
            0,
        )

        old_cluster_id = db.insert_face_cluster(
            conn,
            album_id=album_id,
            model_name=model_a.name,
            model_version=model_a.version,
            centroid=np.array([1.0, 0.0, 0.0], dtype=np.float32),
            avg_similarity=1.0,
            min_similarity=1.0,
            max_similarity=1.0,
            size=1,
        )
        db.insert_face_cluster_member(conn, old_cluster_id, face_a, 0.0)

        stats = cluster_album_faces(conn, album_id, distance_threshold=0.2)
        assert stats["clusters_created"] == 2
        assert stats["members_created"] == 2
        assert stats["faces_seen"] == 2
        assert stats["models"] == 2

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT model_name, COUNT(*) AS count
            FROM face_clusters
            WHERE album_id = ?
            GROUP BY model_name
            """,
            (album_id,),
        )
        rows = {row["model_name"]: row["count"] for row in cursor.fetchall()}
        assert rows == {"model_a": 1, "model_b": 1}

        cursor.execute("SELECT COUNT(*) AS count FROM face_cluster_members")
        assert cursor.fetchone()["count"] == 2
    finally:
        conn.close()

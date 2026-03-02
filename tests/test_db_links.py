"""Tests for bib_face_links table CRUD in db.py."""

from __future__ import annotations

import sqlite3

import pytest

import db


@pytest.fixture
def conn(tmp_path, monkeypatch):
    """Create an in-memory database with schema for testing."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    connection = db.get_connection()
    yield connection
    connection.close()


@pytest.fixture
def photo_id(conn):
    """Insert a photo record and return its ID."""
    return db.insert_photo(conn, "album1", "http://example.com/photo.jpg")


class TestBibFaceLinksTable:
    def test_insert_and_get_link(self, conn, photo_id):
        bib_det_id = db.insert_bib_detection(conn, photo_id, "42", 0.9, [[0, 0], [10, 0], [10, 10], [0, 10]])
        face_det_id = db.insert_face_detection(
            conn, photo_id, 0,
            bbox=[[10, 10], [50, 10], [50, 50], [10, 50]],
            embedding=None,
            model_info=db.FaceModelInfo(name="test", version="1", embedding_dim=128),
        )

        link_id = db.insert_bib_face_link(conn, photo_id, bib_det_id, face_det_id, "autolink")
        assert link_id > 0

        links = db.get_bib_face_links(conn, photo_id)
        assert len(links) == 1
        assert links[0]["bib_detection_id"] == bib_det_id
        assert links[0]["face_detection_id"] == face_det_id
        assert links[0]["provenance"] == "autolink"

    def test_delete_links(self, conn, photo_id):
        bib_det_id = db.insert_bib_detection(conn, photo_id, "42", 0.9, [[0, 0], [10, 0], [10, 10], [0, 10]])
        face_det_id = db.insert_face_detection(
            conn, photo_id, 0,
            bbox=[[10, 10], [50, 10], [50, 50], [10, 50]],
            embedding=None,
            model_info=db.FaceModelInfo(name="test", version="1", embedding_dim=128),
        )

        db.insert_bib_face_link(conn, photo_id, bib_det_id, face_det_id, "autolink")
        deleted = db.delete_bib_face_links(conn, photo_id)
        assert deleted == 1

        links = db.get_bib_face_links(conn, photo_id)
        assert len(links) == 0

    def test_unique_constraint(self, conn, photo_id):
        bib_det_id = db.insert_bib_detection(conn, photo_id, "42", 0.9, [[0, 0], [10, 0], [10, 10], [0, 10]])
        face_det_id = db.insert_face_detection(
            conn, photo_id, 0,
            bbox=[[10, 10], [50, 10], [50, 50], [10, 50]],
            embedding=None,
            model_info=db.FaceModelInfo(name="test", version="1", embedding_dim=128),
        )

        db.insert_bib_face_link(conn, photo_id, bib_det_id, face_det_id, "autolink")
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_bib_face_link(conn, photo_id, bib_det_id, face_det_id, "manual")

    def test_get_links_empty_photo(self, conn, photo_id):
        links = db.get_bib_face_links(conn, photo_id)
        assert links == []

    def test_delete_links_empty_photo(self, conn, photo_id):
        deleted = db.delete_bib_face_links(conn, photo_id)
        assert deleted == 0

    def test_multiple_links_per_photo(self, conn, photo_id):
        bib_det_id1 = db.insert_bib_detection(conn, photo_id, "42", 0.9, [[0, 0], [10, 0], [10, 10], [0, 10]])
        bib_det_id2 = db.insert_bib_detection(conn, photo_id, "7", 0.8, [[20, 0], [30, 0], [30, 10], [20, 10]])
        face_det_id1 = db.insert_face_detection(
            conn, photo_id, 0,
            bbox=[[10, 10], [50, 10], [50, 50], [10, 50]],
            embedding=None,
            model_info=db.FaceModelInfo(name="test", version="1", embedding_dim=128),
        )
        face_det_id2 = db.insert_face_detection(
            conn, photo_id, 1,
            bbox=[[60, 10], [90, 10], [90, 50], [60, 50]],
            embedding=None,
            model_info=db.FaceModelInfo(name="test", version="1", embedding_dim=128),
        )

        db.insert_bib_face_link(conn, photo_id, bib_det_id1, face_det_id1, "autolink")
        db.insert_bib_face_link(conn, photo_id, bib_det_id2, face_det_id2, "autolink")

        links = db.get_bib_face_links(conn, photo_id)
        assert len(links) == 2

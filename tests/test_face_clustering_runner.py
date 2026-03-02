"""Tests for _assign_face_clusters in benchmarking.runner (task-051)."""

from __future__ import annotations

from unittest.mock import patch

import cv2
import numpy as np
import pytest

from pipeline.types import FaceBox
from benchmarking.runner import PhotoResult, _assign_face_clusters


def _photo_result(content_hash: str, face_boxes: list[FaceBox] | None = None) -> PhotoResult:
    return PhotoResult(
        content_hash=content_hash,
        expected_bibs=[],
        detected_bibs=[],
        tp=0, fp=0, fn=0,
        status="PASS",
        detection_time_ms=1.0,
        pred_face_boxes=face_boxes,
    )


def _make_image_bytes(w: int = 100, h: int = 100) -> bytes:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".png", img)
    return buf.tobytes()


class _FakeEmbedder:
    """Returns a fixed embedding per face, controllable via constructor."""

    def __init__(self, embeddings: list[np.ndarray]):
        self._embeddings = embeddings
        self._call_idx = 0

    def embed(self, image, boxes):
        result = []
        for _ in boxes:
            result.append(self._embeddings[self._call_idx])
            self._call_idx += 1
        return result

    def model_info(self):
        from faces.types import FaceModelInfo
        return FaceModelInfo(name="fake", version="0", embedding_dim=4)


class TestAssignFaceClusters:
    def test_empty_results_no_crash(self):
        _assign_face_clusters([], {})

    def test_no_face_boxes_no_crash(self):
        pr = _photo_result("aaa")
        pr.pred_face_boxes = []
        _assign_face_clusters([pr], {"aaa": _make_image_bytes()})

    def test_assigns_cluster_ids(self):
        fbox = FaceBox(x=0.1, y=0.1, w=0.3, h=0.3)
        assert fbox.cluster_id is None
        pr = _photo_result("aaa", [fbox])
        emb = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        with patch("faces.embedder.get_face_embedder", return_value=_FakeEmbedder([emb])):
            _assign_face_clusters([pr], {"aaa": _make_image_bytes()})
        assert pr.pred_face_boxes[0].cluster_id is not None
        assert isinstance(pr.pred_face_boxes[0].cluster_id, int)

    def test_groups_similar_embeddings(self):
        # Two identical embeddings should end up in the same cluster
        emb_a = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        emb_b = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        pr1 = _photo_result("aaa", [FaceBox(x=0.1, y=0.1, w=0.2, h=0.2)])
        pr2 = _photo_result("bbb", [FaceBox(x=0.1, y=0.1, w=0.2, h=0.2)])
        img = _make_image_bytes()
        with patch("faces.embedder.get_face_embedder", return_value=_FakeEmbedder([emb_a, emb_b])):
            _assign_face_clusters([pr1, pr2], {"aaa": img, "bbb": img})
        assert pr1.pred_face_boxes[0].cluster_id == pr2.pred_face_boxes[0].cluster_id

    def test_separates_dissimilar_embeddings(self):
        # Two orthogonal embeddings should be in different clusters (with tight threshold)
        emb_a = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        emb_b = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)
        pr1 = _photo_result("aaa", [FaceBox(x=0.1, y=0.1, w=0.2, h=0.2)])
        pr2 = _photo_result("bbb", [FaceBox(x=0.1, y=0.1, w=0.2, h=0.2)])
        img = _make_image_bytes()
        with patch("faces.embedder.get_face_embedder", return_value=_FakeEmbedder([emb_a, emb_b])):
            _assign_face_clusters([pr1, pr2], {"aaa": img, "bbb": img}, distance_threshold=0.3)
        assert pr1.pred_face_boxes[0].cluster_id != pr2.pred_face_boxes[0].cluster_id

    def test_missing_image_skipped(self):
        pr = _photo_result("aaa", [FaceBox(x=0.1, y=0.1, w=0.2, h=0.2)])
        # No image in cache
        _assign_face_clusters([pr], {})
        assert pr.pred_face_boxes[0].cluster_id is None


class TestFaceBoxClusterId:
    def test_defaults_to_none(self):
        fb = FaceBox(x=0.1, y=0.1, w=0.2, h=0.2)
        assert fb.cluster_id is None

    def test_roundtrips(self):
        fb = FaceBox(x=0.1, y=0.1, w=0.2, h=0.2, cluster_id=5)
        d = fb.model_dump()
        assert d["cluster_id"] == 5
        reloaded = FaceBox(**d)
        assert reloaded.cluster_id == 5

    def test_backward_compat_missing_field(self):
        d = {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2, "scope": "keep"}
        fb = FaceBox(**d)
        assert fb.cluster_id is None

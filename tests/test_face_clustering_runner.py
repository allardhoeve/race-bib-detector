"""Tests for _assign_face_clusters in benchmarking.runner (task-051)."""

from __future__ import annotations

import numpy as np
import pytest

from pipeline.types import FaceBox, FaceCandidateTrace
from benchmarking.runner import PhotoResult, _assign_face_clusters


def _photo_result(
    content_hash: str,
    face_boxes: list[FaceBox] | None = None,
    face_trace: list[FaceCandidateTrace] | None = None,
) -> PhotoResult:
    return PhotoResult(
        content_hash=content_hash,
        expected_bibs=[],
        detected_bibs=[],
        tp=0, fp=0, fn=0,
        status="PASS",
        detection_time_ms=1.0,
        pred_face_boxes=face_boxes,
        face_trace=face_trace,
    )


def _make_accepted_trace(embedding: list[float] | None = None) -> FaceCandidateTrace:
    return FaceCandidateTrace(
        x=0.1, y=0.1, w=0.2, h=0.2,
        confidence=0.9,
        passed=True,
        accepted=True,
        pixel_bbox=(10, 10, 30, 30),
        embedding=embedding,
    )


class TestAssignFaceClusters:
    def test_empty_results_no_crash(self):
        _assign_face_clusters([])

    def test_no_face_boxes_no_crash(self):
        pr = _photo_result("aaa")
        pr.pred_face_boxes = []
        _assign_face_clusters([pr])

    def test_assigns_cluster_ids(self):
        fbox = FaceBox(x=0.1, y=0.1, w=0.3, h=0.3)
        assert fbox.cluster_id is None
        emb = [1.0, 0.0, 0.0, 0.0]
        trace = _make_accepted_trace(embedding=emb)
        pr = _photo_result("aaa", [fbox], [trace])
        _assign_face_clusters([pr])
        assert pr.pred_face_boxes[0].cluster_id is not None
        assert isinstance(pr.pred_face_boxes[0].cluster_id, int)

    def test_groups_similar_embeddings(self):
        # Two identical embeddings should end up in the same cluster
        emb = [1.0, 0.0, 0.0, 0.0]
        pr1 = _photo_result("aaa", [FaceBox(x=0.1, y=0.1, w=0.2, h=0.2)], [_make_accepted_trace(emb)])
        pr2 = _photo_result("bbb", [FaceBox(x=0.1, y=0.1, w=0.2, h=0.2)], [_make_accepted_trace(emb)])
        _assign_face_clusters([pr1, pr2])
        assert pr1.pred_face_boxes[0].cluster_id == pr2.pred_face_boxes[0].cluster_id

    def test_separates_dissimilar_embeddings(self):
        # Two orthogonal embeddings should be in different clusters (with tight threshold)
        emb_a = [1.0, 0.0, 0.0, 0.0]
        emb_b = [0.0, 1.0, 0.0, 0.0]
        pr1 = _photo_result("aaa", [FaceBox(x=0.1, y=0.1, w=0.2, h=0.2)], [_make_accepted_trace(emb_a)])
        pr2 = _photo_result("bbb", [FaceBox(x=0.1, y=0.1, w=0.2, h=0.2)], [_make_accepted_trace(emb_b)])
        _assign_face_clusters([pr1, pr2], distance_threshold=0.3)
        assert pr1.pred_face_boxes[0].cluster_id != pr2.pred_face_boxes[0].cluster_id

    def test_no_embedding_skipped(self):
        """Faces without embeddings in trace are skipped (no crash)."""
        fbox = FaceBox(x=0.1, y=0.1, w=0.2, h=0.2)
        trace = _make_accepted_trace(embedding=None)
        pr = _photo_result("aaa", [fbox], [trace])
        _assign_face_clusters([pr])
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

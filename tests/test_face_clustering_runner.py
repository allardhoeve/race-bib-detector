"""Tests for face clustering in benchmark runner (task-051, task-091)."""

from __future__ import annotations

import numpy as np
import pytest

from pipeline.types import FaceLabel, FaceCandidateTrace
from benchmarking.runner import PhotoResult
from pipeline.cluster import cluster
from tests.helpers import make_face_trace as _make_accepted_trace


def _photo_result(
    content_hash: str,
    face_boxes: list[FaceLabel] | None = None,
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


def _gather_traces(photo_results: list[PhotoResult]) -> list[FaceCandidateTrace]:
    """Collect all face_trace entries — mirrors what runner does."""
    all_traces: list[FaceCandidateTrace] = []
    for result in photo_results:
        if result.face_trace:
            all_traces.extend(result.face_trace)
    return all_traces


class TestRunnerClustering:
    """Tests that cluster() works correctly when applied to runner PhotoResults."""

    def test_empty_results_no_crash(self):
        result = cluster([])
        assert result.cluster_count == 0

    def test_no_face_trace_no_crash(self):
        pr = _photo_result("aaa")
        cluster(_gather_traces([pr]))

    def test_assigns_cluster_ids_via_trace(self):
        emb = [1.0, 0.0, 0.0, 0.0]
        trace = _make_accepted_trace(embedding=emb)
        pr = _photo_result("aaa", [FaceLabel(x=0.1, y=0.1, w=0.3, h=0.3)], [trace])
        cluster(_gather_traces([pr]))
        assert trace.cluster_id is not None
        assert isinstance(trace.cluster_id, int)

    def test_groups_similar_embeddings(self):
        emb = [1.0, 0.0, 0.0, 0.0]
        t1 = _make_accepted_trace(emb)
        t2 = _make_accepted_trace(emb)
        pr1 = _photo_result("aaa", [FaceLabel(x=0.1, y=0.1, w=0.2, h=0.2)], [t1])
        pr2 = _photo_result("bbb", [FaceLabel(x=0.1, y=0.1, w=0.2, h=0.2)], [t2])
        cluster(_gather_traces([pr1, pr2]))
        assert t1.cluster_id == t2.cluster_id

    def test_separates_dissimilar_embeddings(self):
        t1 = _make_accepted_trace([1.0, 0.0, 0.0, 0.0])
        t2 = _make_accepted_trace([0.0, 1.0, 0.0, 0.0])
        pr1 = _photo_result("aaa", [FaceLabel(x=0.1, y=0.1, w=0.2, h=0.2)], [t1])
        pr2 = _photo_result("bbb", [FaceLabel(x=0.1, y=0.1, w=0.2, h=0.2)], [t2])
        cluster(_gather_traces([pr1, pr2]), distance_threshold=0.3)
        assert t1.cluster_id != t2.cluster_id

    def test_no_embedding_skipped(self):
        trace = _make_accepted_trace(embedding=None)
        pr = _photo_result("aaa", [FaceLabel(x=0.1, y=0.1, w=0.2, h=0.2)], [trace])
        cluster(_gather_traces([pr]))
        assert trace.cluster_id is None


class TestFaceLabelClusterId:
    def test_defaults_to_none(self):
        fb = FaceLabel(x=0.1, y=0.1, w=0.2, h=0.2)
        assert fb.cluster_id is None

    def test_roundtrips(self):
        fb = FaceLabel(x=0.1, y=0.1, w=0.2, h=0.2, cluster_id=5)
        d = fb.model_dump()
        assert d["cluster_id"] == 5
        reloaded = FaceLabel(**d)
        assert reloaded.cluster_id == 5

    def test_backward_compat_missing_field(self):
        d = {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2, "scope": "keep"}
        fb = FaceLabel(**d)
        assert fb.cluster_id is None

"""Tests for pipeline.cluster — unified face clustering."""

from __future__ import annotations

import numpy as np
import pytest

from pipeline.types import FaceCandidateTrace


def _make_trace(embedding: list[float] | None = None) -> FaceCandidateTrace:
    return FaceCandidateTrace(
        x=0.1, y=0.1, w=0.2, h=0.2,
        confidence=0.9,
        passed=True,
        accepted=True,
        pixel_bbox=(10, 10, 30, 30),
        embedding=embedding,
    )


class TestCluster:
    def test_cluster_empty_traces(self):
        """cluster() with no embedded traces returns empty result."""
        from pipeline.cluster import cluster

        result = cluster([])
        assert result.cluster_count == 0
        assert result.face_count == 0

    def test_cluster_singleton(self):
        """Single face gets cluster_id=0, cluster_distance~0.0."""
        from pipeline.cluster import cluster

        trace = _make_trace([1.0, 0.0, 0.0, 0.0])
        result = cluster([trace])
        assert result.cluster_count == 1
        assert result.face_count == 1
        assert trace.cluster_id == 0
        assert trace.cluster_distance is not None
        assert trace.cluster_distance < 1e-6
        assert trace.nearest_other_distance == float("inf")

    def test_cluster_two_groups(self):
        """Two distinct embedding groups get separate cluster_ids."""
        from pipeline.cluster import cluster

        t1 = _make_trace([1.0, 0.0, 0.0, 0.0])
        t2 = _make_trace([0.99, 0.01, 0.0, 0.0])
        t3 = _make_trace([0.0, 1.0, 0.0, 0.0])
        result = cluster([t1, t2, t3], distance_threshold=0.3)
        assert result.cluster_count == 2
        assert t1.cluster_id == t2.cluster_id
        assert t1.cluster_id != t3.cluster_id

    def test_cluster_writes_diagnostics_to_traces(self):
        """cluster() populates cluster_id, cluster_distance, nearest_other_distance."""
        from pipeline.cluster import cluster

        t1 = _make_trace([1.0, 0.0, 0.0, 0.0])
        t2 = _make_trace([0.0, 1.0, 0.0, 0.0])
        cluster([t1, t2], distance_threshold=0.3)
        for t in [t1, t2]:
            assert t.cluster_id is not None
            assert t.cluster_distance is not None
            assert t.nearest_other_distance is not None
            assert t.nearest_other_distance < float("inf")

    def test_unembedded_traces_unchanged(self):
        """Traces without embeddings keep None cluster fields."""
        from pipeline.cluster import cluster

        embedded = _make_trace([1.0, 0.0, 0.0, 0.0])
        bare = _make_trace(None)
        cluster([embedded, bare])
        assert embedded.cluster_id == 0
        assert bare.cluster_id is None
        assert bare.cluster_distance is None
        assert bare.nearest_other_distance is None

    def test_cluster_result_summary(self):
        """ClusterResult has correct cluster_count and face_count."""
        from pipeline.cluster import cluster

        traces = [
            _make_trace([1.0, 0.0, 0.0, 0.0]),
            _make_trace([0.99, 0.01, 0.0, 0.0]),
            _make_trace([0.0, 1.0, 0.0, 0.0]),
            _make_trace(None),  # unembedded — not counted
        ]
        result = cluster(traces, distance_threshold=0.3)
        assert result.cluster_count == 2
        assert result.face_count == 3
        assert result.centroids.shape[0] == 2

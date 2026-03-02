"""Tests for pipeline_types — shared types extracted from benchmarking.ground_truth and faces.autolink."""

from __future__ import annotations

import pytest


class TestBibLabelFromPipelineTypes:
    def test_import_from_pipeline_types(self):
        from pipeline.types import BibLabel
        box = BibLabel(x=0.1, y=0.2, w=0.3, h=0.4, number="42")
        assert box.number == "42"
        assert box.has_coords

    def test_scope_validation(self):
        from pipeline.types import BibLabel
        with pytest.raises(ValueError):
            BibLabel(x=0, y=0, w=0.1, h=0.1, scope="invalid")


class TestFaceLabelFromPipelineTypes:
    def test_import_from_pipeline_types(self):
        from pipeline.types import FaceLabel
        box = FaceLabel(x=0.1, y=0.2, w=0.3, h=0.4)
        assert box.scope == "keep"
        assert box.has_coords

    def test_scope_compat(self):
        from pipeline.types import FaceLabel
        box = FaceLabel(x=0.1, y=0.2, w=0.3, h=0.4, scope="ignore")
        assert box.scope == "exclude"


class TestBibFaceLinkFromPipelineTypes:
    def test_import_from_pipeline_types(self):
        from pipeline.types import BibFaceLink
        link = BibFaceLink(bib_index=0, face_index=1)
        assert link.to_pair() == [0, 1]


class TestScopeConstants:
    def test_constants_importable(self):
        from pipeline.types import (
            BIB_BOX_SCOPES,
            _BIB_BOX_UNSCORED,
            FACE_SCOPE_TAGS,
            FACE_BOX_TAGS,
            _FACE_SCOPE_COMPAT,
        )
        assert "bib" in BIB_BOX_SCOPES
        assert "not_bib" in _BIB_BOX_UNSCORED
        assert "keep" in FACE_SCOPE_TAGS
        assert "tiny" in FACE_BOX_TAGS
        assert _FACE_SCOPE_COMPAT["ignore"] == "exclude"


class TestAutolinkFromPipelineTypes:
    def test_predict_links_importable(self):
        from pipeline.types import predict_links, TraceLink, BibCandidateTrace, FaceCandidateTrace
        bib = BibCandidateTrace(
            x=0.1, y=0.5, w=0.1, h=0.1,
            area=100, aspect_ratio=1.0, median_brightness=200.0,
            mean_brightness=200.0, relative_area=0.01,
            passed_validation=True, accepted=True, bib_number="1",
        )
        face = FaceCandidateTrace(
            x=0.1, y=0.1, w=0.1, h=0.1,
            confidence=0.9, passed=True, accepted=True,
        )
        result = predict_links([bib], [face])
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TraceLink)

    def test_torso_region_importable(self):
        from pipeline.types import _torso_region, FaceCandidateTrace
        face = FaceCandidateTrace(
            x=0.1, y=0.1, w=0.1, h=0.1,
            confidence=0.9, passed=True, accepted=True,
        )
        tx, ty, tw, th = _torso_region(face)
        assert tw > 0 and th > 0


class TestTraceLink:
    def test_importable_and_constructable(self):
        from pipeline.types import TraceLink, BibCandidateTrace, FaceCandidateTrace
        bib_trace = BibCandidateTrace(
            x=0.1, y=0.5, w=0.1, h=0.1,
            area=100, aspect_ratio=1.0, median_brightness=200.0,
            mean_brightness=200.0, relative_area=0.01,
            passed_validation=True, accepted=True, bib_number="42",
        )
        face_trace = FaceCandidateTrace(
            x=0.1, y=0.1, w=0.1, h=0.1,
            confidence=0.9, passed=True, accepted=True,
        )
        link = TraceLink(
            face_trace=face_trace,
            bib_trace=bib_trace,
            provenance="single_face",
            distance=0.25,
        )
        assert link.face_trace is face_trace
        assert link.bib_trace is bib_trace
        assert link.provenance == "single_face"
        assert link.distance == 0.25


class TestReExportsFromGroundTruth:
    """Verify that benchmarking.ground_truth re-exports work for backward compat."""

    def test_bibbox_from_ground_truth(self):
        from benchmarking.ground_truth import BibLabel
        box = BibLabel(x=0.1, y=0.2, w=0.3, h=0.4, number="42")
        assert box.number == "42"

    def test_facebox_from_ground_truth(self):
        from benchmarking.ground_truth import FaceLabel
        box = FaceLabel(x=0.1, y=0.2, w=0.3, h=0.4)
        assert box.scope == "keep"

    def test_bibfacelink_from_ground_truth(self):
        from benchmarking.ground_truth import BibFaceLink
        link = BibFaceLink(bib_index=0, face_index=1)
        assert link.to_pair() == [0, 1]

    def test_scope_constants_from_ground_truth(self):
        from benchmarking.ground_truth import BIB_BOX_SCOPES, _BIB_BOX_UNSCORED, FACE_SCOPE_TAGS, FACE_BOX_TAGS
        assert "bib" in BIB_BOX_SCOPES

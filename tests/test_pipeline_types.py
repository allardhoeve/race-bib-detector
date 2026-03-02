"""Tests for pipeline_types — shared types extracted from benchmarking.ground_truth and faces.autolink."""

from __future__ import annotations

import pytest


class TestBibBoxFromPipelineTypes:
    def test_import_from_pipeline_types(self):
        from pipeline.types import BibBox
        box = BibBox(x=0.1, y=0.2, w=0.3, h=0.4, number="42")
        assert box.number == "42"
        assert box.has_coords

    def test_scope_validation(self):
        from pipeline.types import BibBox
        with pytest.raises(ValueError):
            BibBox(x=0, y=0, w=0.1, h=0.1, scope="invalid")


class TestFaceBoxFromPipelineTypes:
    def test_import_from_pipeline_types(self):
        from pipeline.types import FaceBox
        box = FaceBox(x=0.1, y=0.2, w=0.3, h=0.4)
        assert box.scope == "keep"
        assert box.has_coords

    def test_scope_compat(self):
        from pipeline.types import FaceBox
        box = FaceBox(x=0.1, y=0.2, w=0.3, h=0.4, scope="ignore")
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
        from pipeline.types import predict_links, AutolinkResult, BibBox, FaceBox
        bib = BibBox(x=0.1, y=0.5, w=0.1, h=0.1, number="1")
        face = FaceBox(x=0.1, y=0.1, w=0.1, h=0.1)
        result = predict_links([bib], [face])
        assert isinstance(result, AutolinkResult)
        assert len(result.pairs) == 1

    def test_torso_region_importable(self):
        from pipeline.types import _torso_region, FaceBox
        face = FaceBox(x=0.1, y=0.1, w=0.1, h=0.1)
        tx, ty, tw, th = _torso_region(face)
        assert tw > 0 and th > 0


class TestReExportsFromGroundTruth:
    """Verify that benchmarking.ground_truth re-exports work for backward compat."""

    def test_bibbox_from_ground_truth(self):
        from benchmarking.ground_truth import BibBox
        box = BibBox(x=0.1, y=0.2, w=0.3, h=0.4, number="42")
        assert box.number == "42"

    def test_facebox_from_ground_truth(self):
        from benchmarking.ground_truth import FaceBox
        box = FaceBox(x=0.1, y=0.2, w=0.3, h=0.4)
        assert box.scope == "keep"

    def test_bibfacelink_from_ground_truth(self):
        from benchmarking.ground_truth import BibFaceLink
        link = BibFaceLink(bib_index=0, face_index=1)
        assert link.to_pair() == [0, 1]

    def test_scope_constants_from_ground_truth(self):
        from benchmarking.ground_truth import BIB_BOX_SCOPES, _BIB_BOX_UNSCORED, FACE_SCOPE_TAGS, FACE_BOX_TAGS
        assert "bib" in BIB_BOX_SCOPES

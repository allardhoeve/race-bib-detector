"""TDD tests for custom serialisation logic in runner.py Pydantic models.

Covers the non-trivial validator/serialiser cases introduced when the runner
dataclasses were migrated to pydantic.BaseModel (task-034).
"""
from __future__ import annotations

import pytest

from pipeline.types import BibBox, BibFaceLink, FaceBox
from benchmarking.runner import BibCandidateSummary, FacePipelineConfig, PhotoResult, PipelineConfig, RunMetadata
from benchmarking.scoring import BibScorecard, FaceScorecard, LinkScorecard


# =============================================================================
# PipelineConfig — clahe_tile_size round-trip
# =============================================================================


class TestPipelineConfigTileSize:
    def _cfg(self, tile_size) -> PipelineConfig:
        return PipelineConfig(
            target_width=None,
            clahe_enabled=True,
            clahe_clip_limit=2.0,
            clahe_tile_size=tile_size,
            clahe_dynamic_range_threshold=None,
        )

    def test_tuple_serialised_as_list(self):
        d = self._cfg((8, 8)).model_dump()
        assert d["clahe_tile_size"] == [8, 8]
        assert isinstance(d["clahe_tile_size"], list)

    def test_list_coerced_to_tuple_on_load(self):
        d = {
            "target_width": None, "clahe_enabled": True,
            "clahe_clip_limit": 2.0, "clahe_tile_size": [8, 8],
            "clahe_dynamic_range_threshold": None,
        }
        cfg = PipelineConfig.model_validate(d)
        assert cfg.clahe_tile_size == (8, 8)
        assert isinstance(cfg.clahe_tile_size, tuple)

    def test_none_tile_size_round_trips_cleanly(self):
        d = self._cfg(None).model_dump()
        assert d["clahe_tile_size"] is None
        reloaded = PipelineConfig.model_validate(d)
        assert reloaded.clahe_tile_size is None

    def test_full_round_trip_preserves_values(self):
        cfg = self._cfg((16, 16))
        reloaded = PipelineConfig.model_validate(cfg.model_dump())
        assert reloaded.clahe_tile_size == (16, 16)
        assert reloaded.clahe_clip_limit == 2.0


# =============================================================================
# FacePipelineConfig — fallback_backend normalisation
# =============================================================================


def _face_cfg_dict(**overrides) -> dict:
    base = {
        "face_backend": "dnn",
        "dnn_confidence_min": 0.5,
        "dnn_fallback_confidence_min": 0.3,
        "dnn_fallback_max": 5,
        "fallback_backend": None,
        "fallback_min_face_count": 0,
        "fallback_max": 0,
        "fallback_iou_threshold": 0.3,
    }
    return {**base, **overrides}


class TestFacePipelineConfigFallbackBackend:
    def test_empty_string_normalised_to_none(self):
        cfg = FacePipelineConfig.model_validate(_face_cfg_dict(fallback_backend=""))
        assert cfg.fallback_backend is None

    def test_real_backend_passes_through(self):
        cfg = FacePipelineConfig.model_validate(_face_cfg_dict(fallback_backend="haar"))
        assert cfg.fallback_backend == "haar"

    def test_none_stays_none(self):
        cfg = FacePipelineConfig.model_validate(_face_cfg_dict(fallback_backend=None))
        assert cfg.fallback_backend is None


# =============================================================================
# RunMetadata — nested config round-trips
# =============================================================================


def _base_meta_dict(**overrides) -> dict:
    base = {
        "run_id": "abc12345",
        "timestamp": "2025-01-01T00:00:00",
        "split": "full",
        "git_commit": "deadbeef",
        "git_dirty": False,
        "python_version": "3.14.0",
        "package_versions": {},
        "hostname": "testhost",
        "gpu_info": None,
        "total_runtime_seconds": 10.0,
    }
    return {**base, **overrides}


class TestRunMetadataRoundTrip:
    def test_nested_pipeline_config_loaded_and_dumped(self):
        d = _base_meta_dict(pipeline_config={
            "target_width": 1024, "clahe_enabled": True,
            "clahe_clip_limit": 2.0, "clahe_tile_size": [8, 8],
            "clahe_dynamic_range_threshold": 0.5,
        })
        meta = RunMetadata.model_validate(d)
        assert meta.pipeline_config is not None
        # list → tuple on load
        assert meta.pipeline_config.clahe_tile_size == (8, 8)
        # tuple → list on dump
        d2 = meta.model_dump(exclude_none=True)
        assert d2["pipeline_config"]["clahe_tile_size"] == [8, 8]

    def test_optional_fields_absent_when_none(self):
        meta = RunMetadata.model_validate(_base_meta_dict())
        assert meta.pipeline_config is None
        assert meta.face_pipeline_config is None
        assert meta.note is None
        d = meta.model_dump(exclude_none=True)
        assert "pipeline_config" not in d
        assert "face_pipeline_config" not in d
        assert "note" not in d

    def test_note_included_when_set(self):
        meta = RunMetadata.model_validate(_base_meta_dict(note="experiment v2"))
        d = meta.model_dump(exclude_none=True)
        assert d["note"] == "experiment v2"


# =============================================================================
# PhotoResult — prediction + GT box fields (task-049)
# =============================================================================


def _photo_result_dict(**overrides) -> dict:
    base = {
        "content_hash": "abcd1234",
        "expected_bibs": [1, 2],
        "detected_bibs": [1],
        "tp": 1,
        "fp": 0,
        "fn": 1,
        "status": "PARTIAL",
        "detection_time_ms": 123.4,
    }
    return {**base, **overrides}


class TestPhotoResultBoxFields:
    def test_box_fields_default_none(self):
        pr = PhotoResult(**_photo_result_dict())
        assert pr.pred_bib_boxes is None
        assert pr.pred_face_boxes is None
        assert pr.gt_bib_boxes is None
        assert pr.gt_face_boxes is None

    def test_with_boxes_roundtrip(self):
        bib_boxes = [BibBox(x=0.1, y=0.2, w=0.3, h=0.4, number="42", scope="bib")]
        face_boxes = [FaceBox(x=0.5, y=0.6, w=0.1, h=0.1, scope="keep")]
        pr = PhotoResult(**_photo_result_dict(
            pred_bib_boxes=bib_boxes,
            pred_face_boxes=face_boxes,
            gt_bib_boxes=bib_boxes,
            gt_face_boxes=face_boxes,
        ))
        d = pr.model_dump()
        reloaded = PhotoResult(**d)
        assert len(reloaded.pred_bib_boxes) == 1
        assert reloaded.pred_bib_boxes[0].number == "42"
        assert len(reloaded.pred_face_boxes) == 1
        assert reloaded.pred_face_boxes[0].scope == "keep"
        assert len(reloaded.gt_bib_boxes) == 1
        assert len(reloaded.gt_face_boxes) == 1

    def test_backward_compat_old_dict_without_box_fields(self):
        old_dict = _photo_result_dict()
        # Simulate old JSON that never had these fields
        assert "pred_bib_boxes" not in old_dict
        pr = PhotoResult(**old_dict)
        assert pr.pred_bib_boxes is None
        assert pr.pred_face_boxes is None
        assert pr.gt_bib_boxes is None
        assert pr.gt_face_boxes is None

    def test_pred_links_default_none(self):
        pr = PhotoResult(**_photo_result_dict())
        assert pr.pred_links is None

    def test_pred_links_serialization(self):
        links = [BibFaceLink(bib_index=0, face_index=1), BibFaceLink(bib_index=2, face_index=0)]
        pr = PhotoResult(**_photo_result_dict(pred_links=links))
        d = pr.model_dump()
        assert d["pred_links"] == [
            {"bib_index": 0, "face_index": 1},
            {"bib_index": 2, "face_index": 0},
        ]
        reloaded = PhotoResult(**d)
        assert len(reloaded.pred_links) == 2
        assert reloaded.pred_links[0].bib_index == 0
        assert reloaded.pred_links[1].face_index == 0


class TestPhotoResultScorecards:
    def test_scorecards_default_none(self):
        pr = PhotoResult(**_photo_result_dict())
        assert pr.bib_scorecard is None
        assert pr.face_scorecard is None
        assert pr.link_scorecard is None
        assert pr.face_detection_time_ms is None

    def test_with_scorecards_roundtrip(self):
        bib_sc = BibScorecard(detection_tp=2, detection_fp=0, detection_fn=1, ocr_correct=2, ocr_total=2)
        face_sc = FaceScorecard(detection_tp=1, detection_fp=1, detection_fn=0)
        link_sc = LinkScorecard(link_tp=1, link_fp=0, link_fn=0, gt_link_count=1)
        pr = PhotoResult(**_photo_result_dict(
            bib_scorecard=bib_sc,
            face_scorecard=face_sc,
            link_scorecard=link_sc,
            face_detection_time_ms=42.5,
        ))
        d = pr.model_dump()
        assert d["bib_scorecard"]["detection_tp"] == 2
        assert d["bib_scorecard"]["ocr_correct"] == 2
        assert d["face_scorecard"]["detection_tp"] == 1
        assert d["link_scorecard"]["link_tp"] == 1
        assert d["face_detection_time_ms"] == 42.5
        reloaded = PhotoResult(**d)
        assert reloaded.bib_scorecard.detection_tp == 2
        assert reloaded.face_scorecard.detection_fp == 1
        assert reloaded.link_scorecard.gt_link_count == 1
        assert reloaded.face_detection_time_ms == 42.5

    def test_backward_compat_old_run_without_scorecards(self):
        old_dict = _photo_result_dict()
        assert "bib_scorecard" not in old_dict
        pr = PhotoResult(**old_dict)
        assert pr.bib_scorecard is None
        assert pr.face_scorecard is None
        assert pr.link_scorecard is None
        assert pr.face_detection_time_ms is None


class TestBoxConfidence:
    def test_bib_box_confidence_optional(self):
        box = BibBox(x=0.1, y=0.2, w=0.3, h=0.4, number="42")
        assert box.confidence is None
        box_with = BibBox(x=0.1, y=0.2, w=0.3, h=0.4, number="42", confidence=0.85)
        assert box_with.confidence == 0.85

    def test_face_box_confidence_optional(self):
        box = FaceBox(x=0.1, y=0.2, w=0.3, h=0.4, scope="keep")
        assert box.confidence is None
        box_with = FaceBox(x=0.1, y=0.2, w=0.3, h=0.4, scope="keep", confidence=0.9)
        assert box_with.confidence == 0.9

    def test_confidence_excluded_when_none(self):
        box = BibBox(x=0.1, y=0.2, w=0.3, h=0.4, number="42")
        d = box.model_dump(exclude_none=True)
        assert "confidence" not in d

    def test_confidence_included_when_set(self):
        box = BibBox(x=0.1, y=0.2, w=0.3, h=0.4, number="42", confidence=0.85)
        d = box.model_dump(exclude_none=True)
        assert d["confidence"] == 0.85


# =============================================================================
# BibCandidateSummary — round-trip and PhotoResult integration (task-062)
# =============================================================================


def _candidate_dict(**overrides) -> dict:
    base = {
        "x": 0.12, "y": 0.34, "w": 0.05, "h": 0.08,
        "area": 4200, "aspect_ratio": 1.6,
        "median_brightness": 220.0, "mean_brightness": 215.5,
        "relative_area": 0.003, "passed": True,
        "rejection_reason": None,
    }
    return {**base, **overrides}


class TestBibCandidateSummary:
    def test_round_trip(self):
        cs = BibCandidateSummary(**_candidate_dict())
        d = cs.model_dump()
        reloaded = BibCandidateSummary.model_validate(d)
        assert reloaded.x == cs.x
        assert reloaded.area == 4200
        assert reloaded.passed is True
        assert reloaded.rejection_reason is None

    def test_rejected_candidate_preserves_reason(self):
        cs = BibCandidateSummary(**_candidate_dict(
            passed=False, rejection_reason="too_small",
        ))
        d = cs.model_dump()
        reloaded = BibCandidateSummary.model_validate(d)
        assert reloaded.passed is False
        assert reloaded.rejection_reason == "too_small"


class TestPhotoResultBibCandidates:
    def test_with_candidates_round_trip(self):
        candidates = [
            BibCandidateSummary(**_candidate_dict()),
            BibCandidateSummary(**_candidate_dict(passed=False, rejection_reason="low_contrast")),
        ]
        pr = PhotoResult(**_photo_result_dict(bib_candidates=candidates))
        d = pr.model_dump()
        reloaded = PhotoResult.model_validate(d)
        assert len(reloaded.bib_candidates) == 2
        assert reloaded.bib_candidates[0].passed is True
        assert reloaded.bib_candidates[1].rejection_reason == "low_contrast"

    def test_without_candidates_backward_compat(self):
        old_dict = _photo_result_dict()
        assert "bib_candidates" not in old_dict
        pr = PhotoResult.model_validate(old_dict)
        assert pr.bib_candidates is None

"""TDD tests for custom serialisation logic in runner.py Pydantic models.

Covers the non-trivial validator/serialiser cases introduced when the runner
dataclasses were migrated to pydantic.BaseModel (task-034).
"""
from __future__ import annotations

import pytest

from benchmarking.runner import FacePipelineConfig, PipelineConfig, RunMetadata


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

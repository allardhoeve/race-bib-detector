"""TDD tests for task-037: Pydantic migration of remaining dataclasses.

Red tests first — these test custom logic (validators, serializers) that is
being ADDED as part of the migration. Green when implementation is done.
"""

from __future__ import annotations

import pytest


# =============================================================================
# IdentityMatch — similarity rounded to 4dp in model_dump()
# =============================================================================


class TestIdentityMatchSimilarityRounding:
    """model_dump() must round similarity to 4 decimal places."""

    def test_similarity_rounded_in_model_dump(self):
        from benchmarking.face_embeddings import IdentityMatch

        match = IdentityMatch(
            identity="alice",
            similarity=0.123456789,
            content_hash="abc",
            box_index=0,
        )
        d = match.model_dump()
        assert d["similarity"] == round(0.123456789, 4)

    def test_similarity_already_4dp_unchanged(self):
        from benchmarking.face_embeddings import IdentityMatch

        match = IdentityMatch(
            identity="alice",
            similarity=0.9512,
            content_hash="abc",
            box_index=0,
        )
        d = match.model_dump()
        assert d["similarity"] == 0.9512


# =============================================================================
# FaceModelInfo — embedding_dim coerced to int via model_validate()
# =============================================================================


class TestFaceModelInfoEmbeddingDimCoercion:
    """model_validate() must coerce embedding_dim from str/float to int."""

    def test_embedding_dim_coerces_string(self):
        from faces.types import FaceModelInfo

        info = FaceModelInfo.model_validate(
            {"name": "facenet", "version": "1.0", "embedding_dim": "512"}
        )
        assert info.embedding_dim == 512
        assert isinstance(info.embedding_dim, int)

    def test_embedding_dim_coerces_float(self):
        from faces.types import FaceModelInfo

        info = FaceModelInfo.model_validate(
            {"name": "facenet", "version": "1.0", "embedding_dim": 512.0}
        )
        assert info.embedding_dim == 512
        assert isinstance(info.embedding_dim, int)

    def test_embedding_dim_native_int_unchanged(self):
        from faces.types import FaceModelInfo

        info = FaceModelInfo.model_validate(
            {"name": "facenet", "version": "1.0", "embedding_dim": 128}
        )
        assert info.embedding_dim == 128

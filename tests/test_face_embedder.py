"""Tests for face embedding interface, implementations, and identity search."""

import numpy as np
import pytest

from faces.embedder import (
    PixelEmbedder,
    FaceNetEmbedder,
    get_face_embedder,
    get_face_embedder_by_name,
    _EMBEDDERS,
)
from benchmarking.face_embeddings import EmbeddingIndex, find_top_k, IdentityMatch


# =============================================================================
# PixelEmbedder tests
# =============================================================================


class TestPixelEmbedder:
    def test_produces_correct_dimensionality(self):
        embedder = PixelEmbedder(size=16)
        image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        # Create a 4-point bbox polygon: (0,0)-(50,0)-(50,50)-(0,50)
        bbox = [[0, 0], [50, 0], [50, 50], [0, 50]]
        embeddings = embedder.embed(image, [bbox])
        assert len(embeddings) == 1
        assert embeddings[0].shape == (16 * 16,)
        assert embeddings[0].dtype == np.float32

    def test_l2_normalized(self):
        embedder = PixelEmbedder(size=16)
        image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        bbox = [[10, 10], [60, 10], [60, 60], [10, 60]]
        embeddings = embedder.embed(image, [bbox])
        norm = np.linalg.norm(embeddings[0])
        assert norm == pytest.approx(1.0, abs=1e-5)

    def test_empty_boxes_returns_empty(self):
        embedder = PixelEmbedder()
        image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        embeddings = embedder.embed(image, [])
        assert embeddings == []

    def test_zero_area_box_returns_zeros(self):
        embedder = PixelEmbedder(size=8)
        image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        # Zero-area bbox (x1==x2)
        bbox = [[50, 50], [50, 50], [50, 60], [50, 60]]
        embeddings = embedder.embed(image, [bbox])
        assert len(embeddings) == 1
        assert np.all(embeddings[0] == 0)

    def test_model_info(self):
        embedder = PixelEmbedder(size=32)
        info = embedder.model_info()
        assert info.name == "pixel"
        assert info.embedding_dim == 32 * 32

    def test_rejects_non_rgb_image(self):
        embedder = PixelEmbedder()
        gray = np.zeros((100, 100), dtype=np.uint8)
        with pytest.raises(ValueError, match="Expected RGB"):
            embedder.embed(gray, [[[0, 0], [10, 0], [10, 10], [0, 10]]])

    def test_multiple_boxes(self):
        embedder = PixelEmbedder(size=8)
        image = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
        bbox1 = [[10, 10], [50, 10], [50, 50], [10, 50]]
        bbox2 = [[60, 60], [100, 60], [100, 100], [60, 100]]
        embeddings = embedder.embed(image, [bbox1, bbox2])
        assert len(embeddings) == 2
        assert embeddings[0].shape == (64,)
        assert embeddings[1].shape == (64,)


# =============================================================================
# FaceNetEmbedder tests (requires facenet-pytorch)
# =============================================================================


@pytest.fixture
def facenet_available():
    try:
        import facenet_pytorch  # noqa: F401
        return True
    except ImportError:
        return False


class TestFaceNetEmbedder:
    def test_produces_512_dim_embeddings(self, facenet_available):
        if not facenet_available:
            pytest.skip("facenet-pytorch not installed")
        embedder = FaceNetEmbedder()
        image = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
        bbox = [[20, 20], [160, 20], [160, 160], [20, 160]]
        embeddings = embedder.embed(image, [bbox])
        assert len(embeddings) == 1
        assert embeddings[0].shape == (512,)
        assert embeddings[0].dtype == np.float32

    def test_l2_normalized(self, facenet_available):
        if not facenet_available:
            pytest.skip("facenet-pytorch not installed")
        embedder = FaceNetEmbedder()
        image = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
        bbox = [[20, 20], [160, 20], [160, 160], [20, 160]]
        embeddings = embedder.embed(image, [bbox])
        norm = np.linalg.norm(embeddings[0])
        assert norm == pytest.approx(1.0, abs=1e-5)

    def test_model_info(self):
        embedder = FaceNetEmbedder()
        info = embedder.model_info()
        assert info.name == "facenet_vggface2"
        assert info.embedding_dim == 512

    def test_zero_area_box_returns_zeros(self, facenet_available):
        if not facenet_available:
            pytest.skip("facenet-pytorch not installed")
        embedder = FaceNetEmbedder()
        image = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
        bbox = [[50, 50], [50, 50], [50, 60], [50, 60]]
        embeddings = embedder.embed(image, [bbox])
        assert np.all(embeddings[0] == 0)


# =============================================================================
# Registry / factory tests
# =============================================================================


class TestEmbedderRegistry:
    def test_pixel_registered(self):
        assert "pixel" in _EMBEDDERS

    def test_facenet_registered(self):
        assert "facenet" in _EMBEDDERS

    def test_get_by_name_pixel(self):
        embedder = get_face_embedder_by_name("pixel")
        assert isinstance(embedder, PixelEmbedder)

    def test_get_by_name_facenet(self):
        embedder = get_face_embedder_by_name("facenet")
        assert isinstance(embedder, FaceNetEmbedder)

    def test_get_by_name_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown face embedder"):
            get_face_embedder_by_name("nonexistent")

    def test_get_default_uses_config(self, monkeypatch):
        monkeypatch.setattr("config.FACE_EMBEDDER", "pixel")
        embedder = get_face_embedder()
        assert isinstance(embedder, PixelEmbedder)


# =============================================================================
# find_top_k tests
# =============================================================================


class TestFindTopK:
    def _make_index(self, identities, embeddings):
        return EmbeddingIndex(
            embeddings=np.array(embeddings, dtype=np.float32),
            identities=identities,
            content_hashes=["hash_" + str(i) for i in range(len(identities))],
            box_indices=list(range(len(identities))),
        )

    def test_returns_correct_ordering(self):
        # Create embeddings: Alice is close to query, Bob is far
        index = self._make_index(
            ["Alice", "Bob"],
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        )
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        results = find_top_k(query, index, k=5)
        assert len(results) == 2
        assert results[0].identity == "Alice"
        assert results[0].similarity > results[1].similarity

    def test_respects_k_limit(self):
        index = self._make_index(
            ["A", "B", "C"],
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        )
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        results = find_top_k(query, index, k=1)
        assert len(results) == 1
        assert results[0].identity == "A"

    def test_empty_index_returns_empty(self):
        index = EmbeddingIndex(
            embeddings=np.empty((0, 3), dtype=np.float32),
        )
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        results = find_top_k(query, index)
        assert results == []

    def test_deduplicates_by_identity(self):
        # Two entries for "Alice" with different embeddings
        index = self._make_index(
            ["Alice", "Alice", "Bob"],
            [[0.9, 0.1, 0.0], [0.8, 0.2, 0.0], [0.0, 1.0, 0.0]],
        )
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        results = find_top_k(query, index, k=5)
        identities = [r.identity for r in results]
        assert identities.count("Alice") == 1
        assert "Bob" in identities

    def test_result_has_correct_fields(self):
        index = self._make_index(["Alice"], [[1.0, 0.0, 0.0]])
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        results = find_top_k(query, index, k=1)
        assert len(results) == 1
        r = results[0]
        assert isinstance(r, IdentityMatch)
        assert r.identity == "Alice"
        assert r.similarity == pytest.approx(1.0, abs=0.01)
        assert r.content_hash == "hash_0"
        assert r.box_index == 0

    def test_to_dict(self):
        match = IdentityMatch(
            identity="Alice", similarity=0.9512, content_hash="abc123", box_index=2
        )
        d = match.to_dict()
        assert d == {
            "identity": "Alice",
            "similarity": 0.9512,
            "content_hash": "abc123",
            "box_index": 2,
        }

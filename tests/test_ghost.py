"""TDD tests for benchmarking.ghost — precomputed detection suggestions."""

from __future__ import annotations

import json

import pytest

from benchmarking.ghost import (
    BibSuggestion,
    Provenance,
    PhotoSuggestions,
    SuggestionStore,
    load_suggestion_store,
    save_suggestion_store,
    normalize_quad,
)


# =============================================================================
# SuggestionStore
# =============================================================================


class TestSuggestionStore:
    def test_empty(self):
        store = SuggestionStore()
        assert store.get("abc") is None
        assert not store.has("abc")

    def test_add_and_get(self):
        store = SuggestionStore()
        ps = PhotoSuggestions(content_hash="abc")
        store.add(ps)
        assert store.has("abc")
        assert store.get("abc") is ps

    def test_overwrite(self):
        store = SuggestionStore()
        ps1 = PhotoSuggestions(content_hash="abc")
        ps2 = PhotoSuggestions(
            content_hash="abc",
            bibs=[BibSuggestion(x=0.1, y=0.2, w=0.3, h=0.15, number="99", confidence=0.5)],
        )
        store.add(ps1)
        store.add(ps2)
        assert len(store.get("abc").bibs) == 1

    def test_hashes(self):
        store = SuggestionStore()
        store.add(PhotoSuggestions(content_hash="aaa"))
        store.add(PhotoSuggestions(content_hash="bbb"))
        assert store.hashes() == {"aaa", "bbb"}


# =============================================================================
# load/save
# =============================================================================


class TestLoadSave:
    def test_nonexistent_returns_empty(self, tmp_path):
        store = load_suggestion_store(tmp_path / "missing.json")
        assert not store.has("anything")

    def test_round_trip(self, tmp_path):
        path = tmp_path / "suggestions.json"
        store = SuggestionStore()
        prov = Provenance(backend="test", version="1.0", config={})
        store.add(PhotoSuggestions(
            content_hash="h1",
            bibs=[BibSuggestion(x=0.1, y=0.2, w=0.3, h=0.15, number="42", confidence=0.9)],
            provenance=prov,
        ))

        save_suggestion_store(store, path)
        store2 = load_suggestion_store(path)

        assert store2.has("h1")
        assert store2.get("h1").bibs[0].number == "42"

    def test_valid_json(self, tmp_path):
        path = tmp_path / "suggestions.json"
        store = SuggestionStore()
        store.add(PhotoSuggestions(content_hash="h1"))
        save_suggestion_store(store, path)

        data = json.loads(path.read_text())
        assert "photos" in data
        assert "h1" in data["photos"]


# =============================================================================
# normalize_quad
# =============================================================================


class TestNormalizeQuad:
    """normalize_quad converts a pixel-space quadrilateral to normalised (x, y, w, h)."""

    def test_basic(self):
        # 100x200 image, box at top-left quarter
        quad = [[0, 0], [50, 0], [50, 100], [0, 100]]
        x, y, w, h = normalize_quad(quad, img_width=100, img_height=200)
        assert x == pytest.approx(0.0)
        assert y == pytest.approx(0.0)
        assert w == pytest.approx(0.5)
        assert h == pytest.approx(0.5)

    def test_offset_box(self):
        quad = [[100, 200], [300, 200], [300, 400], [100, 400]]
        x, y, w, h = normalize_quad(quad, img_width=400, img_height=800)
        assert x == pytest.approx(0.25)
        assert y == pytest.approx(0.25)
        assert w == pytest.approx(0.5)
        assert h == pytest.approx(0.25)

    def test_zero_size_image(self):
        quad = [[0, 0], [10, 0], [10, 10], [0, 10]]
        x, y, w, h = normalize_quad(quad, img_width=0, img_height=0)
        assert x == 0.0 and y == 0.0 and w == 0.0 and h == 0.0

    def test_rotated_quad_uses_bounding_rect(self):
        """Non-axis-aligned quad → bounding rectangle used."""
        quad = [[10, 0], [20, 10], [10, 20], [0, 10]]
        x, y, w, h = normalize_quad(quad, img_width=100, img_height=100)
        assert x == pytest.approx(0.0)
        assert y == pytest.approx(0.0)
        assert w == pytest.approx(0.2)
        assert h == pytest.approx(0.2)

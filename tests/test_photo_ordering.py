"""Tests for the photo ordering contract between runner and frozen gallery.

Both the benchmark runner ([N/total] in log output) and the frozen-set
gallery (#N in the thumbnail grid) must iterate photos in snapshot.hashes
order.  _select_photo_hashes is the single place that enforces this for
the runner side.  These tests ensure the contract is not accidentally broken.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarking.photo_metadata import PhotoMetadata, PhotoMetadataStore
from benchmarking.runner import _select_photo_hashes
from benchmarking.sets import BenchmarkSnapshot, BenchmarkSnapshotMetadata, FROZEN_DIR


@pytest.fixture()
def frozen_dir(tmp_path, monkeypatch):
    """Redirect FROZEN_DIR to a temp directory for test isolation."""
    monkeypatch.setattr("benchmarking.sets.FROZEN_DIR", tmp_path)
    return tmp_path


def _make_frozen_set(frozen_dir: Path, name: str, hashes: list[str]) -> None:
    """Write a minimal frozen set with the given hash order."""
    d = frozen_dir / name
    d.mkdir()
    (d / "index.json").write_text(json.dumps({
        "hashes": hashes,
        "index": {h: f"{h}.jpg" for h in hashes},
    }))
    (d / "metadata.json").write_text(json.dumps({
        "name": name,
        "created_at": "2026-01-01T00:00:00",
        "photo_count": len(hashes),
    }))


def _make_meta_store(hash_split_pairs: list[tuple[str, str]]) -> PhotoMetadataStore:
    """Build a PhotoMetadataStore from (hash, split) pairs.

    Order of pairs determines metadata iteration order.
    """
    store = PhotoMetadataStore()
    for h, split in hash_split_pairs:
        store.set(h, PhotoMetadata(split=split))
    return store


# =========================================================================
# Frozen set: ordering must follow snapshot.hashes
# =========================================================================


class TestFrozenSetOrdering:
    """When a frozen set is specified, photo order comes from snapshot.hashes."""

    def test_frozen_full_uses_snapshot_order(self, frozen_dir):
        """split='full' + frozen set → exact snapshot.hashes order."""
        snapshot_order = ["hash_c", "hash_a", "hash_b"]
        _make_frozen_set(frozen_dir, "test-set", snapshot_order)

        # Metadata has a DIFFERENT insertion order
        meta = _make_meta_store([
            ("hash_a", "iteration"),
            ("hash_b", "iteration"),
            ("hash_c", "iteration"),
        ])

        result = _select_photo_hashes("full", meta, "test-set")
        assert result == snapshot_order

    def test_frozen_full_is_complete(self, frozen_dir):
        """split='full' returns every hash in the frozen set."""
        hashes = ["h1", "h2", "h3", "h4"]
        _make_frozen_set(frozen_dir, "test-set", hashes)

        # Only some hashes are in metadata — doesn't matter for split='full'
        meta = _make_meta_store([("h1", "iteration"), ("h3", "")])

        result = _select_photo_hashes("full", meta, "test-set")
        assert result == hashes

    def test_frozen_iteration_preserves_snapshot_order(self, frozen_dir):
        """split='iteration' + frozen set → intersection in snapshot order."""
        snapshot_order = ["hash_c", "hash_a", "hash_b"]
        _make_frozen_set(frozen_dir, "test-set", snapshot_order)

        # Only hash_a and hash_c are in the iteration split
        meta = _make_meta_store([
            ("hash_a", "iteration"),
            ("hash_b", ""),           # not in iteration split
            ("hash_c", "iteration"),
        ])

        result = _select_photo_hashes("iteration", meta, "test-set")
        # snapshot order is [c, a, b]; after filtering out b → [c, a]
        assert result == ["hash_c", "hash_a"]

    def test_frozen_iteration_filters_non_split_hashes(self, frozen_dir):
        """Hashes in the frozen set but not in the split are excluded."""
        _make_frozen_set(frozen_dir, "test-set", ["h1", "h2", "h3"])

        meta = _make_meta_store([
            ("h1", "iteration"),
            ("h2", ""),          # not in iteration
            ("h3", "iteration"),
        ])

        result = _select_photo_hashes("iteration", meta, "test-set")
        assert "h2" not in result
        assert result == ["h1", "h3"]


# =========================================================================
# No frozen set: ordering comes from metadata
# =========================================================================


class TestNoFrozenSet:
    """Without a frozen set, ordering comes from the metadata store."""

    def test_full_split_returns_all_in_metadata_order(self, frozen_dir):
        meta = _make_meta_store([
            ("hash_b", "iteration"),
            ("hash_a", ""),
            ("hash_c", "iteration"),
        ])

        result = _select_photo_hashes("full", meta, None)
        assert result == ["hash_b", "hash_a", "hash_c"]

    def test_iteration_split_filters_correctly(self, frozen_dir):
        meta = _make_meta_store([
            ("hash_b", "iteration"),
            ("hash_a", ""),
            ("hash_c", "iteration"),
        ])

        result = _select_photo_hashes("iteration", meta, None)
        assert result == ["hash_b", "hash_c"]


# =========================================================================
# Gallery template contract (structural check)
# =========================================================================


class TestGalleryUsesSnapshotOrder:
    """The frozen gallery template must iterate snapshot.hashes.

    This is a structural test: it reads the template source and verifies
    the iteration variable matches the runner's source of order.
    """

    def test_template_iterates_snapshot_hashes(self):
        template_path = (
            Path(__file__).parent.parent
            / "benchmarking" / "templates" / "frozen_set_photos.html"
        )
        source = template_path.read_text()
        assert "{% for h in snapshot.hashes %}" in source, (
            "Gallery template must iterate snapshot.hashes to match "
            "the runner's photo ordering contract"
        )

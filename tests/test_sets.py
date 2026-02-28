"""Tests for benchmarking/sets.py — frozen snapshot data layer."""

from __future__ import annotations

import json

import pytest

import benchmarking.sets as sets_module
from benchmarking.photo_metadata import (
    PhotoMetadata,
    PhotoMetadataStore,
    load_photo_metadata,
    save_photo_metadata,
)
from benchmarking.sets import BenchmarkSnapshot, freeze, list_snapshots


@pytest.fixture(autouse=True)
def isolated_frozen_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(sets_module, "FROZEN_DIR", tmp_path / "frozen")
    # Also isolate photo_metadata.json
    meta_path = tmp_path / "photo_metadata.json"
    monkeypatch.setattr(
        "benchmarking.photo_metadata.get_photo_metadata_path", lambda: meta_path
    )


# ---------------------------------------------------------------------------
# freeze()
# ---------------------------------------------------------------------------


class TestFreeze:
    def test_creates_metadata_and_index_files(self, tmp_path):
        snapshot = freeze(
            name="v1",
            hashes=["abc123"],
            index={"abc123": "photo_a.jpg"},
        )
        frozen_dir = sets_module.FROZEN_DIR
        assert (frozen_dir / "v1" / "metadata.json").exists()
        assert (frozen_dir / "v1" / "index.json").exists()

    def test_metadata_contents(self):
        snapshot = freeze(
            name="v1",
            hashes=["abc123", "def456"],
            index={"abc123": "a.jpg", "def456": "b.jpg"},
            description="test run",
        )
        with open(snapshot.path / "metadata.json") as f:
            meta = json.load(f)
        assert meta["name"] == "v1"
        assert meta["photo_count"] == 2
        assert meta["description"] == "test run"
        assert "created_at" in meta

    def test_index_contents(self):
        snapshot = freeze(
            name="v1",
            hashes=["abc123"],
            index={"abc123": "photo_a.jpg"},
        )
        with open(snapshot.path / "index.json") as f:
            data = json.load(f)
        assert data["hashes"] == ["abc123"]
        assert data["index"] == {"abc123": "photo_a.jpg"}

    def test_name_conflict_raises(self):
        freeze(name="v1", hashes=[], index={})
        with pytest.raises(ValueError, match="Snapshot already exists"):
            freeze(name="v1", hashes=[], index={})

    def test_description_defaults_to_empty(self):
        snapshot = freeze(name="v1", hashes=[], index={})
        assert snapshot.metadata.description == ""

    def test_returns_snapshot_with_correct_metadata(self):
        snapshot = freeze(
            name="mysnap",
            hashes=["h1", "h2", "h3"],
            index={"h1": "a.jpg", "h2": "b.jpg", "h3": "c.jpg"},
        )
        assert snapshot.metadata.name == "mysnap"
        assert snapshot.metadata.photo_count == 3


# ---------------------------------------------------------------------------
# BenchmarkSnapshot.load()
# ---------------------------------------------------------------------------


class TestSnapshotLoadRoundtrip:
    def test_roundtrip(self):
        original = freeze(
            name="snap",
            hashes=["aaa", "bbb"],
            index={"aaa": "x.jpg", "bbb": "y.jpg"},
            description="hello",
        )
        loaded = BenchmarkSnapshot.load("snap")
        assert loaded.metadata.name == original.metadata.name
        assert loaded.metadata.photo_count == original.metadata.photo_count
        assert loaded.metadata.description == original.metadata.description
        assert loaded.metadata.created_at == original.metadata.created_at
        assert loaded.hashes == original.hashes
        assert loaded.index == original.index


# ---------------------------------------------------------------------------
# list_snapshots()
# ---------------------------------------------------------------------------


class TestListSnapshots:
    def test_empty_when_no_frozen_dir(self):
        # FROZEN_DIR does not exist yet
        assert list_snapshots() == []

    def test_returns_all_snapshots(self):
        freeze(name="alpha", hashes=["h1"], index={"h1": "a.jpg"})
        freeze(name="beta", hashes=["h2", "h3"], index={"h2": "b.jpg", "h3": "c.jpg"})
        snaps = list_snapshots()
        names = {s.name for s in snaps}
        assert names == {"alpha", "beta"}

    def test_sorted_by_created_at_descending(self):
        freeze(name="first", hashes=[], index={})
        freeze(name="second", hashes=[], index={})
        freeze(name="third", hashes=[], index={})
        snaps = list_snapshots()
        # Most recently created should be first
        assert snaps[0].name == "third"
        assert snaps[-1].name == "first"

    def test_skips_dirs_without_metadata(self, tmp_path):
        # A directory without metadata.json should be silently ignored
        sets_module.FROZEN_DIR.mkdir(parents=True)
        (sets_module.FROZEN_DIR / "orphan").mkdir()
        freeze(name="valid", hashes=[], index={})
        snaps = list_snapshots()
        assert len(snaps) == 1
        assert snaps[0].name == "valid"


# ---------------------------------------------------------------------------
# Freeze stamps PhotoMetadata
# ---------------------------------------------------------------------------


class TestFreezeStampsMetadata:
    def test_freeze_stamps_photo_metadata(self):
        freeze(name="v1", hashes=["abc123"], index={"abc123": "a.jpg"})
        store = load_photo_metadata()
        meta = store.get("abc123")
        assert meta is not None
        assert meta.frozen == "v1"

    def test_refreeze_overwrites(self, tmp_path):
        """Re-freezing with a different name overwrites the frozen field."""
        # First freeze
        freeze(name="v1", hashes=["abc123"], index={"abc123": "a.jpg"})
        store = load_photo_metadata()
        assert store.get("abc123").frozen == "v1"

        # Second freeze (different name, must clear existing dir check)
        freeze(name="v2", hashes=["abc123"], index={"abc123": "a.jpg"})
        store = load_photo_metadata()
        assert store.get("abc123").frozen == "v2"

    def test_freeze_preserves_existing_metadata_fields(self):
        """Freezing should not clobber existing fields like split or tags."""
        store = PhotoMetadataStore()
        store.set("abc123", PhotoMetadata(
            paths=["a.jpg"], split="iteration", bib_tags=["no_bib"],
        ))
        save_photo_metadata(store)

        freeze(name="v1", hashes=["abc123"], index={"abc123": "a.jpg"})
        store = load_photo_metadata()
        meta = store.get("abc123")
        assert meta.frozen == "v1"
        assert meta.split == "iteration"
        assert meta.bib_tags == ["no_bib"]

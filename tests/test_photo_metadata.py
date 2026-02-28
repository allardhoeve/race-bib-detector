"""Tests for benchmarking.photo_metadata — PhotoMetadata model and store."""

from __future__ import annotations

import pytest

from benchmarking.photo_metadata import (
    PhotoMetadata,
    PhotoMetadataStore,
    load_photo_metadata,
    save_photo_metadata,
)


class TestPhotoMetadataRoundtrip:
    def test_save_load_preserves_all_fields(self, tmp_path):
        store = PhotoMetadataStore()
        store.set("abc123", PhotoMetadata(
            paths=["photo1.jpg", "photo1_dup.jpg"],
            split="iteration",
            bib_tags=["no_bib"],
            face_tags=["no_faces"],
        ))
        path = tmp_path / "photo_metadata.json"
        save_photo_metadata(store, path)
        loaded = load_photo_metadata(path)
        meta = loaded.get("abc123")
        assert meta is not None
        assert meta.paths == ["photo1.jpg", "photo1_dup.jpg"]
        assert meta.split == "iteration"
        assert meta.bib_tags == ["no_bib"]
        assert meta.face_tags == ["no_faces"]


class TestPhotoMetadataDefaults:
    def test_missing_optional_fields_get_defaults(self):
        meta = PhotoMetadata(paths=["a.jpg"])
        assert meta.split == ""
        assert meta.bib_tags == []
        assert meta.face_tags == []


class TestPhotoMetadataStoreGetSet:
    def test_get_returns_none_for_missing(self):
        store = PhotoMetadataStore()
        assert store.get("nonexistent") is None

    def test_set_then_get(self):
        store = PhotoMetadataStore()
        meta = PhotoMetadata(paths=["x.jpg"], split="full")
        store.set("hash1", meta)
        assert store.get("hash1") is meta

    def test_set_overwrites(self):
        store = PhotoMetadataStore()
        store.set("h", PhotoMetadata(paths=["a.jpg"]))
        store.set("h", PhotoMetadata(paths=["b.jpg"]))
        assert store.get("h").paths == ["b.jpg"]


class TestGetHashesBySplit:
    def _store(self):
        store = PhotoMetadataStore()
        store.set("a", PhotoMetadata(paths=["a.jpg"], split="full"))
        store.set("b", PhotoMetadata(paths=["b.jpg"], split="iteration"))
        store.set("c", PhotoMetadata(paths=["c.jpg"], split="full"))
        return store

    def test_full_returns_all(self):
        store = self._store()
        hashes = store.get_hashes_by_split("full")
        assert set(hashes) == {"a", "b", "c"}

    def test_iteration_returns_filtered(self):
        store = self._store()
        hashes = store.get_hashes_by_split("iteration")
        assert hashes == ["b"]


class TestBibTagValidation:
    def test_invalid_bib_tag_rejected(self):
        with pytest.raises(ValueError, match="Invalid bib photo tags"):
            PhotoMetadata(paths=["a.jpg"], bib_tags=["not_a_real_tag"])

    def test_valid_bib_tag_accepted(self):
        meta = PhotoMetadata(paths=["a.jpg"], bib_tags=["no_bib", "dark_bib"])
        assert meta.bib_tags == ["no_bib", "dark_bib"]


class TestFaceTagValidation:
    def test_invalid_face_tag_rejected(self):
        with pytest.raises(ValueError, match="Invalid face photo tags"):
            PhotoMetadata(paths=["a.jpg"], face_tags=["bogus"])

    def test_valid_face_tag_accepted(self):
        meta = PhotoMetadata(paths=["a.jpg"], face_tags=["no_faces"])
        assert meta.face_tags == ["no_faces"]


class TestSplitValidation:
    def test_invalid_split_rejected(self):
        with pytest.raises(ValueError, match="Invalid split"):
            PhotoMetadata(paths=["a.jpg"], split="bogus")

    def test_empty_string_accepted(self):
        meta = PhotoMetadata(paths=["a.jpg"], split="")
        assert meta.split == ""

    def test_valid_splits_accepted(self):
        for split in ("iteration", "full"):
            meta = PhotoMetadata(paths=["a.jpg"], split=split)
            assert meta.split == split


class TestLoadNonexistent:
    def test_load_nonexistent_returns_empty(self, tmp_path):
        store = load_photo_metadata(tmp_path / "nonexistent.json")
        assert len(store.photos) == 0

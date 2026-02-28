"""Tests for benchmarking.migrate_photo_metadata."""

from __future__ import annotations

import json

import pytest

from benchmarking.migrate_photo_metadata import migrate


def _write_json(path, data):
    path.write_text(json.dumps(data, indent=2))


@pytest.fixture
def migration_workspace(tmp_path):
    """Create a workspace with old-format JSON files for migration testing."""
    index_path = tmp_path / "photo_index.json"
    bib_gt_path = tmp_path / "bib_ground_truth.json"
    face_gt_path = tmp_path / "face_ground_truth.json"
    metadata_path = tmp_path / "photo_metadata.json"

    # Old photo_index.json
    _write_json(index_path, {
        "aaa111": ["photo_a.jpg"],
        "bbb222": ["photo_b.jpg", "photo_b_dup.jpg"],
    })

    # Old bib_ground_truth.json (with split and tags on photos)
    _write_json(bib_gt_path, {
        "version": 3,
        "photos": {
            "aaa111": {
                "boxes": [{"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4, "number": "42", "scope": "bib"}],
                "tags": ["dark_bib"],
                "split": "iteration",
                "labeled": True,
            },
            "bbb222": {
                "boxes": [],
                "tags": [],
                "split": "full",
                "labeled": False,
            },
        },
    })

    # Old face_ground_truth.json (with tags on photos)
    _write_json(face_gt_path, {
        "version": 3,
        "photos": {
            "aaa111": {
                "boxes": [],
                "tags": ["no_faces"],
                "labeled": False,
            },
            "bbb222": {
                "boxes": [{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2, "scope": "keep", "tags": []}],
                "tags": [],
                "labeled": True,
            },
        },
    })

    return {
        "index_path": index_path,
        "bib_gt_path": bib_gt_path,
        "face_gt_path": face_gt_path,
        "metadata_path": metadata_path,
    }


class TestMigratePhotos:
    def test_migrate_merges_all_sources(self, migration_workspace):
        """Paths, split, bib_tags, face_tags all present after migration."""
        store = migrate(
            index_path=migration_workspace["index_path"],
            bib_gt_path=migration_workspace["bib_gt_path"],
            face_gt_path=migration_workspace["face_gt_path"],
            metadata_path=migration_workspace["metadata_path"],
            delete_old_index=False,
        )

        meta_a = store.get("aaa111")
        assert meta_a is not None
        assert meta_a.paths == ["photo_a.jpg"]
        assert meta_a.split == "iteration"
        assert meta_a.bib_tags == ["dark_bib"]
        assert meta_a.face_tags == ["no_faces"]

        meta_b = store.get("bbb222")
        assert meta_b is not None
        assert meta_b.paths == ["photo_b.jpg", "photo_b_dup.jpg"]
        assert meta_b.split == "full"
        assert meta_b.bib_tags == []
        assert meta_b.face_tags == []

    def test_migrate_preserves_all_tags(self, migration_workspace):
        """No tags lost during migration."""
        store = migrate(
            index_path=migration_workspace["index_path"],
            bib_gt_path=migration_workspace["bib_gt_path"],
            face_gt_path=migration_workspace["face_gt_path"],
            metadata_path=migration_workspace["metadata_path"],
            delete_old_index=False,
        )

        assert store.get("aaa111").bib_tags == ["dark_bib"]
        assert store.get("aaa111").face_tags == ["no_faces"]

    def test_migrate_preserves_all_splits(self, migration_workspace):
        """No splits lost during migration."""
        store = migrate(
            index_path=migration_workspace["index_path"],
            bib_gt_path=migration_workspace["bib_gt_path"],
            face_gt_path=migration_workspace["face_gt_path"],
            metadata_path=migration_workspace["metadata_path"],
            delete_old_index=False,
        )

        assert store.get("aaa111").split == "iteration"
        assert store.get("bbb222").split == "full"

    def test_migrate_strips_tags_from_gt(self, migration_workspace):
        """After migration, GT files no longer contain split/tags."""
        migrate(
            index_path=migration_workspace["index_path"],
            bib_gt_path=migration_workspace["bib_gt_path"],
            face_gt_path=migration_workspace["face_gt_path"],
            metadata_path=migration_workspace["metadata_path"],
            delete_old_index=False,
        )

        # Check bib GT
        with open(migration_workspace["bib_gt_path"]) as f:
            bib_data = json.load(f)
        for photo_data in bib_data["photos"].values():
            assert "tags" not in photo_data
            assert "split" not in photo_data

        # Check face GT
        with open(migration_workspace["face_gt_path"]) as f:
            face_data = json.load(f)
        for photo_data in face_data["photos"].values():
            assert "tags" not in photo_data

    def test_migrate_deletes_old_index(self, migration_workspace):
        """Old photo_index.json is deleted after migration."""
        migrate(
            index_path=migration_workspace["index_path"],
            bib_gt_path=migration_workspace["bib_gt_path"],
            face_gt_path=migration_workspace["face_gt_path"],
            metadata_path=migration_workspace["metadata_path"],
            delete_old_index=True,
        )
        assert not migration_workspace["index_path"].exists()

    def test_migrate_creates_metadata_file(self, migration_workspace):
        """photo_metadata.json is created."""
        migrate(
            index_path=migration_workspace["index_path"],
            bib_gt_path=migration_workspace["bib_gt_path"],
            face_gt_path=migration_workspace["face_gt_path"],
            metadata_path=migration_workspace["metadata_path"],
            delete_old_index=False,
        )
        assert migration_workspace["metadata_path"].exists()

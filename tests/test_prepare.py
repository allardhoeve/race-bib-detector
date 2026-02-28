"""TDD tests for benchmarking.prepare — benchmark prepare command."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmarking.prepare import prepare_benchmark, PrepareResult
from benchmarking.ground_truth import (
    BibBox,
    BibPhotoLabel,
    FacePhotoLabel,
    BibGroundTruth,
    FaceGroundTruth,
    load_bib_ground_truth,
    save_bib_ground_truth,
    load_face_ground_truth,
    save_face_ground_truth,
)
from benchmarking.photo_index import load_photo_index, save_photo_index
from benchmarking.photo_metadata import load_photo_metadata
from benchmarking.scanner import compute_content_hash


def _make_image(path: Path, content: bytes = b"fake-jpeg-content") -> None:
    """Create a minimal file that passes the image extension check."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


@pytest.fixture
def workspace(tmp_path):
    """Create a workspace with source_dir, photos_dir, and GT paths."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    bib_gt_path = tmp_path / "bib_ground_truth.json"
    face_gt_path = tmp_path / "face_ground_truth.json"
    index_path = tmp_path / "photo_index.json"
    return {
        "source_dir": source_dir,
        "photos_dir": photos_dir,
        "bib_gt_path": bib_gt_path,
        "face_gt_path": face_gt_path,
        "index_path": index_path,
    }


def _prepare(workspace, **kwargs) -> PrepareResult:
    """Helper to call prepare_benchmark with workspace paths."""
    return prepare_benchmark(
        source_dir=workspace["source_dir"],
        photos_dir=workspace["photos_dir"],
        bib_gt_path=workspace["bib_gt_path"],
        face_gt_path=workspace["face_gt_path"],
        index_path=workspace["index_path"],
        **kwargs,
    )


# =============================================================================
# Copy photos with dedup
# =============================================================================


class TestCopyPhotos:
    """prepare_benchmark copies photos from source to photos_dir, deduped by hash."""

    def test_copies_image_files(self, workspace):
        _make_image(workspace["source_dir"] / "photo1.jpg", b"image-one")
        _make_image(workspace["source_dir"] / "photo2.jpg", b"image-two")

        result = _prepare(workspace)

        assert result.copied == 2
        assert result.skipped == 0
        # Photos should exist in photos_dir
        copied_files = list(workspace["photos_dir"].rglob("*.jpg"))
        assert len(copied_files) == 2

    def test_skips_non_image_files(self, workspace):
        _make_image(workspace["source_dir"] / "photo.jpg", b"image")
        (workspace["source_dir"] / "readme.txt").write_text("not an image")

        result = _prepare(workspace)

        assert result.copied == 1
        copied_files = list(workspace["photos_dir"].rglob("*"))
        # Only image files should be copied
        assert all(f.suffix == ".jpg" for f in copied_files if f.is_file())

    def test_dedup_by_hash(self, workspace):
        """Two files with same content → only one copy."""
        _make_image(workspace["source_dir"] / "photo_a.jpg", b"same-content")
        _make_image(workspace["source_dir"] / "photo_b.jpg", b"same-content")

        result = _prepare(workspace)

        assert result.copied == 1
        assert result.skipped == 1

    def test_skips_already_present(self, workspace):
        """Photo already in photos_dir → not copied again."""
        _make_image(workspace["source_dir"] / "photo.jpg", b"existing")
        # Pre-place in photos_dir
        _make_image(workspace["photos_dir"] / "photo.jpg", b"existing")

        result = _prepare(workspace)

        assert result.copied == 0
        assert result.skipped == 1

    def test_copies_from_subdirectories(self, workspace):
        """Source dir with subdirectories → all images found recursively."""
        _make_image(workspace["source_dir"] / "sub" / "deep.jpg", b"deep-image")

        result = _prepare(workspace)

        assert result.copied == 1

    def test_multiple_formats(self, workspace):
        """Supports jpg, jpeg, png, gif, bmp, webp."""
        _make_image(workspace["source_dir"] / "a.jpg", b"jpg")
        _make_image(workspace["source_dir"] / "b.png", b"png")
        _make_image(workspace["source_dir"] / "c.webp", b"webp")

        result = _prepare(workspace)

        assert result.copied == 3

    def test_empty_source_dir(self, workspace):
        result = _prepare(workspace)
        assert result.copied == 0
        assert result.skipped == 0
        assert result.total_photos == 0


# =============================================================================
# Photo index update
# =============================================================================


class TestIndexUpdate:
    """prepare_benchmark updates photo_index.json after copying."""

    def test_index_created_for_new_photos(self, workspace):
        _make_image(workspace["source_dir"] / "photo.jpg", b"content-A")

        _prepare(workspace)

        index = load_photo_index(workspace["index_path"])
        assert len(index) == 1
        hash_val = compute_content_hash(workspace["source_dir"] / "photo.jpg")
        assert hash_val in index

    def test_index_includes_existing_photos(self, workspace):
        """Index includes both old and new photos."""
        _make_image(workspace["photos_dir"] / "old.jpg", b"old-content")
        # Pre-build index with old photo
        old_hash = compute_content_hash(workspace["photos_dir"] / "old.jpg")
        save_photo_index({old_hash: ["old.jpg"]}, workspace["index_path"])

        _make_image(workspace["source_dir"] / "new.jpg", b"new-content")

        _prepare(workspace)

        index = load_photo_index(workspace["index_path"])
        new_hash = compute_content_hash(workspace["source_dir"] / "new.jpg")
        assert old_hash in index
        assert new_hash in index

    def test_index_paths_relative_to_photos_dir(self, workspace):
        _make_image(workspace["source_dir"] / "photo.jpg", b"data")

        _prepare(workspace)

        index = load_photo_index(workspace["index_path"])
        for paths in index.values():
            for p in paths:
                assert not Path(p).is_absolute()


# =============================================================================
# Ground truth entries
# =============================================================================


class TestGroundTruthEntries:
    """prepare_benchmark creates empty GT entries for new photos."""

    def test_bib_gt_entry_created(self, workspace):
        _make_image(workspace["source_dir"] / "photo.jpg", b"bib-content")
        hash_val = compute_content_hash(workspace["source_dir"] / "photo.jpg")

        _prepare(workspace)

        bib_gt = load_bib_ground_truth(workspace["bib_gt_path"])
        assert bib_gt.has_photo(hash_val)
        label = bib_gt.get_photo(hash_val)
        assert label.boxes == []
        assert label.labeled is False

    def test_face_gt_entry_created(self, workspace):
        _make_image(workspace["source_dir"] / "photo.jpg", b"face-content")
        hash_val = compute_content_hash(workspace["source_dir"] / "photo.jpg")

        _prepare(workspace)

        face_gt = load_face_ground_truth(workspace["face_gt_path"])
        assert face_gt.has_photo(hash_val)
        label = face_gt.get_photo(hash_val)
        assert label.boxes == []

    def test_does_not_overwrite_existing_labels(self, workspace):
        """If a photo already has labels, prepare should not overwrite them."""
        _make_image(workspace["source_dir"] / "photo.jpg", b"labeled-photo")
        hash_val = compute_content_hash(workspace["source_dir"] / "photo.jpg")

        # Pre-create a labeled entry
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(BibPhotoLabel(
            content_hash=hash_val,
            boxes=[BibBox(x=0.1, y=0.2, w=0.3, h=0.4, number="42")],
            labeled=True,
        ))
        save_bib_ground_truth(bib_gt, workspace["bib_gt_path"])

        # Pre-place in photos_dir so it's "already present"
        _make_image(workspace["photos_dir"] / "photo.jpg", b"labeled-photo")

        _prepare(workspace)

        bib_gt = load_bib_ground_truth(workspace["bib_gt_path"])
        label = bib_gt.get_photo(hash_val)
        assert label.labeled is True
        assert len(label.boxes) == 1
        assert label.boxes[0].number == "42"

    def test_split_assigned_to_new_photos(self, workspace):
        """New photos should be assigned to the 'full' split by default."""
        _make_image(workspace["source_dir"] / "photo.jpg", b"split-test")
        hash_val = compute_content_hash(workspace["source_dir"] / "photo.jpg")

        _prepare(workspace)

        meta_store = load_photo_metadata(workspace["index_path"])
        meta = meta_store.get(hash_val)
        assert meta is not None
        assert meta.split == "full"


# =============================================================================
# --reset-labels flag
# =============================================================================


class TestResetLabels:
    """--reset-labels clears all labels but keeps photos and GT entries."""

    def test_clears_bib_labels(self, workspace):
        _make_image(workspace["source_dir"] / "photo.jpg", b"reset-content")
        hash_val = compute_content_hash(workspace["source_dir"] / "photo.jpg")

        # Pre-create labeled entry
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(BibPhotoLabel(
            content_hash=hash_val,
            boxes=[BibBox(x=0.1, y=0.2, w=0.3, h=0.4, number="42")],
            labeled=True,
        ))
        save_bib_ground_truth(bib_gt, workspace["bib_gt_path"])

        # Pre-place photo
        _make_image(workspace["photos_dir"] / "photo.jpg", b"reset-content")

        _prepare(workspace, reset_labels=True)

        bib_gt = load_bib_ground_truth(workspace["bib_gt_path"])
        label = bib_gt.get_photo(hash_val)
        assert label.labeled is False
        assert label.boxes == []

    def test_clears_face_labels(self, workspace):
        from benchmarking.ground_truth import FaceBox
        _make_image(workspace["source_dir"] / "photo.jpg", b"face-reset")
        hash_val = compute_content_hash(workspace["source_dir"] / "photo.jpg")

        face_gt = FaceGroundTruth()
        face_gt.add_photo(FacePhotoLabel(
            content_hash=hash_val,
            boxes=[FaceBox(x=0.1, y=0.2, w=0.15, h=0.2, scope="keep")],
        ))
        save_face_ground_truth(face_gt, workspace["face_gt_path"])

        _make_image(workspace["photos_dir"] / "photo.jpg", b"face-reset")

        _prepare(workspace, reset_labels=True)

        face_gt = load_face_ground_truth(workspace["face_gt_path"])
        label = face_gt.get_photo(hash_val)
        assert label.boxes == []

    def test_keeps_photos_on_disk(self, workspace):
        _make_image(workspace["photos_dir"] / "existing.jpg", b"keep-me")

        _prepare(workspace, reset_labels=True)

        assert (workspace["photos_dir"] / "existing.jpg").exists()


# =============================================================================
# PrepareResult
# =============================================================================


class TestPrepareResult:
    """PrepareResult reports what happened."""

    def test_result_fields(self, workspace):
        _make_image(workspace["source_dir"] / "a.jpg", b"aa")
        _make_image(workspace["source_dir"] / "b.jpg", b"bb")

        result = _prepare(workspace)

        assert result.copied == 2
        assert result.skipped == 0
        assert result.total_photos >= 2
        assert isinstance(result.new_hashes, set)
        assert len(result.new_hashes) == 2

    def test_idempotent_run(self, workspace):
        """Running prepare twice → second run copies nothing."""
        _make_image(workspace["source_dir"] / "photo.jpg", b"idem")

        result1 = _prepare(workspace)
        assert result1.copied == 1

        result2 = _prepare(workspace)
        assert result2.copied == 0
        assert result2.skipped == 1

"""Tests for frozen-set enforcement: guards, redirects, and viewer."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from benchmarking.frozen_check import is_frozen, require_not_frozen
from benchmarking.ground_truth import (
    BibGroundTruth,
    BibPhotoLabel,
    FaceGroundTruth,
    FacePhotoLabel,
    save_bib_ground_truth,
    save_face_ground_truth,
)
from benchmarking.photo_index import save_photo_index
from benchmarking.photo_metadata import (
    PhotoMetadata,
    PhotoMetadataStore,
    save_photo_metadata,
)
from benchmarking.sets import freeze

import benchmarking.sets as sets_module

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_UNFROZEN = "c" * 64


@pytest.fixture
def frozen_env(tmp_path, monkeypatch):
    """Set up an environment with one frozen and one unfrozen photo."""
    meta_path = tmp_path / "photo_metadata.json"
    index_path = tmp_path / "photo_index.json"
    bib_gt_path = tmp_path / "bib_ground_truth.json"
    face_gt_path = tmp_path / "face_ground_truth.json"
    link_gt_path = tmp_path / "bib_face_links.json"
    suggestions_path = tmp_path / "suggestions.json"
    identities_path = tmp_path / "face_identities.json"
    frozen_dir = tmp_path / "frozen"

    # Patch all paths
    monkeypatch.setattr(
        "benchmarking.photo_metadata.get_photo_metadata_path", lambda: meta_path
    )
    monkeypatch.setattr(
        "benchmarking.photo_index.get_photo_index_path", lambda: index_path
    )
    monkeypatch.setattr(
        "benchmarking.ground_truth.get_bib_ground_truth_path", lambda: bib_gt_path
    )
    monkeypatch.setattr(
        "benchmarking.ground_truth.get_face_ground_truth_path", lambda: face_gt_path
    )
    monkeypatch.setattr(
        "benchmarking.ground_truth.get_link_ground_truth_path", lambda: link_gt_path
    )
    monkeypatch.setattr(
        "benchmarking.ghost.get_suggestion_store_path", lambda: suggestions_path
    )
    monkeypatch.setattr(
        "benchmarking.identities.get_identities_path", lambda: identities_path
    )
    monkeypatch.setattr(sets_module, "FROZEN_DIR", frozen_dir)

    # Set up photo index
    save_photo_index(
        {HASH_A: ["photo_a.jpg"], HASH_B: ["photo_b.jpg"], HASH_UNFROZEN: ["photo_c.jpg"]},
        index_path,
    )

    # Set up ground truth (all labeled)
    bib_gt = BibGroundTruth()
    bib_gt.add_photo(BibPhotoLabel(content_hash=HASH_A, labeled=True))
    bib_gt.add_photo(BibPhotoLabel(content_hash=HASH_B, labeled=True))
    bib_gt.add_photo(BibPhotoLabel(content_hash=HASH_UNFROZEN, labeled=True))
    save_bib_ground_truth(bib_gt, bib_gt_path)

    face_gt = FaceGroundTruth()
    face_gt.add_photo(FacePhotoLabel(content_hash=HASH_A, labeled=True))
    face_gt.add_photo(FacePhotoLabel(content_hash=HASH_B, labeled=True))
    face_gt.add_photo(FacePhotoLabel(content_hash=HASH_UNFROZEN, labeled=True))
    save_face_ground_truth(face_gt, face_gt_path)

    # Set up initial metadata for all photos
    store = PhotoMetadataStore()
    store.set(HASH_A, PhotoMetadata(paths=["photo_a.jpg"]))
    store.set(HASH_B, PhotoMetadata(paths=["photo_b.jpg"]))
    store.set(HASH_UNFROZEN, PhotoMetadata(paths=["photo_c.jpg"]))
    save_photo_metadata(store, meta_path)

    # Freeze HASH_A and HASH_B into "gold-v1"
    freeze(
        name="gold-v1",
        hashes=[HASH_A, HASH_B],
        index={HASH_A: "photo_a.jpg", HASH_B: "photo_b.jpg"},
        description="First gold set",
    )

    return tmp_path


@pytest.fixture
def client(frozen_env):
    from benchmarking.app import create_app
    app = create_app()
    return TestClient(app, follow_redirects=False)


# ---------------------------------------------------------------------------
# Unit tests: is_frozen / require_not_frozen
# ---------------------------------------------------------------------------

class TestIsFrozen:
    def test_returns_none_when_not_frozen(self, frozen_env):
        assert is_frozen(HASH_UNFROZEN) is None

    def test_returns_snapshot_name(self, frozen_env):
        assert is_frozen(HASH_A) == "gold-v1"


class TestRequireNotFrozen:
    def test_raises_409_with_detail(self, frozen_env):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            require_not_frozen(HASH_A)
        assert exc_info.value.status_code == 409
        assert "gold-v1" in exc_info.value.detail

    def test_passes_for_unfrozen(self, frozen_env):
        require_not_frozen(HASH_UNFROZEN)  # no exception


# ---------------------------------------------------------------------------
# API save endpoint guards (409 for frozen photos)
# ---------------------------------------------------------------------------

class TestSaveGuards:
    def test_save_bib_boxes_rejected_for_frozen(self, client):
        resp = client.put(
            f"/api/bibs/{HASH_A}",
            json={"boxes": [], "tags": [], "split": "full"},
        )
        assert resp.status_code == 409
        assert "gold-v1" in resp.json()["detail"]

    def test_save_face_boxes_rejected_for_frozen(self, client):
        resp = client.put(
            f"/api/faces/{HASH_A}",
            json={"boxes": [], "face_tags": []},
        )
        assert resp.status_code == 409
        assert "gold-v1" in resp.json()["detail"]

    def test_save_associations_rejected_for_frozen(self, client):
        resp = client.put(
            f"/api/associations/{HASH_A}",
            json={"links": []},
        )
        assert resp.status_code == 409
        assert "gold-v1" in resp.json()["detail"]

    def test_identity_rename_allowed_on_frozen(self, client):
        # Identity rename is exempted from frozen check
        resp = client.patch(
            "/api/identities/test_name",
            json={"new_name": "test_name_2"},
        )
        # 400 because identity doesn't exist, but NOT 409 — that's the point
        assert resp.status_code != 409


# ---------------------------------------------------------------------------
# Edit view redirects for frozen photos
# ---------------------------------------------------------------------------

class TestLabelingRedirects:
    def test_bib_page_redirects_for_frozen(self, client):
        resp = client.get(f"/bibs/{HASH_A[:8]}")
        assert resp.status_code == 302
        assert "/frozen/gold-v1/" in resp.headers["location"]

    def test_face_page_redirects_for_frozen(self, client):
        resp = client.get(f"/faces/{HASH_A[:8]}")
        assert resp.status_code == 302
        assert "/frozen/gold-v1/" in resp.headers["location"]

    def test_association_page_redirects_for_frozen(self, client):
        resp = client.get(f"/associations/{HASH_A[:8]}")
        assert resp.status_code == 302
        assert "/frozen/gold-v1/" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Frozen viewer pages
# ---------------------------------------------------------------------------

class TestFrozenViewer:
    def test_frozen_sets_list_page(self, client):
        resp = client.get("/frozen/")
        assert resp.status_code == 200
        assert "gold-v1" in resp.text

    def test_frozen_set_photos_page(self, client):
        resp = client.get("/frozen/gold-v1/")
        assert resp.status_code == 200
        assert HASH_A[:8] in resp.text

    def test_frozen_photo_detail_page(self, client):
        resp = client.get(f"/frozen/gold-v1/{HASH_A[:8]}")
        assert resp.status_code == 200
        assert "Read-only" in resp.text

    def test_frozen_set_not_found(self, client):
        resp = client.get("/frozen/nonexistent/")
        assert resp.status_code == 404

    def test_frozen_photo_not_in_set(self, client):
        resp = client.get(f"/frozen/gold-v1/{HASH_UNFROZEN[:8]}")
        assert resp.status_code == 404

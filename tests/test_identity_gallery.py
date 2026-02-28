"""Tests for identity gallery service and endpoints."""

import io

import pytest
from PIL import Image

from benchmarking.ground_truth import (
    BibBox,
    BibFaceLink,
    BibGroundTruth,
    BibPhotoLabel,
    FaceBox,
    FaceGroundTruth,
    FacePhotoLabel,
    LinkGroundTruth,
    save_bib_ground_truth,
    save_face_ground_truth,
    save_link_ground_truth,
)
from benchmarking.identities import save_identities
from benchmarking.photo_index import save_photo_index
from benchmarking.services.identity_gallery_service import get_identity_gallery

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


@pytest.fixture(autouse=True)
def patch_paths(tmp_path, monkeypatch):
    """Monkeypatch all GT and index paths to tmp_path."""
    bib_gt_path = tmp_path / "bib_ground_truth.json"
    face_gt_path = tmp_path / "face_ground_truth.json"
    link_gt_path = tmp_path / "bib_face_links.json"
    index_path = tmp_path / "photo_index.json"
    suggestions_path = tmp_path / "suggestions.json"
    identities_path = tmp_path / "face_identities.json"

    save_photo_index({
        HASH_A: ["photo_a.jpg"],
        HASH_B: ["photo_b.jpg"],
        HASH_C: ["photo_c.jpg"],
    }, index_path)

    monkeypatch.setattr("benchmarking.ground_truth.get_bib_ground_truth_path", lambda: bib_gt_path)
    monkeypatch.setattr("benchmarking.ground_truth.get_face_ground_truth_path", lambda: face_gt_path)
    monkeypatch.setattr("benchmarking.ground_truth.get_link_ground_truth_path", lambda: link_gt_path)
    monkeypatch.setattr("benchmarking.photo_metadata.get_photo_metadata_path", lambda: index_path)
    monkeypatch.setattr("benchmarking.ghost.get_suggestion_store_path", lambda: suggestions_path)
    monkeypatch.setattr("benchmarking.identities.get_identities_path", lambda: identities_path)


def _make_face_box(scope="keep", identity=None, tags=None):
    return FaceBox(x=0.1, y=0.2, w=0.3, h=0.4, scope=scope, identity=identity, tags=tags or [])


def _make_bib_box(number="42"):
    return BibBox(x=0.1, y=0.5, w=0.2, h=0.1, number=number, scope="bib")


def _save_face_gt(photos: dict[str, FacePhotoLabel]):
    gt = FaceGroundTruth()
    for h, label in photos.items():
        gt.add_photo(label)
    save_face_ground_truth(gt)


def _save_bib_gt(photos: dict[str, BibPhotoLabel]):
    gt = BibGroundTruth()
    for h, label in photos.items():
        gt.add_photo(label)
    save_bib_ground_truth(gt)


def _save_link_gt(photos: dict[str, list[BibFaceLink]]):
    gt = LinkGroundTruth()
    for h, links in photos.items():
        gt.set_links(h, links)
    save_link_ground_truth(gt)


# ---- Service tests --------------------------------------------------------


class TestGetIdentityGallery:
    def test_groups_by_identity(self):
        """Faces with different identities end up in different groups."""
        _save_face_gt({
            HASH_A: FacePhotoLabel(content_hash=HASH_A, boxes=[
                _make_face_box(identity="Iva"),
                _make_face_box(identity="Jens"),
            ], labeled=True),
            HASH_B: FacePhotoLabel(content_hash=HASH_B, boxes=[
                _make_face_box(identity="Iva"),
            ], labeled=True),
        })

        groups = get_identity_gallery()
        names = [g.name for g in groups]
        assert "Iva" in names
        assert "Jens" in names

        iva = next(g for g in groups if g.name == "Iva")
        assert len(iva.faces) == 2

        jens = next(g for g in groups if g.name == "Jens")
        assert len(jens.faces) == 1

    def test_excludes_non_keep_scope(self):
        """Only keep-scoped boxes appear in the gallery."""
        _save_face_gt({
            HASH_A: FacePhotoLabel(content_hash=HASH_A, boxes=[
                _make_face_box(scope="keep", identity="Iva"),
                _make_face_box(scope="exclude", identity="Iva"),
                _make_face_box(scope="uncertain", identity="Iva"),
            ], labeled=True),
        })

        groups = get_identity_gallery()
        assert len(groups) == 1
        assert len(groups[0].faces) == 1

    def test_excludes_boxes_without_coords(self):
        """Legacy boxes without coordinates are excluded."""
        _save_face_gt({
            HASH_A: FacePhotoLabel(content_hash=HASH_A, boxes=[
                FaceBox(x=0, y=0, w=0, h=0, scope="keep", identity="Iva"),
                _make_face_box(identity="Iva"),
            ], labeled=True),
        })

        groups = get_identity_gallery()
        assert len(groups) == 1
        assert len(groups[0].faces) == 1

    def test_null_identity_grouped_as_unassigned(self):
        """Faces with identity=None go to 'Unassigned' group, sorted last."""
        _save_face_gt({
            HASH_A: FacePhotoLabel(content_hash=HASH_A, boxes=[
                _make_face_box(identity=None),
                _make_face_box(identity="Iva"),
            ], labeled=True),
        })

        groups = get_identity_gallery()
        assert groups[-1].name == "Unassigned"
        assert len(groups[-1].faces) == 1

    def test_sort_order(self):
        """Errors first, then alphabetical, Unassigned last."""
        _save_face_gt({
            HASH_A: FacePhotoLabel(content_hash=HASH_A, boxes=[
                _make_face_box(identity="Zara"),
                _make_face_box(identity="anon-2"),
                _make_face_box(identity=None),
                _make_face_box(identity="Abel"),
                _make_face_box(identity="anon-1"),
            ], labeled=True),
        })

        groups = get_identity_gallery()
        names = [g.name for g in groups]
        assert names == ["Abel", "anon-1", "anon-2", "Zara", "Unassigned"]

    def test_multi_bib_identities_sort_first(self):
        """Identities with multiple bib numbers sort before clean ones."""
        _save_face_gt({
            HASH_A: FacePhotoLabel(content_hash=HASH_A, boxes=[
                _make_face_box(identity="Zara"),
                _make_face_box(identity="Abel"),
            ], labeled=True),
            HASH_B: FacePhotoLabel(content_hash=HASH_B, boxes=[
                _make_face_box(identity="Zara"),
            ], labeled=True),
        })
        _save_bib_gt({
            HASH_A: BibPhotoLabel(content_hash=HASH_A, boxes=[
                _make_bib_box(number="10"),
                _make_bib_box(number="99"),
            ], labeled=True),
            HASH_B: BibPhotoLabel(content_hash=HASH_B, boxes=[
                _make_bib_box(number="20"),
            ], labeled=True),
        })
        # Zara linked to bib 10 in photo A and bib 20 in photo B → multi-bib
        # Abel linked to bib 99 in photo A → single bib
        _save_link_gt({
            HASH_A: [
                BibFaceLink(bib_index=0, face_index=0),  # Zara ↔ 10
                BibFaceLink(bib_index=1, face_index=1),  # Abel ↔ 99
            ],
            HASH_B: [
                BibFaceLink(bib_index=0, face_index=0),  # Zara ↔ 20
            ],
        })

        groups = get_identity_gallery()
        names = [g.name for g in groups]
        # Zara has multi-bib error → first; Abel is clean → second
        assert names == ["Zara", "Abel"]

    def test_resolves_bib_link(self):
        """Linked face shows bib number and bib box index."""
        _save_face_gt({
            HASH_A: FacePhotoLabel(content_hash=HASH_A, boxes=[
                _make_face_box(identity="Iva"),
            ], labeled=True),
        })
        _save_bib_gt({
            HASH_A: BibPhotoLabel(content_hash=HASH_A, boxes=[
                _make_bib_box(number="42"),
            ], labeled=True),
        })
        _save_link_gt({
            HASH_A: [BibFaceLink(bib_index=0, face_index=0)],
        })

        groups = get_identity_gallery()
        face = groups[0].faces[0]
        assert face.bib_number == "42"
        assert face.bib_box_index == 0

    def test_no_bib_link(self):
        """Unlinked face has None for bib fields."""
        _save_face_gt({
            HASH_A: FacePhotoLabel(content_hash=HASH_A, boxes=[
                _make_face_box(identity="Iva"),
            ], labeled=True),
        })

        groups = get_identity_gallery()
        face = groups[0].faces[0]
        assert face.bib_number is None
        assert face.bib_box_index is None

    def test_empty_ground_truth(self):
        """No face data → empty gallery."""
        groups = get_identity_gallery()
        assert groups == []


# ---- Endpoint tests -------------------------------------------------------


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Create a test client with the app."""
    from benchmarking.app import create_app
    from starlette.testclient import TestClient
    return TestClient(create_app(), follow_redirects=False)


class TestIdentityGalleryEndpoint:
    def test_gallery_page_renders(self, app_client):
        """GET /identities/ returns 200."""
        resp = app_client.get("/identities/")
        assert resp.status_code == 200
        assert "Identity Gallery" in resp.text

    def test_gallery_shows_identity_names(self, app_client):
        """Gallery page includes identity names from face GT."""
        _save_face_gt({
            HASH_A: FacePhotoLabel(content_hash=HASH_A, boxes=[
                _make_face_box(identity="Iva"),
                _make_face_box(identity="Jens"),
            ], labeled=True),
        })

        resp = app_client.get("/identities/")
        assert resp.status_code == 200
        assert "Iva" in resp.text
        assert "Jens" in resp.text


class TestIdentityRenameFromGallery:
    def test_rename_identity_via_patch(self, app_client):
        """PATCH /api/identities/{name} renames identity across GT."""
        save_identities(["OldName", "Other"])
        _save_face_gt({
            HASH_A: FacePhotoLabel(content_hash=HASH_A, boxes=[
                _make_face_box(identity="OldName"),
                _make_face_box(identity="OldName"),
                _make_face_box(identity="Other"),
            ], labeled=True),
        })

        resp = app_client.patch(
            "/api/identities/OldName",
            json={"new_name": "NewName"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated_count"] == 2
        assert "NewName" in data["identities"]
        assert "OldName" not in data["identities"]

        # Verify gallery now shows the new name
        groups = get_identity_gallery()
        names = [g.name for g in groups]
        assert "NewName" in names
        assert "OldName" not in names

    def test_rename_same_name_returns_400(self, app_client):
        """PATCH with same name returns 400."""
        _save_face_gt({
            HASH_A: FacePhotoLabel(content_hash=HASH_A, boxes=[
                _make_face_box(identity="Iva"),
            ], labeled=True),
        })

        resp = app_client.patch(
            "/api/identities/Iva",
            json={"new_name": "Iva"},
        )
        assert resp.status_code == 400

    def test_rename_empty_name_returns_400(self, app_client):
        """PATCH with empty new_name returns 400."""
        resp = app_client.patch(
            "/api/identities/Iva",
            json={"new_name": "  "},
        )
        assert resp.status_code == 400


class TestBibCropEndpoint:
    def test_bib_crop_returns_jpeg(self, app_client, tmp_path, monkeypatch):
        """GET /api/bibs/{hash}/crop/{index} returns JPEG image."""
        # Create a test photo
        photos_dir = tmp_path / "photos"
        photos_dir.mkdir()
        img = Image.new("RGB", (100, 100), color="red")
        photo_path = photos_dir / "photo_a.jpg"
        img.save(photo_path)

        monkeypatch.setattr("benchmarking.services.bib_service.PHOTOS_DIR", photos_dir)

        _save_bib_gt({
            HASH_A: BibPhotoLabel(content_hash=HASH_A, boxes=[
                _make_bib_box(number="42"),
            ], labeled=True),
        })

        resp = app_client.get(f"/api/bibs/{HASH_A[:8]}/crop/0")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"
        # Verify it's a valid JPEG
        img = Image.open(io.BytesIO(resp.content))
        assert img.format == "JPEG"

    def test_bib_crop_not_found(self, app_client):
        """GET /api/bibs/{unknown}/crop/0 returns 404."""
        resp = app_client.get(f"/api/bibs/{HASH_A[:8]}/crop/0")
        assert resp.status_code == 404

    def test_bib_crop_invalid_index(self, app_client):
        """GET /api/bibs/{hash}/crop/{bad_index} returns 404."""
        _save_bib_gt({
            HASH_A: BibPhotoLabel(content_hash=HASH_A, boxes=[
                _make_bib_box(),
            ], labeled=True),
        })
        resp = app_client.get(f"/api/bibs/{HASH_A[:8]}/crop/5")
        assert resp.status_code == 404

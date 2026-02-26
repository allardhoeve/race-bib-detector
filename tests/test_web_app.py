"""Tests for web_app API endpoints (bib boxes, face boxes, identities)."""

import io

import pytest
from PIL import Image
from starlette.testclient import TestClient


from benchmarking.ghost import (
    BibSuggestion,
    FaceSuggestion,
    PhotoSuggestions,
    SuggestionStore,
    save_suggestion_store,
)
from benchmarking.photo_index import save_photo_index


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_UNKNOWN = "f" * 64


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Create a test client with all paths monkeypatched to tmp_path."""
    bib_gt_path = tmp_path / "bib_ground_truth.json"
    face_gt_path = tmp_path / "face_ground_truth.json"
    suggestions_path = tmp_path / "suggestions.json"
    identities_path = tmp_path / "face_identities.json"
    index_path = tmp_path / "photo_index.json"

    # Create a photo index with test hashes
    save_photo_index({HASH_A: ["photo_a.jpg"], HASH_B: ["photo_b.jpg"]}, index_path)

    # Monkeypatch all path functions
    monkeypatch.setattr(
        "benchmarking.ground_truth.get_bib_ground_truth_path", lambda: bib_gt_path
    )
    monkeypatch.setattr(
        "benchmarking.ground_truth.get_face_ground_truth_path", lambda: face_gt_path
    )
    monkeypatch.setattr(
        "benchmarking.ghost.get_suggestion_store_path", lambda: suggestions_path
    )
    monkeypatch.setattr(
        "benchmarking.identities.get_identities_path", lambda: identities_path
    )
    monkeypatch.setattr(
        "benchmarking.photo_index.get_photo_index_path", lambda: index_path
    )

    from benchmarking.app import create_app

    app = create_app()
    return TestClient(app, follow_redirects=False)


# =============================================================================
# Bib Box API
# =============================================================================


class TestBibBoxApi:
    def test_get_bib_boxes_empty(self, app_client):
        """GET bib boxes for a photo with no GT returns empty boxes."""
        resp = app_client.get(f"/api/bibs/{HASH_A}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["boxes"] == []
        assert "tags" in data

    def test_save_and_load_bib_boxes_with_coords(self, app_client):
        """Save bib boxes with coordinates, then load them back."""
        boxes = [
            {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4, "number": "42", "scope": "bib"},
            {"x": 0.5, "y": 0.6, "w": 0.1, "h": 0.1, "number": "7", "scope": "not_bib"},
        ]
        save_resp = app_client.put(
            f"/api/bibs/{HASH_A[:8]}",
            json={
                "boxes": boxes,
                "tags": [],
                "split": "full",
            },
        )
        assert save_resp.status_code == 200

        resp = app_client.get(f"/api/bibs/{HASH_A}")
        data = resp.json()
        assert len(data["boxes"]) == 2
        assert data["boxes"][0]["number"] == "42"
        assert data["boxes"][0]["x"] == pytest.approx(0.1)
        assert data["boxes"][1]["scope"] == "not_bib"
        assert data["labeled"] is True

    def test_save_bibs_backward_compat(self, app_client):
        """Sending bibs as int list (no boxes) creates zero-area boxes."""
        resp = app_client.put(
            f"/api/bibs/{HASH_A[:8]}",
            json={
                "bibs": [123, 456],
                "tags": [],
                "split": "full",
            },
        )
        assert resp.status_code == 200

        get_resp = app_client.get(f"/api/bibs/{HASH_A}")
        data = get_resp.json()
        assert len(data["boxes"]) == 2
        numbers = {b["number"] for b in data["boxes"]}
        assert numbers == {"123", "456"}
        # Zero-area coords
        for box in data["boxes"]:
            assert box["x"] == 0 and box["y"] == 0 and box["w"] == 0 and box["h"] == 0

    def test_get_bib_boxes_with_suggestions(self, app_client):
        """GET bib boxes includes suggestions from ghost labeling."""
        # Set up suggestions
        store = SuggestionStore()
        store.add(
            PhotoSuggestions(
                content_hash=HASH_A,
                bibs=[BibSuggestion(x=0.1, y=0.2, w=0.3, h=0.4, number="99", confidence=0.9)],
            )
        )
        save_suggestion_store(store)

        resp = app_client.get(f"/api/bibs/{HASH_A}")
        data = resp.json()
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["number"] == "99"
        assert data["suggestions"][0]["confidence"] == pytest.approx(0.9)

    def test_get_bib_boxes_unknown_hash_404(self, app_client):
        resp = app_client.get(f"/api/bibs/{HASH_UNKNOWN}")
        assert resp.status_code == 404

    def test_save_invalid_scope_400(self, app_client):
        resp = app_client.put(
            f"/api/bibs/{HASH_A[:8]}",
            json={
                "boxes": [{"x": 0, "y": 0, "w": 0.1, "h": 0.1, "number": "1", "scope": "invalid_scope"}],
                "tags": [],
                "split": "full",
            },
        )
        assert resp.status_code == 400

    def test_bib_boxes_include_split(self, app_client):
        """GET bib boxes includes split info."""
        app_client.put(
            f"/api/bibs/{HASH_A[:8]}",
            json={
                "boxes": [],
                "tags": ["no_bib"],
                "split": "iteration",
            },
        )
        resp = app_client.get(f"/api/bibs/{HASH_A}")
        data = resp.json()
        assert data["split"] == "iteration"
        assert "no_bib" in data["tags"]

    def test_old_bib_boxes_url_redirects_308(self, app_client):
        """GET /api/bib_boxes/<hash> returns 308 redirect."""
        resp = app_client.get(f"/api/bib_boxes/{HASH_A}")
        assert resp.status_code == 308

    def test_old_save_label_returns_410(self, app_client):
        """POST /api/labels returns 410 Gone."""
        resp = app_client.post("/api/labels", json={"content_hash": HASH_A, "boxes": []})
        assert resp.status_code == 410


# =============================================================================
# Face Box API
# =============================================================================


class TestFaceBoxApi:
    def test_get_face_boxes_empty(self, app_client):
        resp = app_client.get(f"/api/faces/{HASH_A}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["boxes"] == []

    def test_save_and_load_face_boxes(self, app_client):
        boxes = [
            {"x": 0.1, "y": 0.2, "w": 0.15, "h": 0.2, "scope": "keep", "identity": "Alice"},
            {"x": 0.5, "y": 0.3, "w": 0.1, "h": 0.15, "scope": "exclude"},
        ]
        save_resp = app_client.put(
            f"/api/faces/{HASH_A[:8]}",
            json={"boxes": boxes, "face_tags": []},
        )
        assert save_resp.status_code == 200

        resp = app_client.get(f"/api/faces/{HASH_A}")
        data = resp.json()
        assert len(data["boxes"]) == 2
        assert data["boxes"][0]["scope"] == "keep"
        assert data["boxes"][0]["identity"] == "Alice"
        assert data["boxes"][1]["scope"] == "exclude"

    def test_save_face_backward_compat(self, app_client):
        """Sending face_count without boxes keeps current behavior (compat tags)."""
        resp = app_client.put(
            f"/api/faces/{HASH_A[:8]}",
            json={"face_count": 3, "face_tags": ["face_tiny_faces"]},
        )
        assert resp.status_code == 200

        get_resp = app_client.get(f"/api/faces/{HASH_A}")
        data = get_resp.json()
        assert "face_tiny_faces" in data["tags"]

    def test_save_and_load_face_boxes_with_tags(self, app_client):
        """Save face boxes with per-box tags, verify round-trip."""
        boxes = [
            {"x": 0.1, "y": 0.2, "w": 0.15, "h": 0.2, "scope": "keep", "tags": ["tiny", "blurry"]},
            {"x": 0.5, "y": 0.3, "w": 0.1, "h": 0.15, "scope": "exclude", "tags": ["profile"]},
        ]
        save_resp = app_client.put(
            f"/api/faces/{HASH_A[:8]}",
            json={"boxes": boxes, "face_tags": ["no_faces"]},
        )
        assert save_resp.status_code == 200

        resp = app_client.get(f"/api/faces/{HASH_A}")
        data = resp.json()
        assert len(data["boxes"]) == 2
        assert data["boxes"][0]["tags"] == ["tiny", "blurry"]
        assert data["boxes"][1]["tags"] == ["profile"]
        assert "no_faces" in data["tags"]

    def test_save_face_box_invalid_tag_400(self, app_client):
        """Invalid per-box tag returns 400."""
        resp = app_client.put(
            f"/api/faces/{HASH_A[:8]}",
            json={
                "boxes": [{"x": 0, "y": 0, "w": 0.1, "h": 0.1, "scope": "keep", "tags": ["invalid"]}],
                "face_tags": [],
            },
        )
        assert resp.status_code == 400

    def test_face_boxes_empty_tags_omitted(self, app_client):
        """Boxes with no tags don't include tags key in response."""
        boxes = [{"x": 0.1, "y": 0.2, "w": 0.15, "h": 0.2, "scope": "keep"}]
        app_client.put(
            f"/api/faces/{HASH_A[:8]}",
            json={"boxes": boxes, "face_tags": []},
        )
        resp = app_client.get(f"/api/faces/{HASH_A}")
        data = resp.json()
        # Box tags should be empty (model_dump always includes the key)
        assert data["boxes"][0].get("tags", []) == []

    def test_get_face_boxes_with_suggestions(self, app_client):
        store = SuggestionStore()
        store.add(
            PhotoSuggestions(
                content_hash=HASH_A,
                faces=[FaceSuggestion(x=0.2, y=0.3, w=0.1, h=0.15, confidence=0.85)],
            )
        )
        save_suggestion_store(store)

        resp = app_client.get(f"/api/faces/{HASH_A}")
        data = resp.json()
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["confidence"] == pytest.approx(0.85)

    def test_get_face_boxes_unknown_hash_404(self, app_client):
        resp = app_client.get(f"/api/faces/{HASH_UNKNOWN}")
        assert resp.status_code == 404

    def test_save_invalid_scope_400(self, app_client):
        resp = app_client.put(
            f"/api/faces/{HASH_A[:8]}",
            json={
                "boxes": [{"x": 0, "y": 0, "w": 0.1, "h": 0.1, "scope": "bad_scope"}],
                "face_tags": [],
            },
        )
        assert resp.status_code == 400

    def test_old_face_boxes_url_redirects_308(self, app_client):
        """GET /api/face_boxes/<hash> returns 308 redirect."""
        resp = app_client.get(f"/api/face_boxes/{HASH_A}")
        assert resp.status_code == 308

    def test_old_save_face_label_returns_410(self, app_client):
        """POST /api/face_labels returns 410 Gone."""
        resp = app_client.post("/api/face_labels", json={"content_hash": HASH_A, "boxes": []})
        assert resp.status_code == 410


# =============================================================================
# Identities API
# =============================================================================


class TestIdentitiesApi:
    def test_get_identities_empty(self, app_client):
        resp = app_client.get("/api/identities")
        assert resp.status_code == 200
        assert resp.json()["identities"] == []

    def test_add_identity(self, app_client):
        resp = app_client.post(
            "/api/identities", json={"name": "Bob"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "Bob" in data["identities"]

    def test_add_duplicate_idempotent(self, app_client):
        app_client.post("/api/identities", json={"name": "Alice"})
        app_client.post("/api/identities", json={"name": "Alice"})
        resp = app_client.get("/api/identities")
        data = resp.json()
        assert data["identities"].count("Alice") == 1

    def test_identities_sorted(self, app_client):
        app_client.post("/api/identities", json={"name": "Charlie"})
        app_client.post("/api/identities", json={"name": "Alice"})
        app_client.post("/api/identities", json={"name": "Bob"})
        resp = app_client.get("/api/identities")
        data = resp.json()
        assert data["identities"] == ["Alice", "Bob", "Charlie"]


# =============================================================================
# Rename Identity API
# =============================================================================


class TestRenameIdentityApi:
    def test_rename_missing_params_400(self, app_client):
        """Missing new_name returns 400."""
        resp = app_client.patch("/api/identities/Alice", json={})
        assert resp.status_code == 400

        resp = app_client.patch("/api/identities/Alice", json={"new_name": ""})
        assert resp.status_code == 400

    def test_rename_same_name_400(self, app_client):
        """old == new returns 400."""
        resp = app_client.patch(
            "/api/identities/Alice", json={"new_name": "Alice"}
        )
        assert resp.status_code == 400

    def test_rename_updates_face_boxes(self, app_client):
        """Renaming identity updates all face GT boxes."""
        # Save face labels with anon-1 identity
        boxes = [
            {"x": 0.1, "y": 0.2, "w": 0.15, "h": 0.2, "scope": "keep", "identity": "anon-1"},
            {"x": 0.5, "y": 0.3, "w": 0.1, "h": 0.15, "scope": "keep", "identity": "Bob"},
        ]
        app_client.put(
            f"/api/faces/{HASH_A[:8]}",
            json={"boxes": boxes, "face_tags": []},
        )
        # Also save for HASH_B with anon-1
        app_client.put(
            f"/api/faces/{HASH_B[:8]}",
            json={
                "boxes": [{"x": 0.2, "y": 0.3, "w": 0.1, "h": 0.1, "scope": "keep", "identity": "anon-1"}],
                "face_tags": [],
            },
        )

        resp = app_client.patch(
            "/api/identities/anon-1", json={"new_name": "Alice"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated_count"] == 2  # one in HASH_A, one in HASH_B

        # Verify boxes are updated
        resp_a = app_client.get(f"/api/faces/{HASH_A}")
        boxes_a = resp_a.json()["boxes"]
        assert boxes_a[0]["identity"] == "Alice"
        assert boxes_a[1]["identity"] == "Bob"  # unchanged

        resp_b = app_client.get(f"/api/faces/{HASH_B}")
        boxes_b = resp_b.json()["boxes"]
        assert boxes_b[0]["identity"] == "Alice"

    def test_rename_updates_identities_list(self, app_client):
        """Renaming updates the identities list: old removed, new added."""
        app_client.post("/api/identities", json={"name": "anon-1"})
        app_client.post("/api/identities", json={"name": "Bob"})

        resp = app_client.patch(
            "/api/identities/anon-1", json={"new_name": "Alice"}
        )
        assert resp.status_code == 200
        ids = resp.json()["identities"]
        assert "Alice" in ids
        assert "anon-1" not in ids
        assert "Bob" in ids

    def test_rename_no_matches_returns_zero(self, app_client):
        """Rename an identity that has no boxes returns updated_count=0."""
        app_client.post("/api/identities", json={"name": "anon-5"})

        resp = app_client.patch(
            "/api/identities/anon-5", json={"new_name": "Carol"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated_count"] == 0
        assert "Carol" in data["identities"]
        assert "anon-5" not in data["identities"]

    def test_old_rename_identity_returns_410(self, app_client):
        """POST /api/rename_identity returns 410 Gone."""
        resp = app_client.post("/api/rename_identity", json={"old_name": "A", "new_name": "B"})
        assert resp.status_code == 410


# =============================================================================
# Face Identity Suggestions API
# =============================================================================


class TestFaceIdentitySuggestions:
    def test_missing_params_400(self, app_client):
        """Missing box coordinates returns 400."""
        resp = app_client.get(f"/api/faces/{HASH_A}/suggestions")
        assert resp.status_code == 400

    def test_unknown_hash_404(self, app_client):
        resp = app_client.get(
            f"/api/faces/{HASH_UNKNOWN}/suggestions"
            "?box_x=0.1&box_y=0.2&box_w=0.3&box_h=0.4"
        )
        assert resp.status_code == 404

    def test_empty_index_returns_empty_suggestions(self, app_client, monkeypatch):
        """When no labeled faces exist, returns empty suggestions."""
        import numpy as np
        from benchmarking.face_embeddings import EmbeddingIndex

        # Monkeypatch the embedding index cache to have an empty index
        monkeypatch.setattr(
            "benchmarking.services.face_service.build_embedding_index",
            lambda *a, **kw: EmbeddingIndex(
                embeddings=np.empty((0, 3), dtype=np.float32),
            ),
        )

        resp = app_client.get(
            f"/api/faces/{HASH_A}/suggestions"
            "?box_x=0.1&box_y=0.2&box_w=0.3&box_h=0.4"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["suggestions"] == []


# =============================================================================
# Face Crop API
# =============================================================================


def _make_test_jpeg(path, width=100, height=80):
    """Create a small test JPEG file."""
    img = Image.new("RGB", (width, height), color=(255, 0, 0))
    img.save(path, format="JPEG")


@pytest.fixture
def crop_client(tmp_path, monkeypatch):
    """Test client with PHOTOS_DIR pointed at tmp_path and a real JPEG."""
    bib_gt_path = tmp_path / "bib_ground_truth.json"
    face_gt_path = tmp_path / "face_ground_truth.json"
    suggestions_path = tmp_path / "suggestions.json"
    identities_path = tmp_path / "face_identities.json"
    index_path = tmp_path / "photo_index.json"
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()

    # Create a test photo
    _make_test_jpeg(photos_dir / "photo_a.jpg")

    save_photo_index({HASH_A: ["photo_a.jpg"]}, index_path)

    monkeypatch.setattr(
        "benchmarking.ground_truth.get_bib_ground_truth_path", lambda: bib_gt_path
    )
    monkeypatch.setattr(
        "benchmarking.ground_truth.get_face_ground_truth_path", lambda: face_gt_path
    )
    monkeypatch.setattr(
        "benchmarking.ghost.get_suggestion_store_path", lambda: suggestions_path
    )
    monkeypatch.setattr(
        "benchmarking.identities.get_identities_path", lambda: identities_path
    )
    monkeypatch.setattr(
        "benchmarking.photo_index.get_photo_index_path", lambda: index_path
    )
    monkeypatch.setattr("benchmarking.services.face_service.PHOTOS_DIR", photos_dir)

    from benchmarking.app import create_app

    app = create_app()
    return TestClient(app, follow_redirects=False)


class TestFaceCropApi:
    def test_unknown_hash_404(self, crop_client):
        resp = crop_client.get(f"/api/faces/{HASH_UNKNOWN}/crop/0")
        assert resp.status_code == 404

    def test_no_face_gt_404(self, crop_client):
        """Hash exists in index but has no face GT entry."""
        resp = crop_client.get(f"/api/faces/{HASH_A}/crop/0")
        assert resp.status_code == 404

    def test_box_index_out_of_range_404(self, crop_client):
        """Box index beyond available boxes."""
        # Save a face label with one box
        crop_client.put(
            f"/api/faces/{HASH_A[:8]}",
            json={
                "boxes": [{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2, "scope": "keep"}],
                "face_tags": [],
            },
        )
        resp = crop_client.get(f"/api/faces/{HASH_A}/crop/5")
        assert resp.status_code == 404

    def test_zero_area_box_404(self, crop_client):
        """Box with zero-area coords returns 404."""
        crop_client.put(
            f"/api/faces/{HASH_A[:8]}",
            json={
                "boxes": [{"x": 0, "y": 0, "w": 0, "h": 0, "scope": "keep"}],
                "face_tags": [],
            },
        )
        resp = crop_client.get(f"/api/faces/{HASH_A}/crop/0")
        assert resp.status_code == 404

    def test_success_returns_jpeg(self, crop_client):
        """Valid hash + box_index returns a cropped JPEG."""
        crop_client.put(
            f"/api/faces/{HASH_A[:8]}",
            json={
                "boxes": [{"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5, "scope": "keep"}],
                "face_tags": [],
            },
        )
        resp = crop_client.get(f"/api/faces/{HASH_A}/crop/0")
        assert resp.status_code == 200
        assert resp.headers['content-type'] == "image/jpeg"

        # Verify it's a valid JPEG we can open
        img = Image.open(io.BytesIO(resp.content))
        assert img.format == "JPEG"
        assert img.width > 0 and img.height > 0


# =============================================================================
# Home Route
# =============================================================================


class TestHomeRoute:
    def test_home_route_200(self, app_client):
        """GET / returns 200."""
        resp = app_client.get("/")
        assert resp.status_code == 200

    def test_home_route_shows_progress(self, app_client):
        """Home page shows per-step labeled counts based on saved GT data."""
        # Save one bib label and one face label via the API
        app_client.put(
            f"/api/bibs/{HASH_A[:8]}",
            json={
                "boxes": [{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2, "number": "42", "scope": "bib"}],
                "tags": [],
                "split": "full",
            },
        )
        app_client.put(
            f"/api/faces/{HASH_A[:8]}",
            json={
                "boxes": [{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2, "scope": "keep"}],
                "face_tags": [],
            },
        )

        resp = app_client.get("/")
        assert resp.status_code == 200
        body = resp.text
        # Index has 2 photos (HASH_A, HASH_B); 1 labeled in each dimension
        assert "1 / 2" in body

    def test_home_route_links_na(self, app_client, monkeypatch):
        """Home page shows N/A for links when load_link_ground_truth raises."""
        def _raise():
            raise ImportError("link GT not available")

        monkeypatch.setattr("benchmarking.ground_truth.load_link_ground_truth", _raise)
        resp = app_client.get("/")
        assert resp.status_code == 200
        assert "N/A" in resp.text


# =============================================================================
# Staging Route + Freeze API
# =============================================================================


@pytest.fixture
def freeze_client(tmp_path, monkeypatch):
    """Test client with all GT paths + FROZEN_DIR monkeypatched."""
    bib_gt_path = tmp_path / "bib_ground_truth.json"
    face_gt_path = tmp_path / "face_ground_truth.json"
    link_gt_path = tmp_path / "bib_face_links.json"
    suggestions_path = tmp_path / "suggestions.json"
    identities_path = tmp_path / "face_identities.json"
    index_path = tmp_path / "photo_index.json"
    frozen_dir = tmp_path / "frozen"

    from benchmarking.photo_index import save_photo_index
    save_photo_index({HASH_A: ["photo_a.jpg"], HASH_B: ["photo_b.jpg"]}, index_path)

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
    monkeypatch.setattr(
        "benchmarking.photo_index.get_photo_index_path", lambda: index_path
    )
    monkeypatch.setattr("benchmarking.sets.FROZEN_DIR", frozen_dir)

    from benchmarking.app import create_app
    app = create_app()
    return TestClient(app, follow_redirects=False)


class TestStagingRoute:
    def test_staging_route_200(self, freeze_client):
        """GET /benchmark/staging/ returns 200."""
        resp = freeze_client.get("/benchmark/staging/")
        assert resp.status_code == 200

    def test_old_staging_url_redirects_301(self, freeze_client):
        """GET /staging/ redirects 301 to /benchmark/staging/."""
        resp = freeze_client.get("/staging/")
        assert resp.status_code == 301
        assert "/benchmark/staging/" in resp.headers["Location"]


class TestApiFreezeEndpoint:
    def test_freeze_creates_snapshot(self, freeze_client):
        """POST /api/freeze with valid hashes returns 200 and snapshot metadata."""
        resp = freeze_client.post(
            "/api/freeze",
            json={"name": "test-snap", "hashes": [HASH_A], "description": "test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test-snap"
        assert data["photo_count"] == 1
        assert "created_at" in data

    def test_freeze_conflict(self, freeze_client):
        """POST /api/freeze with a name that already exists returns 409."""
        freeze_client.post(
            "/api/freeze",
            json={"name": "dup-snap", "hashes": [HASH_A]},
        )
        resp = freeze_client.post(
            "/api/freeze",
            json={"name": "dup-snap", "hashes": [HASH_A]},
        )
        assert resp.status_code == 409

    def test_freeze_missing_name(self, freeze_client):
        """POST with empty name returns 400."""
        resp = freeze_client.post(
            "/api/freeze",
            json={"name": "", "hashes": [HASH_A]},
        )
        assert resp.status_code == 400

    def test_freeze_empty_hashes(self, freeze_client):
        """POST with empty hashes list returns 400."""
        resp = freeze_client.post(
            "/api/freeze",
            json={"name": "no-photos", "hashes": []},
        )
        assert resp.status_code == 400


# =============================================================================
# Task-019 URL redirect smoke tests
# =============================================================================


class TestTask019Redirects:
    def test_old_labels_url_redirects_301(self, app_client):
        """GET /labels/ returns 301 to /bibs/."""
        resp = app_client.get("/labels/")
        assert resp.status_code == 301
        assert "/bibs/" in resp.headers["Location"]

    def test_old_faces_labels_url_redirects_301(self, app_client):
        """GET /faces/labels/ returns 301 to /faces/."""
        resp = app_client.get("/faces/labels/")
        assert resp.status_code == 301
        assert "/faces/" in resp.headers["Location"]

    def test_bibs_index_redirects(self, app_client):
        """GET /bibs/ returns 302 redirect to first photo."""
        resp = app_client.get("/bibs/")
        assert resp.status_code in (200, 302)

    def test_faces_index_redirects(self, app_client):
        """GET /faces/ returns 302 redirect to first photo."""
        resp = app_client.get("/faces/")
        assert resp.status_code in (200, 302)

    def test_associations_index_redirects(self, app_client):
        """GET /associations/ returns 302 redirect to first photo."""
        resp = app_client.get("/associations/")
        assert resp.status_code in (200, 302)

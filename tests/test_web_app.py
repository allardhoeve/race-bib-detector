"""Tests for web_app API endpoints (bib boxes, face boxes, identities)."""

import json
import pytest
from pathlib import Path

from benchmarking.ground_truth import (
    BibBox,
    BibPhotoLabel,
    BibGroundTruth,
    FaceBox,
    FacePhotoLabel,
    FaceGroundTruth,
    save_bib_ground_truth,
    save_face_ground_truth,
)
from benchmarking.ghost import (
    BibSuggestion,
    FaceSuggestion,
    PhotoSuggestions,
    SuggestionStore,
    save_suggestion_store,
)
from benchmarking.identities import save_identities
from benchmarking.photo_index import save_photo_index


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_UNKNOWN = "f" * 64


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Create a Flask test client with all paths monkeypatched to tmp_path."""
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

    from benchmarking.web_app import create_app

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    return client


# =============================================================================
# Bib Box API
# =============================================================================


class TestBibBoxApi:
    def test_get_bib_boxes_empty(self, app_client):
        """GET bib boxes for a photo with no GT returns empty boxes."""
        resp = app_client.get(f"/api/bib_boxes/{HASH_A}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["boxes"] == []
        assert "tags" in data

    def test_save_and_load_bib_boxes_with_coords(self, app_client):
        """Save bib boxes with coordinates, then load them back."""
        boxes = [
            {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4, "number": "42", "tag": "bib"},
            {"x": 0.5, "y": 0.6, "w": 0.1, "h": 0.1, "number": "7", "tag": "not_bib"},
        ]
        save_resp = app_client.post(
            "/api/labels",
            json={
                "content_hash": HASH_A,
                "boxes": boxes,
                "tags": [],
                "split": "full",
            },
        )
        assert save_resp.status_code == 200

        resp = app_client.get(f"/api/bib_boxes/{HASH_A}")
        data = resp.get_json()
        assert len(data["boxes"]) == 2
        assert data["boxes"][0]["number"] == "42"
        assert data["boxes"][0]["x"] == pytest.approx(0.1)
        assert data["boxes"][1]["tag"] == "not_bib"
        assert data["labeled"] is True

    def test_save_bibs_backward_compat(self, app_client):
        """Sending bibs as int list (no boxes) creates zero-area boxes."""
        resp = app_client.post(
            "/api/labels",
            json={
                "content_hash": HASH_A,
                "bibs": [123, 456],
                "tags": [],
                "split": "full",
            },
        )
        assert resp.status_code == 200

        get_resp = app_client.get(f"/api/bib_boxes/{HASH_A}")
        data = get_resp.get_json()
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

        resp = app_client.get(f"/api/bib_boxes/{HASH_A}")
        data = resp.get_json()
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["number"] == "99"
        assert data["suggestions"][0]["confidence"] == pytest.approx(0.9)

    def test_get_bib_boxes_unknown_hash_404(self, app_client):
        resp = app_client.get(f"/api/bib_boxes/{HASH_UNKNOWN}")
        assert resp.status_code == 404

    def test_save_invalid_tag_400(self, app_client):
        resp = app_client.post(
            "/api/labels",
            json={
                "content_hash": HASH_A,
                "boxes": [{"x": 0, "y": 0, "w": 0.1, "h": 0.1, "number": "1", "tag": "invalid_tag"}],
                "tags": [],
                "split": "full",
            },
        )
        assert resp.status_code == 400

    def test_bib_boxes_include_split(self, app_client):
        """GET bib boxes includes split info."""
        app_client.post(
            "/api/labels",
            json={
                "content_hash": HASH_A,
                "boxes": [],
                "tags": ["no_bib"],
                "split": "iteration",
            },
        )
        resp = app_client.get(f"/api/bib_boxes/{HASH_A}")
        data = resp.get_json()
        assert data["split"] == "iteration"
        assert "no_bib" in data["tags"]


# =============================================================================
# Face Box API
# =============================================================================


class TestFaceBoxApi:
    def test_get_face_boxes_empty(self, app_client):
        resp = app_client.get(f"/api/face_boxes/{HASH_A}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["boxes"] == []

    def test_save_and_load_face_boxes(self, app_client):
        boxes = [
            {"x": 0.1, "y": 0.2, "w": 0.15, "h": 0.2, "scope": "keep", "identity": "Alice"},
            {"x": 0.5, "y": 0.3, "w": 0.1, "h": 0.15, "scope": "ignore"},
        ]
        save_resp = app_client.post(
            "/api/face_labels",
            json={"content_hash": HASH_A, "boxes": boxes, "face_tags": []},
        )
        assert save_resp.status_code == 200

        resp = app_client.get(f"/api/face_boxes/{HASH_A}")
        data = resp.get_json()
        assert len(data["boxes"]) == 2
        assert data["boxes"][0]["scope"] == "keep"
        assert data["boxes"][0]["identity"] == "Alice"
        assert data["boxes"][1]["scope"] == "ignore"

    def test_save_face_backward_compat(self, app_client):
        """Sending face_count without boxes keeps current behavior (compat tags)."""
        resp = app_client.post(
            "/api/face_labels",
            json={"content_hash": HASH_A, "face_count": 3, "face_tags": ["face_tiny_faces"]},
        )
        assert resp.status_code == 200

        get_resp = app_client.get(f"/api/face_boxes/{HASH_A}")
        data = get_resp.get_json()
        assert "face_tiny_faces" in data["tags"]

    def test_save_and_load_face_boxes_with_tags(self, app_client):
        """Save face boxes with per-box tags, verify round-trip."""
        boxes = [
            {"x": 0.1, "y": 0.2, "w": 0.15, "h": 0.2, "scope": "keep", "tags": ["tiny", "blurry"]},
            {"x": 0.5, "y": 0.3, "w": 0.1, "h": 0.15, "scope": "ignore", "tags": ["profile"]},
        ]
        save_resp = app_client.post(
            "/api/face_labels",
            json={"content_hash": HASH_A, "boxes": boxes, "face_tags": ["face_no_faces"]},
        )
        assert save_resp.status_code == 200

        resp = app_client.get(f"/api/face_boxes/{HASH_A}")
        data = resp.get_json()
        assert len(data["boxes"]) == 2
        assert data["boxes"][0]["tags"] == ["tiny", "blurry"]
        assert data["boxes"][1]["tags"] == ["profile"]
        assert "face_no_faces" in data["tags"]

    def test_save_face_box_invalid_tag_400(self, app_client):
        """Invalid per-box tag returns 400."""
        resp = app_client.post(
            "/api/face_labels",
            json={
                "content_hash": HASH_A,
                "boxes": [{"x": 0, "y": 0, "w": 0.1, "h": 0.1, "scope": "keep", "tags": ["invalid"]}],
                "face_tags": [],
            },
        )
        assert resp.status_code == 400

    def test_face_boxes_empty_tags_omitted(self, app_client):
        """Boxes with no tags don't include tags key in response."""
        boxes = [{"x": 0.1, "y": 0.2, "w": 0.15, "h": 0.2, "scope": "keep"}]
        app_client.post(
            "/api/face_labels",
            json={"content_hash": HASH_A, "boxes": boxes, "face_tags": []},
        )
        resp = app_client.get(f"/api/face_boxes/{HASH_A}")
        data = resp.get_json()
        # Box should have no "tags" key when empty (FaceBox.to_dict omits it)
        assert "tags" not in data["boxes"][0]

    def test_get_face_boxes_with_suggestions(self, app_client):
        store = SuggestionStore()
        store.add(
            PhotoSuggestions(
                content_hash=HASH_A,
                faces=[FaceSuggestion(x=0.2, y=0.3, w=0.1, h=0.15, confidence=0.85)],
            )
        )
        save_suggestion_store(store)

        resp = app_client.get(f"/api/face_boxes/{HASH_A}")
        data = resp.get_json()
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["confidence"] == pytest.approx(0.85)

    def test_get_face_boxes_unknown_hash_404(self, app_client):
        resp = app_client.get(f"/api/face_boxes/{HASH_UNKNOWN}")
        assert resp.status_code == 404

    def test_save_invalid_scope_400(self, app_client):
        resp = app_client.post(
            "/api/face_labels",
            json={
                "content_hash": HASH_A,
                "boxes": [{"x": 0, "y": 0, "w": 0.1, "h": 0.1, "scope": "bad_scope"}],
                "face_tags": [],
            },
        )
        assert resp.status_code == 400


# =============================================================================
# Identities API
# =============================================================================


class TestIdentitiesApi:
    def test_get_identities_empty(self, app_client):
        resp = app_client.get("/api/identities")
        assert resp.status_code == 200
        assert resp.get_json()["identities"] == []

    def test_add_identity(self, app_client):
        resp = app_client.post(
            "/api/identities", json={"name": "Bob"}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "Bob" in data["identities"]

    def test_add_duplicate_idempotent(self, app_client):
        app_client.post("/api/identities", json={"name": "Alice"})
        app_client.post("/api/identities", json={"name": "Alice"})
        resp = app_client.get("/api/identities")
        data = resp.get_json()
        assert data["identities"].count("Alice") == 1

    def test_identities_sorted(self, app_client):
        app_client.post("/api/identities", json={"name": "Charlie"})
        app_client.post("/api/identities", json={"name": "Alice"})
        app_client.post("/api/identities", json={"name": "Bob"})
        resp = app_client.get("/api/identities")
        data = resp.get_json()
        assert data["identities"] == ["Alice", "Bob", "Charlie"]

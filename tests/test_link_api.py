"""Tests for the bib-face link API endpoints."""

import pytest
from starlette.testclient import TestClient

from benchmarking.photo_index import save_photo_index


HASH_A = "a" * 64
HASH_UNKNOWN = "f" * 64


@pytest.fixture
def link_client(tmp_path, monkeypatch):
    """Test client with link GT path and photo index patched."""
    link_gt_path = tmp_path / "bib_face_links.json"
    bib_gt_path = tmp_path / "bib_ground_truth.json"
    face_gt_path = tmp_path / "face_ground_truth.json"
    suggestions_path = tmp_path / "suggestions.json"
    identities_path = tmp_path / "face_identities.json"
    index_path = tmp_path / "photo_index.json"

    save_photo_index({HASH_A: ["photo_a.jpg"]}, index_path)

    monkeypatch.setattr(
        "benchmarking.ground_truth.get_link_ground_truth_path", lambda: link_gt_path
    )
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


class TestLinkPhotoRoute:
    def test_link_photo_route(self, link_client):
        """GET /associations/<hash> returns 200 and contains expected content."""
        resp = link_client.get(f"/associations/{HASH_A}")
        assert resp.status_code == 200
        html = resp.text
        assert "page-data" in html
        assert "link_labeling_ui.js" in html

    def test_link_photo_unknown_hash_404(self, link_client):
        """GET /associations/<unknown> returns 404."""
        resp = link_client.get(f"/associations/{HASH_UNKNOWN}")
        assert resp.status_code == 404

    def test_old_links_photo_redirects_301(self, link_client):
        """GET /links/<hash> returns 301 to /associations/<hash>."""
        resp = link_client.get(f"/links/{HASH_A}")
        assert resp.status_code == 301
        assert f"/associations/{HASH_A}" in resp.headers["Location"]


class TestBibFaceLinkApi:
    def test_get_links_no_data(self, link_client):
        """GET for a hash with no links returns empty list."""
        resp = link_client.get(f"/api/associations/{HASH_A}")
        assert resp.status_code == 200
        assert resp.json() == {"links": []}

    def test_put_and_get_links(self, link_client):
        """PUT links, then GET returns same list."""
        resp = link_client.put(
            f"/api/associations/{HASH_A}",
            json={"links": [[0, 1], [2, 0]]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["links"] == [[0, 1], [2, 0]]

        get_resp = link_client.get(f"/api/associations/{HASH_A}")
        assert get_resp.status_code == 200
        assert get_resp.json()["links"] == [[0, 1], [2, 0]]

    def test_put_links_replaces_all(self, link_client):
        """Second PUT fully replaces first."""
        link_client.put(
            f"/api/associations/{HASH_A}",
            json={"links": [[0, 1], [1, 2]]},
        )
        link_client.put(
            f"/api/associations/{HASH_A}",
            json={"links": [[3, 4]]},
        )
        resp = link_client.get(f"/api/associations/{HASH_A}")
        assert resp.json()["links"] == [[3, 4]]

    def test_get_links_unknown_hash_404(self, link_client):
        """GET for unknown hash returns 404."""
        resp = link_client.get(f"/api/associations/{HASH_UNKNOWN}")
        assert resp.status_code == 404

    def test_put_links_unknown_hash_404(self, link_client):
        """PUT for unknown hash returns 404."""
        resp = link_client.put(
            f"/api/associations/{HASH_UNKNOWN}",
            json={"links": [[0, 1]]},
        )
        assert resp.status_code == 404

    def test_put_links_invalid_json(self, link_client):
        """PUT with malformed JSON body returns 400."""
        resp = link_client.put(
            f"/api/associations/{HASH_A}",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    def test_put_links_empty(self, link_client):
        """PUT empty list clears all links."""
        link_client.put(
            f"/api/associations/{HASH_A}",
            json={"links": [[0, 1]]},
        )
        link_client.put(
            f"/api/associations/{HASH_A}",
            json={"links": []},
        )
        resp = link_client.get(f"/api/associations/{HASH_A}")
        assert resp.json()["links"] == []

    def test_old_bib_face_links_get_redirects_308(self, link_client):
        """GET /api/bib_face_links/<hash> returns 308 redirect."""
        resp = link_client.get(f"/api/bib_face_links/{HASH_A}")
        assert resp.status_code == 308

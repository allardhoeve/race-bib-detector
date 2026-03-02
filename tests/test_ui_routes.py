"""Integration tests for UI route handlers (bib_photo, face_photo, frozen_photo_detail).

association_photo is tested in test_link_api.py.
benchmark_inspect is tested in benchmarking/test_inspect_route.py.
"""

import pytest
from starlette.testclient import TestClient

from benchmarking.ground_truth import (
    BibGroundTruth,
    BibPhotoLabel,
    FaceGroundTruth,
    FacePhotoLabel,
    save_bib_ground_truth,
    save_face_ground_truth,
)
from benchmarking.photo_index import save_photo_index

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_FROZEN = "f" * 64


@pytest.fixture
def labeling_client(benchmark_paths, tmp_path, monkeypatch):
    """Test client with photo index, bib/face GT, and all paths monkeypatched."""
    save_photo_index({HASH_A: ["photo_a.jpg"], HASH_B: ["photo_b.jpg"]}, benchmark_paths["photo_metadata"])

    bib_gt = BibGroundTruth()
    bib_gt.add_photo(BibPhotoLabel(content_hash=HASH_A, labeled=True))
    save_bib_ground_truth(bib_gt)

    face_gt = FaceGroundTruth()
    face_gt.add_photo(FacePhotoLabel(content_hash=HASH_A, labeled=True))
    save_face_ground_truth(face_gt)

    monkeypatch.setattr("benchmarking.routes.ui.nav.is_frozen", lambda h: None)
    monkeypatch.setattr("benchmarking.runner.RESULTS_DIR", tmp_path / "no_results")

    from benchmarking.app import create_app
    app = create_app()
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def frozen_labeling_client(benchmark_paths, tmp_path, monkeypatch):
    """Test client where HASH_FROZEN is in a frozen set."""
    save_photo_index(
        {HASH_A: ["photo_a.jpg"], HASH_FROZEN: ["photo_f.jpg"]},
        benchmark_paths["photo_metadata"],
    )

    bib_gt = BibGroundTruth()
    bib_gt.add_photo(BibPhotoLabel(content_hash=HASH_A, labeled=True))
    save_bib_ground_truth(bib_gt)

    face_gt = FaceGroundTruth()
    face_gt.add_photo(FacePhotoLabel(content_hash=HASH_A, labeled=True))
    save_face_ground_truth(face_gt)

    monkeypatch.setattr("benchmarking.sets.FROZEN_DIR", tmp_path / "frozen")
    monkeypatch.setattr("benchmarking.runner.RESULTS_DIR", tmp_path / "no_results")

    monkeypatch.setattr(
        "benchmarking.routes.ui.nav.is_frozen",
        lambda h: "verified-set" if h == HASH_FROZEN else None,
    )

    from benchmarking.sets import BenchmarkSnapshot, BenchmarkSnapshotMetadata
    snap = BenchmarkSnapshot(
        metadata=BenchmarkSnapshotMetadata(
            name="verified-set",
            description="test snapshot",
            photo_count=1,
            created_at="2025-01-01T00:00:00",
        ),
        hashes=[HASH_FROZEN],
        index={HASH_FROZEN: "photo_f.jpg"},
    )
    snap.save()

    from benchmarking.app import create_app
    app = create_app()
    return TestClient(app, follow_redirects=False)


# =============================================================================
# Bib photo
# =============================================================================


class TestBibPhoto:
    def test_renders_200(self, labeling_client):
        resp = labeling_client.get(f"/bibs/{HASH_A[:8]}?filter=all")
        assert resp.status_code == 200
        assert HASH_A in resp.text

    def test_404_unknown_hash(self, labeling_client):
        resp = labeling_client.get("/bibs/deadbeef?filter=all")
        assert resp.status_code == 404

    def test_frozen_redirect(self, frozen_labeling_client):
        resp = frozen_labeling_client.get(f"/bibs/{HASH_FROZEN[:8]}?filter=all")
        assert resp.status_code == 302
        assert "/frozen/verified-set/" in resp.headers["location"]

    def test_empty_filter_shows_empty_page(self, labeling_client):
        # With filter=labeled, only HASH_A is labeled; HASH_B is not.
        # But with filter=unlabeled and only HASH_A labeled, HASH_B should appear.
        # Use a filter that yields no results — we need all photos labeled for that.
        # Label HASH_B via API first, then filter=unlabeled → empty
        labeling_client.put(
            f"/api/bibs/{HASH_B[:8]}",
            json={"boxes": [], "tags": [], "split": "full"},
        )
        resp = labeling_client.get("/bibs/?filter=unlabeled")
        # Should render empty.html (200) since both are labeled
        assert resp.status_code == 200
        assert "No Photos Found" in resp.text

    def test_navigation_shows_position(self, labeling_client):
        resp = labeling_client.get(f"/bibs/{HASH_A[:8]}?filter=all")
        assert resp.status_code == 200
        # Should show "1 / 2" or "2 / 2" depending on sort order
        assert "/ 2" in resp.text


# =============================================================================
# Face photo
# =============================================================================


class TestFacePhoto:
    def test_renders_200(self, labeling_client):
        resp = labeling_client.get(f"/faces/{HASH_A[:8]}?filter=all")
        assert resp.status_code == 200
        assert HASH_A in resp.text

    def test_404_unknown_hash(self, labeling_client):
        resp = labeling_client.get("/faces/deadbeef?filter=all")
        assert resp.status_code == 404

    def test_frozen_redirect(self, frozen_labeling_client):
        resp = frozen_labeling_client.get(f"/faces/{HASH_FROZEN[:8]}?filter=all")
        assert resp.status_code == 302
        assert "/frozen/verified-set/" in resp.headers["location"]


# =============================================================================
# Frozen photo detail
# =============================================================================


class TestFrozenPhotoDetail:
    def test_renders_200(self, frozen_labeling_client):
        resp = frozen_labeling_client.get(f"/frozen/verified-set/{HASH_FROZEN[:8]}")
        assert resp.status_code == 200
        assert HASH_FROZEN in resp.text

    def test_404_unknown_hash(self, frozen_labeling_client):
        resp = frozen_labeling_client.get("/frozen/verified-set/deadbeef")
        assert resp.status_code == 404

    def test_404_unknown_set(self, frozen_labeling_client):
        resp = frozen_labeling_client.get(f"/frozen/nonexistent/{HASH_FROZEN[:8]}")
        assert resp.status_code == 404

    def test_navigation_single_photo(self, frozen_labeling_client):
        resp = frozen_labeling_client.get(f"/frozen/verified-set/{HASH_FROZEN[:8]}")
        assert resp.status_code == 200
        # Single photo in set — should show 1 / 1
        assert "1 / 1" in resp.text

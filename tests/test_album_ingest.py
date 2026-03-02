"""Tests for scan/service.py — ingest_album() and rescan_and_cluster()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scan.service import ingest_album, rescan_and_cluster


SCAN_STATS = {
    "photos_found": 5,
    "photos_scanned": 5,
    "photos_skipped": 0,
    "bibs_detected": 3,
    "faces_detected": 10,
}
CLUSTER_STATS = {
    "album_id": "abc123",
    "clusters_created": 4,
    "members_created": 10,
    "faces_seen": 10,
    "models": 1,
}

# cluster_album_faces is lazy-imported inside the function body,
# so we patch it at its source module.
_PATCH_CLUSTER = "faces.clustering.cluster_album_faces"


class TestIngestAlbum:
    @patch(_PATCH_CLUSTER)
    @patch("scan.service.scan_local_directory")
    @patch("scan.service.db")
    def test_ingest_calls_scan_then_cluster(self, mock_db, mock_scan, mock_cluster):
        mock_scan.return_value = SCAN_STATS.copy()
        mock_cluster.return_value = CLUSTER_STATS.copy()
        mock_db.compute_album_id.return_value = "abc123"
        mock_db.get_connection.return_value = MagicMock()

        result = ingest_album("/some/dir")

        mock_scan.assert_called_once()
        mock_cluster.assert_called_once()
        assert result["photos_scanned"] == 5
        assert result["clusters_created"] == 4

    @patch(_PATCH_CLUSTER)
    @patch("scan.service.scan_local_directory")
    @patch("scan.service.db")
    def test_ingest_skips_clustering_when_zero_faces(self, mock_db, mock_scan, mock_cluster):
        stats = SCAN_STATS.copy()
        stats["faces_detected"] = 0
        mock_scan.return_value = stats
        mock_db.compute_album_id.return_value = "abc123"

        result = ingest_album("/some/dir")

        mock_cluster.assert_not_called()
        assert result["faces_detected"] == 0
        assert "clusters_created" not in result

    @patch(_PATCH_CLUSTER)
    @patch("scan.service.scan_local_directory")
    @patch("scan.service.db")
    def test_ingest_resolves_album_id_from_label(self, mock_db, mock_scan, mock_cluster):
        mock_scan.return_value = SCAN_STATS.copy()
        mock_cluster.return_value = CLUSTER_STATS.copy()
        mock_db.compute_album_id.return_value = "lbl123"
        mock_db.get_connection.return_value = MagicMock()

        ingest_album("/some/dir", album_label="Race 2026")

        mock_db.compute_album_id.assert_called_with("Race 2026")

    @patch(_PATCH_CLUSTER)
    @patch("scan.service.scan_local_directory")
    @patch("scan.service.db")
    def test_ingest_resolves_album_id_from_path(self, mock_db, mock_scan, mock_cluster):
        mock_scan.return_value = SCAN_STATS.copy()
        mock_cluster.return_value = CLUSTER_STATS.copy()
        mock_db.compute_album_id.return_value = "pth123"
        mock_db.get_connection.return_value = MagicMock()

        ingest_album("/some/dir")

        # No label → resolves from path
        mock_db.compute_album_id.assert_called_once()
        call_arg = mock_db.compute_album_id.call_args[0][0]
        assert "/some/dir" in call_arg or "some/dir" in call_arg

    @patch(_PATCH_CLUSTER)
    @patch("scan.service.scan_local_directory")
    @patch("scan.service.db")
    def test_ingest_uses_explicit_album_id(self, mock_db, mock_scan, mock_cluster):
        mock_scan.return_value = SCAN_STATS.copy()
        mock_cluster.return_value = CLUSTER_STATS.copy()
        mock_db.get_connection.return_value = MagicMock()

        ingest_album("/some/dir", album_id="explicit_id")

        mock_db.compute_album_id.assert_not_called()
        # Verify the explicit album_id was passed to scan
        _, kwargs = mock_scan.call_args
        assert kwargs.get("album_id") == "explicit_id"

    def test_ingest_rejects_url(self):
        with pytest.raises(ValueError, match="not supported"):
            ingest_album("https://example.com/photos")

    def test_ingest_rejects_photo_identifier(self):
        with pytest.raises(ValueError, match="photo identifier"):
            ingest_album("6dde41fd")

    @patch(_PATCH_CLUSTER)
    @patch("scan.service.scan_local_directory")
    @patch("scan.service.db")
    def test_ingest_passes_limit(self, mock_db, mock_scan, mock_cluster):
        mock_scan.return_value = SCAN_STATS.copy()
        mock_cluster.return_value = CLUSTER_STATS.copy()
        mock_db.compute_album_id.return_value = "abc123"
        mock_db.get_connection.return_value = MagicMock()

        ingest_album("/some/dir", limit=10)

        _, kwargs = mock_scan.call_args
        assert kwargs.get("limit") == 10


class TestRescanAndCluster:
    @patch(_PATCH_CLUSTER)
    @patch("scan.service.rescan_single_photo")
    @patch("scan.service.db")
    def test_rescan_calls_rescan_then_cluster(self, mock_db, mock_rescan, mock_cluster):
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn
        mock_db.get_photo_by_hash.return_value = {
            "album_id": "alb1",
            "photo_hash": "6dde41fd",
        }
        mock_rescan.return_value = SCAN_STATS.copy()
        mock_cluster.return_value = CLUSTER_STATS.copy()

        result = rescan_and_cluster("6dde41fd")

        mock_rescan.assert_called_once_with("6dde41fd")
        mock_cluster.assert_called_once()
        assert result["photos_scanned"] == 5
        assert result["clusters_created"] == 4

    @patch("scan.service.rescan_single_photo")
    @patch("scan.service.db")
    def test_rescan_raises_for_unknown_photo(self, mock_db, mock_rescan):
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn
        mock_db.get_photo_by_hash.return_value = None
        mock_db.get_photo_by_index.return_value = None

        with pytest.raises(ValueError, match="not found"):
            rescan_and_cluster("deadbeef")

    @patch(_PATCH_CLUSTER)
    @patch("scan.service.rescan_single_photo")
    @patch("scan.service.db")
    def test_rescan_finds_album_id_from_photo(self, mock_db, mock_rescan, mock_cluster):
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn
        mock_db.get_photo_by_hash.return_value = {
            "album_id": "my_album",
            "photo_hash": "aabbccdd",
        }
        mock_rescan.return_value = SCAN_STATS.copy()
        mock_cluster.return_value = CLUSTER_STATS.copy()

        rescan_and_cluster("aabbccdd")

        # Verify cluster was called with the correct album_id
        call_args = mock_cluster.call_args
        assert call_args[0][1] == "my_album"

    @patch(_PATCH_CLUSTER)
    @patch("scan.service.rescan_single_photo")
    @patch("scan.service.db")
    def test_rescan_looks_up_by_index(self, mock_db, mock_rescan, mock_cluster):
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn
        mock_db.get_photo_by_hash.return_value = None
        mock_db.get_photo_by_index.return_value = {
            "album_id": "alb1",
            "photo_hash": "12345678",
        }
        mock_rescan.return_value = SCAN_STATS.copy()
        mock_cluster.return_value = CLUSTER_STATS.copy()

        rescan_and_cluster("47")

        mock_db.get_photo_by_index.assert_called_once_with(mock_conn, 47)
        mock_rescan.assert_called_once_with("47")

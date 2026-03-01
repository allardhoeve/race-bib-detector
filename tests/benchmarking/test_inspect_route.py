"""Tests for benchmark inspect route JSON enrichment (task-052)."""

from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

from benchmarking.ground_truth import BibBox, BibFaceLink, FaceBox
from benchmarking.runner import (
    BenchmarkMetrics,
    BenchmarkRun,
    PhotoResult,
    RunMetadata,
)


def _make_metadata() -> RunMetadata:
    return RunMetadata(
        run_id="test1234",
        timestamp="2025-01-01T00:00:00",
        split="full",
        git_commit="deadbeef",
        git_dirty=False,
        python_version="3.14",
        package_versions={},
        hostname="testhost",
        gpu_info=None,
        total_runtime_seconds=1.0,
    )


def _make_metrics() -> BenchmarkMetrics:
    return BenchmarkMetrics(
        total_photos=1, total_tp=1, total_fp=0, total_fn=0,
        precision=1.0, recall=1.0, f1=1.0,
        pass_count=1, partial_count=0, miss_count=0,
    )


def _make_photo_result(
    content_hash: str = "a" * 64,
    pred_bib_boxes: list[BibBox] | None = None,
    pred_face_boxes: list[FaceBox] | None = None,
    gt_bib_boxes: list[BibBox] | None = None,
    gt_face_boxes: list[FaceBox] | None = None,
) -> PhotoResult:
    return PhotoResult(
        content_hash=content_hash,
        expected_bibs=[42],
        detected_bibs=[42],
        tp=1, fp=0, fn=0,
        status="PASS",
        detection_time_ms=100.0,
        pred_bib_boxes=pred_bib_boxes,
        pred_face_boxes=pred_face_boxes,
        gt_bib_boxes=gt_bib_boxes,
        gt_face_boxes=gt_face_boxes,
    )


def _make_run(photo_results: list[PhotoResult]) -> BenchmarkRun:
    return BenchmarkRun(
        metadata=_make_metadata(),
        metrics=_make_metrics(),
        photo_results=photo_results,
    )


def _extract_photo_results_json(html: str) -> list[dict]:
    """Extract photo_results_json from rendered HTML page."""
    # The template embeds it as: photoResults: {{ photo_results_json|safe }}
    # Find the JSON between 'photoResults: ' and the next newline/semicolon
    marker = "photoResults: "
    start = html.index(marker) + len(marker)
    # Find the end — it's followed by a comma or newline
    depth = 0
    end = start
    for i, ch in enumerate(html[start:], start):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    return json.loads(html[start:end])


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client with a monkeypatched run and link GT."""
    from benchmarking.app import create_app

    # Monkeypatch RESULTS_DIR so get_run finds our test run
    monkeypatch.setattr("benchmarking.runner.RESULTS_DIR", tmp_path / "results")
    # Monkeypatch link GT path to tmp
    monkeypatch.setattr(
        "benchmarking.ground_truth.get_link_ground_truth_path",
        lambda: tmp_path / "links.json",
    )

    app = create_app()
    return TestClient(app, follow_redirects=False)


def _save_run(tmp_path, run: BenchmarkRun) -> None:
    run_dir = tmp_path / "results" / run.metadata.run_id
    run_dir.mkdir(parents=True)
    run.save(run_dir / "run.json")


class TestInspectJsonBoxFields:
    def test_includes_pred_bib_boxes(self, client, tmp_path):
        bib_boxes = [BibBox(x=0.1, y=0.2, w=0.3, h=0.4, number="42", scope="bib")]
        pr = _make_photo_result(pred_bib_boxes=bib_boxes, gt_bib_boxes=bib_boxes)
        _save_run(tmp_path, _make_run([pr]))

        resp = client.get("/benchmark/test1234/")
        assert resp.status_code == 200

        data = _extract_photo_results_json(resp.text)
        assert len(data) == 1
        assert "pred_bib_boxes" in data[0]
        assert len(data[0]["pred_bib_boxes"]) == 1
        assert data[0]["pred_bib_boxes"][0]["number"] == "42"

    def test_includes_gt_bib_boxes(self, client, tmp_path):
        gt_boxes = [BibBox(x=0.1, y=0.2, w=0.3, h=0.4, number="7", scope="bib")]
        pr = _make_photo_result(gt_bib_boxes=gt_boxes)
        _save_run(tmp_path, _make_run([pr]))

        resp = client.get("/benchmark/test1234/")
        data = _extract_photo_results_json(resp.text)
        assert "gt_bib_boxes" in data[0]
        assert data[0]["gt_bib_boxes"][0]["number"] == "7"

    def test_includes_face_boxes(self, client, tmp_path):
        pred_faces = [FaceBox(x=0.5, y=0.5, w=0.1, h=0.1, scope="keep")]
        gt_faces = [FaceBox(x=0.5, y=0.5, w=0.1, h=0.1, scope="keep", identity="alice")]
        pr = _make_photo_result(pred_face_boxes=pred_faces, gt_face_boxes=gt_faces)
        _save_run(tmp_path, _make_run([pr]))

        resp = client.get("/benchmark/test1234/")
        data = _extract_photo_results_json(resp.text)
        assert "pred_face_boxes" in data[0]
        assert "gt_face_boxes" in data[0]
        assert data[0]["gt_face_boxes"][0]["identity"] == "alice"

    def test_excludes_none_boxes(self, client, tmp_path):
        # Old-style result with no box data
        pr = _make_photo_result()
        _save_run(tmp_path, _make_run([pr]))

        resp = client.get("/benchmark/test1234/")
        data = _extract_photo_results_json(resp.text)
        assert "pred_bib_boxes" not in data[0]
        assert "pred_face_boxes" not in data[0]
        assert "gt_bib_boxes" not in data[0]
        assert "gt_face_boxes" not in data[0]

    def test_includes_gt_links(self, client, tmp_path):
        content_hash = "a" * 64
        pr = _make_photo_result(content_hash=content_hash)
        _save_run(tmp_path, _make_run([pr]))

        # Write link GT
        from benchmarking.ground_truth import LinkGroundTruth, save_link_ground_truth
        link_gt = LinkGroundTruth()
        link_gt.set_links(content_hash, [BibFaceLink(bib_index=0, face_index=1)])
        save_link_ground_truth(link_gt, tmp_path / "links.json")

        resp = client.get("/benchmark/test1234/")
        data = _extract_photo_results_json(resp.text)
        assert "gt_links" in data[0]
        assert len(data[0]["gt_links"]) == 1
        assert data[0]["gt_links"][0] == {"bib_index": 0, "face_index": 1}

    def test_gt_links_empty_when_no_links(self, client, tmp_path):
        pr = _make_photo_result()
        _save_run(tmp_path, _make_run([pr]))

        resp = client.get("/benchmark/test1234/")
        data = _extract_photo_results_json(resp.text)
        assert data[0]["gt_links"] == []


class TestInspectOverlayAssets:
    def test_template_includes_overlay_script(self, client, tmp_path):
        pr = _make_photo_result()
        _save_run(tmp_path, _make_run([pr]))

        resp = client.get("/benchmark/test1234/")
        assert resp.status_code == 200
        assert "inspect_overlay.js" in resp.text

    def test_template_includes_overlay_canvas(self, client, tmp_path):
        pr = _make_photo_result()
        _save_run(tmp_path, _make_run([pr]))

        resp = client.get("/benchmark/test1234/")
        assert 'id="box-overlay"' in resp.text

    def test_template_includes_overlay_controls(self, client, tmp_path):
        pr = _make_photo_result()
        _save_run(tmp_path, _make_run([pr]))

        resp = client.get("/benchmark/test1234/")
        assert 'id="show-bib-boxes"' in resp.text
        assert 'id="show-face-boxes"' in resp.text
        assert 'id="show-gt"' in resp.text
        assert 'id="show-pred"' in resp.text
        assert 'id="show-links"' in resp.text

"""Pytest configuration — fast-by-default TDD setup.

Slow tests (real OCR / ML model loading) are skipped unless --slow is passed.
Run the full suite:   pytest --slow
Run fast tests only:  pytest          (default)
"""
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--slow",
        action="store_true",
        default=False,
        help="Run slow tests that load ML models (EasyOCR, FaceNet, etc.)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--slow"):
        return  # run everything
    skip_slow = pytest.mark.skip(reason="slow test skipped — pass --slow to include")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)


@pytest.fixture
def benchmark_paths(tmp_path, monkeypatch):
    """Patch all common path-returning functions to redirect to tmp_path.

    Returns a dict of paths for tests that need to reference them directly.
    Not autouse — each file opts in by requesting this fixture.
    """
    paths = {
        "bib_gt": tmp_path / "bib_ground_truth.json",
        "face_gt": tmp_path / "face_ground_truth.json",
        "link_gt": tmp_path / "bib_face_links.json",
        "suggestions": tmp_path / "suggestions.json",
        "identities": tmp_path / "face_identities.json",
        "photo_metadata": tmp_path / "photo_metadata.json",
        "photo_index": tmp_path / "photo_index.json",
    }
    monkeypatch.setattr("benchmarking.ground_truth.get_bib_ground_truth_path", lambda: paths["bib_gt"])
    monkeypatch.setattr("benchmarking.ground_truth.get_face_ground_truth_path", lambda: paths["face_gt"])
    monkeypatch.setattr("benchmarking.ground_truth.get_link_ground_truth_path", lambda: paths["link_gt"])
    monkeypatch.setattr("benchmarking.ghost.get_suggestion_store_path", lambda: paths["suggestions"])
    monkeypatch.setattr("benchmarking.identities.get_identities_path", lambda: paths["identities"])
    monkeypatch.setattr("benchmarking.photo_metadata.get_photo_metadata_path", lambda: paths["photo_metadata"])
    monkeypatch.setattr("benchmarking.photo_index.get_photo_index_path", lambda: paths["photo_index"])
    return paths

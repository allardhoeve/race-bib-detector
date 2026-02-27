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

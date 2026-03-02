"""Unit tests for benchmarking.services.association_service."""

import pytest

from benchmarking.photo_index import save_photo_index
from benchmarking.services import association_service

HASH_A = "a" * 64
HASH_UNKNOWN = "f" * 64


@pytest.fixture(autouse=True)
def patch_paths(benchmark_paths):
    save_photo_index({HASH_A: ["photo_a.jpg"]}, benchmark_paths["photo_metadata"])


def test_get_associations_not_found():
    result = association_service.get_associations(HASH_UNKNOWN[:8])
    assert result is None


def test_set_then_get():
    saved = association_service.set_associations(HASH_A[:8], [[0, 1], [2, 3]])
    assert saved == [[0, 1], [2, 3]]

    retrieved = association_service.get_associations(HASH_A[:8])
    assert retrieved == [[0, 1], [2, 3]]


def test_set_associations_invalid_pair():
    """A pair with too few elements raises IndexError."""
    with pytest.raises((TypeError, IndexError, ValueError)):
        association_service.set_associations(HASH_A[:8], [[0]])

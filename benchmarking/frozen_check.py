"""Frozen-set guard helpers for route handlers."""

from __future__ import annotations

from fastapi import HTTPException

from benchmarking.photo_metadata import load_photo_metadata


def is_frozen(content_hash: str) -> str | None:
    """Return snapshot name if hash is frozen, else None."""
    store = load_photo_metadata()
    return store.is_frozen(content_hash)


def require_not_frozen(content_hash: str) -> None:
    """Raise HTTPException(409) if hash is in a frozen set."""
    set_name = is_frozen(content_hash)
    if set_name:
        raise HTTPException(
            status_code=409,
            detail=f"Photo is in frozen set '{set_name}' and cannot be edited",
        )

"""Shared hash resolution + navigation for photo detail pages."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request
from starlette.responses import RedirectResponse

from benchmarking.frozen_check import is_frozen
from benchmarking.label_utils import find_hash_by_prefix
from benchmarking.photo_index import load_photo_index


@dataclass
class PhotoNavContext:
    """Resolved hash + navigation state for a photo detail page."""

    full_hash: str
    idx: int  # 0-based position in filtered list
    total: int
    prev_url: str | None
    next_url: str | None
    all_index: dict  # full photo index (for next-unlabeled lookups)


def resolve_photo_nav(
    content_hash: str,
    filtered_hashes: list[str],
    request: Request,
    route_name: str,
    filter_suffix: str = '',
) -> PhotoNavContext | RedirectResponse:
    """Resolve hash prefix, check frozen, build prev/next navigation.

    Returns RedirectResponse if the photo is frozen,
    raises HTTPException(404) if not found,
    otherwise returns PhotoNavContext.
    """
    # Resolve from full index (needed for frozen check on hashes not in filter)
    all_index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(all_index.keys()))

    # Frozen redirect
    if full_hash:
        frozen_set = is_frozen(full_hash)
        if frozen_set:
            return RedirectResponse(
                url=str(request.url_for(
                    'frozen_photo_detail',
                    set_name=frozen_set,
                    content_hash=full_hash[:8],
                )),
                status_code=302,
            )

    # Resolve from filtered hashes
    full_hash = find_hash_by_prefix(content_hash, filtered_hashes)
    if not full_hash:
        raise HTTPException(status_code=404, detail='Photo not found')

    # Navigation
    try:
        idx = filtered_hashes.index(full_hash)
    except ValueError:
        raise HTTPException(status_code=404, detail='Photo not in current filter')

    total = len(filtered_hashes)
    prev_url = (
        str(request.url_for(route_name, content_hash=filtered_hashes[idx - 1][:8]))
        + filter_suffix
    ) if idx > 0 else None
    next_url = (
        str(request.url_for(route_name, content_hash=filtered_hashes[idx + 1][:8]))
        + filter_suffix
    ) if idx < total - 1 else None

    return PhotoNavContext(
        full_hash=full_hash,
        idx=idx,
        total=total,
        prev_url=prev_url,
        next_url=next_url,
        all_index=all_index,
    )

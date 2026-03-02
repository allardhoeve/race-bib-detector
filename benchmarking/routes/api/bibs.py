"""Bib and association JSON API endpoints."""

import io
import random
from pathlib import Path
from typing import TypedDict

from fastapi import APIRouter, HTTPException
from PIL import Image
from starlette.responses import StreamingResponse

from benchmarking.frozen_check import require_not_frozen
from benchmarking.ghost import BibSuggestion, load_suggestion_store
from benchmarking.ground_truth import (
    BibFaceLink,
    BibPhotoLabel,
    load_bib_ground_truth,
    load_link_ground_truth,
    save_bib_ground_truth,
    save_link_ground_truth,
)
from benchmarking.label_utils import find_hash_by_prefix
from benchmarking.photo_index import load_photo_index, get_path_for_hash
from benchmarking.photo_metadata import (
    PhotoMetadata,
    load_photo_metadata,
    save_photo_metadata,
)
from benchmarking.schemas import (
    AssociationsResponse,
    BibBoxOut,
    BibSuggestionOut,
    GetBibBoxesResponse,
    SaveAssociationsRequest,
    SaveBibBoxesRequest,
)
from config import ITERATION_SPLIT_PROBABILITY
from pipeline.types import BibLabel

PHOTOS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "photos"

api_bibs_router = APIRouter()


# ---- Bib label helpers (inlined from services/bib_service.py) -------------


class BibLabelData(TypedDict):
    full_hash: str
    boxes: list[BibLabel]
    suggestions: list[BibSuggestion]
    tags: list[str]
    split: str
    labeled: bool


def _get_bib_label(content_hash: str) -> BibLabelData | None:
    """Return typed bib label data for a photo hash prefix, or None if not found."""
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return None

    bib_gt = load_bib_ground_truth()
    label = bib_gt.get_photo(full_hash)

    store = load_suggestion_store()
    photo_sugg = store.get(full_hash)
    suggestions: list[BibSuggestion] = photo_sugg.bibs if photo_sugg else []

    meta_store = load_photo_metadata()
    meta = meta_store.get(full_hash)

    if label:
        return BibLabelData(
            full_hash=full_hash,
            boxes=label.boxes,
            suggestions=suggestions,
            tags=meta.bib_tags if meta else [],
            split=meta.split if meta else "full",
            labeled=label.labeled,
        )
    return BibLabelData(
        full_hash=full_hash,
        boxes=[],
        suggestions=suggestions,
        tags=meta.bib_tags if meta else [],
        split=meta.split if meta else "full",
        labeled=False,
    )


def _save_bib_label(content_hash: str, boxes: list[BibLabel] | None,
                    bibs_legacy: list[int] | None, tags: list[str],
                    split: str) -> None:
    """Construct a BibPhotoLabel and persist it, plus save tags/split to PhotoMetadata."""
    bib_gt = load_bib_ground_truth()
    if boxes is not None:
        pass  # already validated BibLabel objects
    elif bibs_legacy is not None:
        boxes = [BibLabel(x=0, y=0, w=0, h=0, number=str(b), scope="bib")
                 for b in bibs_legacy]
    else:
        boxes = []
    label = BibPhotoLabel(
        content_hash=content_hash,
        boxes=boxes,
        labeled=True,
    )
    bib_gt.add_photo(label)
    save_bib_ground_truth(bib_gt)

    meta_store = load_photo_metadata()
    meta = meta_store.get(content_hash) or PhotoMetadata(paths=[])
    meta.bib_tags = tags
    meta.split = split
    meta_store.set(content_hash, meta)
    save_photo_metadata(meta_store)


def _get_bib_crop_jpeg(content_hash: str, box_index: int) -> bytes | None:
    """Return JPEG bytes of a labeled bib crop, or None if not found."""
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return None

    bib_gt = load_bib_ground_truth()
    label = bib_gt.get_photo(full_hash)
    if not label or box_index < 0 or box_index >= len(label.boxes):
        return None

    box = label.boxes[box_index]
    if not box.has_coords:
        return None

    photo_path = get_path_for_hash(full_hash, PHOTOS_DIR, index)
    if not photo_path or not photo_path.exists():
        return None

    img = Image.open(photo_path)
    w, h = img.size
    left = int(box.x * w)
    upper = int(box.y * h)
    right = int((box.x + box.w) * w)
    lower = int((box.y + box.h) * h)
    crop = img.crop((left, upper, right, lower))

    buf = io.BytesIO()
    crop.save(buf, format='JPEG', quality=85)
    buf.seek(0)
    return buf.read()


def default_split_for_hash(content_hash: str) -> str:
    """Return the existing split for a hash, or randomly assign one."""
    meta_store = load_photo_metadata()
    meta = meta_store.get(content_hash)
    if meta and meta.split:
        return meta.split
    return 'iteration' if random.random() < ITERATION_SPLIT_PROBABILITY else 'full'


# ---- Association helpers (inlined from services/association_service.py) ----


def _get_associations(content_hash: str) -> list[list[int]] | None:
    """Return links for a hash prefix as [[bib_index, face_index], ...].

    Returns None if the hash prefix is not found.
    """
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return None
    link_gt = load_link_ground_truth()
    return [lnk.to_pair() for lnk in link_gt.get_links(full_hash)]


def _set_associations(content_hash: str,
                      raw_links: list[list[int]]) -> list[list[int]] | None:
    """Replace all links for a hash prefix. Returns the saved links.

    Returns None if the hash prefix is not found.
    Raises ValueError / TypeError / IndexError on malformed link pairs.
    """
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return None
    links = [BibFaceLink.from_pair(pair) for pair in raw_links]
    link_gt = load_link_ground_truth()
    link_gt.set_links(full_hash, links)
    save_link_ground_truth(link_gt)
    return [lnk.to_pair() for lnk in links]


# ---- Route handlers -------------------------------------------------------


@api_bibs_router.get('/api/bibs/{content_hash}', response_model=GetBibBoxesResponse)
async def get_bib_boxes(content_hash: str) -> GetBibBoxesResponse:
    """Get bib boxes, suggestions, tags, split, and labeled status."""
    result = _get_bib_label(content_hash)
    if result is None:
        raise HTTPException(status_code=404, detail='Photo not found')
    return GetBibBoxesResponse(
        boxes=[BibBoxOut.model_validate(b.model_dump()) for b in result['boxes']],
        suggestions=[BibSuggestionOut.model_validate(s.to_dict()) for s in result['suggestions']],
        tags=result['tags'],
        split=result['split'],
        labeled=result['labeled'],
    )


@api_bibs_router.put('/api/bibs/{content_hash}')
async def save_bib_label(content_hash: str, request: SaveBibBoxesRequest):
    """Save bib boxes + tags + split for a photo. Replaces all existing data."""
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        raise HTTPException(status_code=404, detail='Photo not found')

    require_not_frozen(full_hash)

    try:
        boxes = [BibLabel.model_validate(b.model_dump()) for b in request.boxes] if request.boxes is not None else None
        _save_bib_label(
            content_hash=full_hash,
            boxes=boxes,
            bibs_legacy=request.bibs,
            tags=request.tags,
            split=request.split,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {'status': 'ok'}


@api_bibs_router.get('/api/bibs/{content_hash}/crop/{box_index}')
async def bib_crop(content_hash: str, box_index: int):
    """Return a JPEG crop of a labeled bib box."""
    jpeg_bytes = _get_bib_crop_jpeg(content_hash, box_index)
    if jpeg_bytes is None:
        raise HTTPException(status_code=404)
    return StreamingResponse(io.BytesIO(jpeg_bytes), media_type='image/jpeg')


@api_bibs_router.get('/api/associations/{content_hash}', response_model=AssociationsResponse)
async def get_associations(content_hash: str) -> AssociationsResponse:
    """Return the bib-face links for a photo."""
    links = _get_associations(content_hash)
    if links is None:
        raise HTTPException(status_code=404, detail='Not found')
    return AssociationsResponse(links=links)


@api_bibs_router.put('/api/associations/{content_hash}', response_model=AssociationsResponse)
async def save_associations(content_hash: str, request: SaveAssociationsRequest) -> AssociationsResponse:
    """Save the bib-face links for a photo. Replaces all existing links."""
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        raise HTTPException(status_code=404, detail='Photo not found')

    require_not_frozen(full_hash)

    try:
        saved = _set_associations(content_hash, request.links)
    except (TypeError, IndexError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f'Invalid link format: {e}')

    if saved is None:
        raise HTTPException(status_code=404, detail='Not found')
    return AssociationsResponse(links=saved)

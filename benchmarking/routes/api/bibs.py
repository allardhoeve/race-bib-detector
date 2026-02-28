"""Bib and association JSON API endpoints."""

import io

from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse

from benchmarking.ground_truth import BibBox
from benchmarking.label_utils import find_hash_by_prefix
from benchmarking.photo_index import load_photo_index
from benchmarking.schemas import (
    AssociationsResponse,
    BibBoxOut,
    BibSuggestionOut,
    GetBibBoxesResponse,
    SaveAssociationsRequest,
    SaveBibBoxesRequest,
)
from benchmarking.services import association_service, bib_service

api_bibs_router = APIRouter()


@api_bibs_router.get('/api/bibs/{content_hash}', response_model=GetBibBoxesResponse)
async def get_bib_boxes(content_hash: str) -> GetBibBoxesResponse:
    """Get bib boxes, suggestions, tags, split, and labeled status."""
    result = bib_service.get_bib_label(content_hash)
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

    try:
        boxes = [BibBox.model_validate(b.model_dump()) for b in request.boxes] if request.boxes is not None else None
        bib_service.save_bib_label(
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
    jpeg_bytes = bib_service.get_bib_crop_jpeg(content_hash, box_index)
    if jpeg_bytes is None:
        raise HTTPException(status_code=404)
    return StreamingResponse(io.BytesIO(jpeg_bytes), media_type='image/jpeg')


@api_bibs_router.get('/api/associations/{content_hash}', response_model=AssociationsResponse)
async def get_associations(content_hash: str) -> AssociationsResponse:
    """Return the bib-face links for a photo."""
    links = association_service.get_associations(content_hash)
    if links is None:
        raise HTTPException(status_code=404, detail='Not found')
    return AssociationsResponse(links=links)


@api_bibs_router.put('/api/associations/{content_hash}', response_model=AssociationsResponse)
async def save_associations(content_hash: str, request: SaveAssociationsRequest) -> AssociationsResponse:
    """Save the bib-face links for a photo. Replaces all existing links."""
    try:
        saved = association_service.set_associations(content_hash, request.links)
    except (TypeError, IndexError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f'Invalid link format: {e}')

    if saved is None:
        raise HTTPException(status_code=404, detail='Not found')
    return AssociationsResponse(links=saved)

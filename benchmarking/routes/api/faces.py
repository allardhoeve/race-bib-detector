"""Face JSON API endpoints."""

import io

from fastapi import APIRouter, Body, HTTPException, Query
from starlette.responses import StreamingResponse

from benchmarking.label_utils import find_hash_by_prefix
from benchmarking.photo_index import load_photo_index
from benchmarking.services import face_service

api_faces_router = APIRouter()


@api_faces_router.get('/api/faces/{content_hash}')
async def get_face_boxes(content_hash: str):
    """Get face boxes, suggestions, and tags."""
    result = face_service.get_face_label(content_hash)
    if result is None:
        raise HTTPException(status_code=404, detail='Photo not found')
    result = dict(result)
    result.pop('full_hash', None)
    return result


@api_faces_router.put('/api/faces/{content_hash}')
async def save_face_label(content_hash: str, body: dict = Body(...)):
    """Save face boxes/tags for a photo label. Replaces all existing data."""
    face_tags = body.get('face_tags', [])

    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        raise HTTPException(status_code=404, detail='Photo not found')

    try:
        face_service.save_face_label(
            content_hash=full_hash,
            boxes_data=body.get('boxes'),
            tags=face_tags,
        )
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {'status': 'ok'}


@api_faces_router.get('/api/faces/{content_hash}/suggestions')
async def face_identity_suggestions(
    content_hash: str,
    box_x: str | None = Query(default=None),
    box_y: str | None = Query(default=None),
    box_w: str | None = Query(default=None),
    box_h: str | None = Query(default=None),
    k: int = Query(default=5),
):
    """Suggest identities for a face box using embedding similarity."""
    try:
        box_x_f = float(box_x)
        box_y_f = float(box_y)
        box_w_f = float(box_w)
        box_h_f = float(box_h)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail='Missing or invalid box_x/box_y/box_w/box_h')

    result = face_service.get_identity_suggestions(content_hash, box_x_f, box_y_f, box_w_f, box_h_f, k=k)
    if result is None:
        raise HTTPException(status_code=404, detail='Photo not found')
    return {'suggestions': result}


@api_faces_router.get('/api/faces/{content_hash}/crop/{box_index}')
async def face_crop(content_hash: str, box_index: int):
    """Return a JPEG crop of a labeled face box."""
    jpeg_bytes = face_service.get_face_crop_jpeg(content_hash, box_index)
    if jpeg_bytes is None:
        raise HTTPException(status_code=404)
    return StreamingResponse(io.BytesIO(jpeg_bytes), media_type='image/jpeg')

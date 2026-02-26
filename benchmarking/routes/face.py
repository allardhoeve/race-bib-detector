"""Face labeling routes."""

import io
import logging
import random

from fastapi import APIRouter, Body, HTTPException, Query, Request
from starlette.responses import RedirectResponse, StreamingResponse

from benchmarking.ground_truth import (
    load_bib_ground_truth,
    load_face_ground_truth,
    ALLOWED_FACE_TAGS,
    FACE_BOX_TAGS,
)
from benchmarking.label_utils import get_filtered_face_hashes, find_hash_by_prefix, find_next_unlabeled_url, is_face_labeled
from benchmarking.photo_index import load_photo_index
from benchmarking.runner import list_runs
from benchmarking.services import face_service
from benchmarking.templates_env import TEMPLATES
from config import ITERATION_SPLIT_PROBABILITY

logger = logging.getLogger(__name__)

face_router = APIRouter()


@face_router.get('/faces/labels/')
async def face_labels_redirect(request: Request):
    """301 shim for backward compatibility."""
    url = str(request.url_for('faces_index'))
    if request.query_params:
        url += '?' + str(request.query_params)
    return RedirectResponse(url=url, status_code=301)


@face_router.get('/faces/labels/{content_hash}')
async def face_label_redirect(content_hash: str, request: Request):
    """301 shim for backward compatibility."""
    url = str(request.url_for('face_photo', content_hash=content_hash))
    if request.query_params:
        url += '?' + str(request.query_params)
    return RedirectResponse(url=url, status_code=301)


@face_router.get('/faces/')
async def faces_index(request: Request, filter_type: str = Query(default='all', alias='filter')):
    """Show first photo for face labeling based on filter."""
    hashes = get_filtered_face_hashes(filter_type)

    if not hashes:
        return TEMPLATES.TemplateResponse(request, 'empty.html')

    url = str(request.url_for('face_photo', content_hash=hashes[0][:8])) + f'?filter={filter_type}'
    return RedirectResponse(url=url, status_code=302)


@face_router.get('/faces/{content_hash}')
async def face_photo(
    content_hash: str,
    request: Request,
    filter_type: str = Query(default='all', alias='filter'),
):
    """Label face count/tags for a specific photo."""
    hashes = get_filtered_face_hashes(filter_type)

    if not hashes:
        return TEMPLATES.TemplateResponse(request, 'empty.html')

    full_hash = find_hash_by_prefix(content_hash, hashes)
    if not full_hash:
        raise HTTPException(status_code=404, detail='Photo not found')

    face_gt = load_face_ground_truth()
    bib_gt = load_bib_ground_truth()
    face_label = face_gt.get_photo(full_hash)
    bib_label = bib_gt.get_photo(full_hash)

    if bib_label:
        default_split = bib_label.split
    else:
        default_split = 'iteration' if random.random() < ITERATION_SPLIT_PROBABILITY else 'full'

    try:
        idx = hashes.index(full_hash)
    except ValueError:
        raise HTTPException(status_code=404, detail='Photo not in current filter')

    total = len(hashes)
    has_prev = idx > 0
    has_next = idx < total - 1

    prev_url = (
        str(request.url_for('face_photo', content_hash=hashes[idx - 1][:8])) + f'?filter={filter_type}'
    ) if has_prev else None
    next_url = (
        str(request.url_for('face_photo', content_hash=hashes[idx + 1][:8])) + f'?filter={filter_type}'
    ) if has_next else None

    all_hashes_sorted = sorted(load_photo_index().keys())

    def _face_is_labeled(h: str) -> bool:
        fl = face_gt.get_photo(h)
        return bool(fl and is_face_labeled(fl))

    next_unlabeled_url = find_next_unlabeled_url(
        full_hash, all_hashes_sorted, _face_is_labeled,
        lambda h: str(request.url_for('face_photo', content_hash=h)) + f'?filter={filter_type}',
    )

    runs = list_runs()
    latest_run_id = runs[0]['run_id'] if runs else None

    return TEMPLATES.TemplateResponse(request, 'face_labeling.html', {
        'content_hash': full_hash,
        'face_count': face_label.face_count if face_label else None,
        'face_tags': face_label.tags if face_label else [],
        'split': default_split,
        'all_face_tags': sorted(ALLOWED_FACE_TAGS),
        'face_box_tags': sorted(FACE_BOX_TAGS),
        'current': idx + 1,
        'total': total,
        'has_prev': has_prev,
        'has_next': has_next,
        'prev_url': prev_url,
        'next_url': next_url,
        'next_unlabeled_url': next_unlabeled_url,
        'filter': filter_type,
        'latest_run_id': latest_run_id,
    })


@face_router.post('/api/face_labels')
async def save_face_label_legacy():
    """Legacy endpoint — gone. Use PUT /api/faces/<hash>."""
    raise HTTPException(status_code=410, detail='Use PUT /api/faces/<hash>')


@face_router.put('/api/faces/{content_hash}')
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


@face_router.get('/api/face_boxes/{content_hash}')
async def get_face_boxes_redirect(content_hash: str, request: Request):
    """308 shim for backward compatibility."""
    return RedirectResponse(
        url=str(request.url_for('get_face_boxes', content_hash=content_hash)),
        status_code=308,
    )


@face_router.get('/api/faces/{content_hash}')
async def get_face_boxes(content_hash: str):
    """Get face boxes, suggestions, and tags."""
    result = face_service.get_face_label(content_hash)
    if result is None:
        raise HTTPException(status_code=404, detail='Photo not found')
    result = dict(result)
    result.pop('full_hash', None)
    return result


@face_router.get('/api/face_identity_suggestions/{content_hash}')
async def face_identity_suggestions_redirect(content_hash: str, request: Request):
    """308 shim for backward compatibility."""
    qs = ('?' + str(request.url.query)) if request.url.query else ''
    return RedirectResponse(
        url=str(request.url_for('face_identity_suggestions', content_hash=content_hash)) + qs,
        status_code=308,
    )


@face_router.get('/api/faces/{content_hash}/suggestions')
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


@face_router.get('/api/face_crop/{content_hash}/{box_index}')
async def face_crop_redirect(content_hash: str, box_index: int, request: Request):
    """308 shim for backward compatibility."""
    return RedirectResponse(
        url=str(request.url_for('face_crop', content_hash=content_hash, box_index=box_index)),
        status_code=308,
    )


@face_router.get('/api/faces/{content_hash}/crop/{box_index}')
async def face_crop(content_hash: str, box_index: int):
    """Return a JPEG crop of a labeled face box."""
    jpeg_bytes = face_service.get_face_crop_jpeg(content_hash, box_index)
    if jpeg_bytes is None:
        raise HTTPException(status_code=404)
    return StreamingResponse(io.BytesIO(jpeg_bytes), media_type='image/jpeg')

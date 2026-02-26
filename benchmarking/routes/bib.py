"""Bib labeling routes."""

import random

from fastapi import APIRouter, Body, HTTPException, Query, Request
from starlette.responses import RedirectResponse

from benchmarking.ground_truth import (
    load_bib_ground_truth,
    ALLOWED_TAGS,
)
from benchmarking.label_utils import get_filtered_hashes, find_hash_by_prefix, find_next_unlabeled_url
from benchmarking.photo_index import load_photo_index
from benchmarking.runner import list_runs
from benchmarking.services import bib_service, association_service
from benchmarking.templates_env import TEMPLATES
from config import ITERATION_SPLIT_PROBABILITY

bib_router = APIRouter()


@bib_router.get('/labels/', include_in_schema=False)
async def labels_index_redirect(request: Request):
    """301 shim for backward compatibility."""
    url = str(request.url_for('bibs_index'))
    if request.query_params:
        url += '?' + str(request.query_params)
    return RedirectResponse(url=url, status_code=301)


@bib_router.get('/bibs/', include_in_schema=False)
async def bibs_index(request: Request, filter_type: str = Query(default='all', alias='filter')):
    """Show first photo based on filter."""
    hashes = get_filtered_hashes(filter_type)

    if not hashes:
        return TEMPLATES.TemplateResponse(request, 'empty.html')

    url = str(request.url_for('bib_photo', content_hash=hashes[0][:8])) + f'?filter={filter_type}'
    return RedirectResponse(url=url, status_code=302)


@bib_router.get('/labels/{content_hash}', include_in_schema=False)
async def labels_photo_redirect(content_hash: str, request: Request):
    """301 shim for backward compatibility."""
    url = str(request.url_for('bib_photo', content_hash=content_hash))
    if request.query_params:
        url += '?' + str(request.query_params)
    return RedirectResponse(url=url, status_code=301)


@bib_router.get('/bibs/{content_hash}', include_in_schema=False)
async def bib_photo(
    content_hash: str,
    request: Request,
    filter_type: str = Query(default='all', alias='filter'),
):
    """Label a specific photo."""
    hashes = get_filtered_hashes(filter_type)

    if not hashes:
        return TEMPLATES.TemplateResponse(request, 'empty.html')

    full_hash = find_hash_by_prefix(content_hash, hashes)
    if not full_hash:
        raise HTTPException(status_code=404, detail='Photo not found')

    bib_gt = load_bib_ground_truth()
    label = bib_gt.get_photo(full_hash)

    if label:
        default_split = label.split
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
        str(request.url_for('bib_photo', content_hash=hashes[idx - 1][:8])) + f'?filter={filter_type}'
    ) if has_prev else None
    next_url = (
        str(request.url_for('bib_photo', content_hash=hashes[idx + 1][:8])) + f'?filter={filter_type}'
    ) if has_next else None

    all_hashes_sorted = sorted(load_photo_index().keys())

    def _bib_is_labeled(h: str) -> bool:
        lbl = bib_gt.get_photo(h)
        return bool(lbl and lbl.labeled)

    next_unlabeled_url = find_next_unlabeled_url(
        full_hash, all_hashes_sorted, _bib_is_labeled,
        lambda h: str(request.url_for('bib_photo', content_hash=h)) + f'?filter={filter_type}',
    )

    runs = list_runs()
    latest_run_id = runs[0]['run_id'] if runs else None

    return TEMPLATES.TemplateResponse(request, 'labeling.html', {
        'content_hash': full_hash,
        'bibs_str': ', '.join(str(b) for b in label.bibs) if label else '',
        'tags': label.tags if label else [],
        'split': default_split,
        'all_tags': sorted(ALLOWED_TAGS),
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


@bib_router.post('/api/labels', include_in_schema=False)
async def save_label_legacy():
    """Legacy endpoint — gone. Use PUT /api/bibs/<hash>."""
    raise HTTPException(status_code=410, detail='Use PUT /api/bibs/<hash>')


@bib_router.put('/api/bibs/{content_hash}')
async def save_bib_label(content_hash: str, body: dict = Body(...)):
    """Save bib boxes + tags + split for a photo. Replaces all existing data."""
    tags = body.get('tags', [])
    split = body.get('split', 'full')

    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        raise HTTPException(status_code=404, detail='Photo not found')

    try:
        bib_service.save_bib_label(
            content_hash=full_hash,
            boxes_data=body.get('boxes'),
            bibs_legacy=body.get('bibs'),
            tags=tags,
            split=split,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {'status': 'ok'}


@bib_router.get('/links/', include_in_schema=False)
async def links_index_redirect(request: Request):
    """301 shim for backward compatibility."""
    return RedirectResponse(url=str(request.url_for('associations_index')), status_code=301)


@bib_router.get('/associations/', include_in_schema=False)
async def associations_index(request: Request):
    """Show first photo for link labeling."""
    index = load_photo_index()
    hashes = sorted(index.keys())
    if not hashes:
        return TEMPLATES.TemplateResponse(request, 'empty.html')
    return RedirectResponse(
        url=str(request.url_for('association_photo', content_hash=hashes[0][:8])),
        status_code=302,
    )


@bib_router.get('/links/{content_hash}', include_in_schema=False)
async def links_photo_redirect(content_hash: str, request: Request):
    """301 shim for backward compatibility."""
    return RedirectResponse(
        url=str(request.url_for('association_photo', content_hash=content_hash)),
        status_code=301,
    )


@bib_router.get('/associations/{content_hash}', include_in_schema=False)
async def association_photo(content_hash: str, request: Request):
    """Link labeling page: associate bib boxes with face boxes."""
    from benchmarking.ground_truth import (
        load_bib_ground_truth, load_face_ground_truth, load_link_ground_truth,
    )
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        raise HTTPException(status_code=404, detail='Photo not found')

    photo_paths = index[full_hash]
    photo_path = photo_paths[0] if isinstance(photo_paths, list) else photo_paths

    bib_gt = load_bib_ground_truth()
    face_gt = load_face_ground_truth()
    link_gt = load_link_ground_truth()

    bib_label = bib_gt.get_photo(full_hash)
    face_label = face_gt.get_photo(full_hash)
    link_label = link_gt.get_links(full_hash)
    is_processed = full_hash in link_gt.photos

    bib_boxes = [b.model_dump() for b in bib_label.boxes] if bib_label else []
    face_boxes = [b.model_dump() for b in face_label.boxes] if face_label else []
    links = [lnk.to_pair() for lnk in link_label]

    all_hashes = sorted(index.keys())
    try:
        idx = all_hashes.index(full_hash)
    except ValueError:
        raise HTTPException(status_code=404, detail='Photo not in index')

    total = len(all_hashes)
    prev_url = str(request.url_for('association_photo', content_hash=all_hashes[idx - 1][:8])) if idx > 0 else None
    next_url = str(request.url_for('association_photo', content_hash=all_hashes[idx + 1][:8])) if idx < total - 1 else None

    next_unlabeled_url = None
    for h in all_hashes[idx + 1:]:
        if h not in link_gt.photos:
            next_unlabeled_url = str(request.url_for('association_photo', content_hash=h[:8]))
            break

    return TEMPLATES.TemplateResponse(request, 'link_labeling.html', {
        'content_hash': full_hash,
        'photo_path': photo_path,
        'bib_boxes': bib_boxes,
        'face_boxes': face_boxes,
        'links': links,
        'is_processed': is_processed,
        'current': idx + 1,
        'total': total,
        'prev_url': prev_url,
        'next_url': next_url,
        'next_unlabeled_url': next_unlabeled_url,
    })


@bib_router.get('/api/bib_face_links/{content_hash}', include_in_schema=False)
async def get_bib_face_links_redirect(content_hash: str, request: Request):
    """308 shim for backward compatibility."""
    return RedirectResponse(
        url=str(request.url_for('get_associations', content_hash=content_hash)),
        status_code=308,
    )


@bib_router.put('/api/bib_face_links/{content_hash}', include_in_schema=False)
async def save_bib_face_links_redirect(content_hash: str, request: Request):
    """308 shim for backward compatibility."""
    return RedirectResponse(
        url=str(request.url_for('save_associations', content_hash=content_hash)),
        status_code=308,
    )


@bib_router.get('/api/associations/{content_hash}')
async def get_associations(content_hash: str):
    """Return the bib-face links for a photo."""
    links = association_service.get_associations(content_hash)
    if links is None:
        raise HTTPException(status_code=404, detail='Not found')
    return {'links': links}


@bib_router.put('/api/associations/{content_hash}')
async def save_associations(content_hash: str, body: dict = Body(...)):
    """Save the bib-face links for a photo. Replaces all existing links."""
    try:
        saved = association_service.set_associations(content_hash, body.get("links", []))
    except (TypeError, IndexError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f'Invalid link format: {e}')

    if saved is None:
        raise HTTPException(status_code=404, detail='Not found')
    return {'status': 'ok', 'links': saved}


@bib_router.get('/api/bib_boxes/{content_hash}', include_in_schema=False)
async def get_bib_boxes_redirect(content_hash: str, request: Request):
    """308 shim for backward compatibility."""
    return RedirectResponse(
        url=str(request.url_for('get_bib_boxes', content_hash=content_hash)),
        status_code=308,
    )


@bib_router.get('/api/bibs/{content_hash}')
async def get_bib_boxes(content_hash: str):
    """Get bib boxes, suggestions, tags, split, and labeled status."""
    result = bib_service.get_bib_label(content_hash)
    if result is None:
        raise HTTPException(status_code=404, detail='Photo not found')
    result = dict(result)
    result.pop('full_hash', None)
    return result

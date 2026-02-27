"""Bib, face, and association labeling HTML views."""

import random

from fastapi import APIRouter, HTTPException, Query, Request
from starlette.responses import RedirectResponse

from benchmarking.ground_truth import (
    ALLOWED_FACE_TAGS,
    ALLOWED_TAGS,
    FACE_BOX_TAGS,
    load_bib_ground_truth,
    load_face_ground_truth,
)
from benchmarking.label_utils import (
    find_hash_by_prefix,
    find_next_unlabeled_url,
    get_filtered_face_hashes,
    get_filtered_hashes,
    is_face_labeled,
)
from benchmarking.services.completion_service import (
    get_link_ready_hashes,
    get_unlinked_hashes,
    workflow_context_for,
)
from benchmarking.photo_index import load_photo_index
from benchmarking.runner import list_runs
from benchmarking.templates_env import TEMPLATES
from config import ITERATION_SPLIT_PROBABILITY

ui_labeling_router = APIRouter()


# ---- BIB LABELING --------------------------------------------------------

@ui_labeling_router.get('/bibs/')
async def bibs_index(request: Request, filter_type: str = Query(default='all', alias='filter')):
    """Show first photo based on filter."""
    hashes = get_filtered_hashes(filter_type)

    if not hashes:
        return TEMPLATES.TemplateResponse(request, 'empty.html')

    url = str(request.url_for('bib_photo', content_hash=hashes[0][:8])) + f'?filter={filter_type}'
    return RedirectResponse(url=url, status_code=302)


@ui_labeling_router.get('/bibs/{content_hash}')
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
        'workflow': workflow_context_for(full_hash, 'bibs'),
    })


# ---- FACE LABELING -------------------------------------------------------

@ui_labeling_router.get('/faces/')
async def faces_index(request: Request, filter_type: str = Query(default='all', alias='filter')):
    """Show first photo for face labeling based on filter."""
    hashes = get_filtered_face_hashes(filter_type)

    if not hashes:
        return TEMPLATES.TemplateResponse(request, 'empty.html')

    url = str(request.url_for('face_photo', content_hash=hashes[0][:8])) + f'?filter={filter_type}'
    return RedirectResponse(url=url, status_code=302)


@ui_labeling_router.get('/faces/{content_hash}')
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
        'workflow': workflow_context_for(full_hash, 'faces'),
    })


# ---- ASSOCIATION LABELING ------------------------------------------------

@ui_labeling_router.get('/associations/')
async def associations_index(request: Request):
    """Show first photo for link labeling."""
    hashes = get_link_ready_hashes()
    if not hashes:
        return TEMPLATES.TemplateResponse(request, 'empty.html')
    return RedirectResponse(
        url=str(request.url_for('association_photo', content_hash=hashes[0][:8])),
        status_code=302,
    )


@ui_labeling_router.get('/associations/{content_hash}')
async def association_photo(content_hash: str, request: Request):
    """Link labeling page: associate bib boxes with face boxes."""
    from benchmarking.ground_truth import load_link_ground_truth

    all_hashes = get_link_ready_hashes()
    full_hash = find_hash_by_prefix(content_hash, all_hashes)
    if not full_hash:
        raise HTTPException(status_code=404, detail='Photo not found or not ready for linking')

    index = load_photo_index()
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

    try:
        idx = all_hashes.index(full_hash)
    except ValueError:
        raise HTTPException(status_code=404, detail='Photo not in link-ready list')

    total = len(all_hashes)
    prev_url = str(request.url_for('association_photo', content_hash=all_hashes[idx - 1][:8])) if idx > 0 else None
    next_url = str(request.url_for('association_photo', content_hash=all_hashes[idx + 1][:8])) if idx < total - 1 else None

    unlinked = get_unlinked_hashes()
    next_unlabeled_url = None
    for h in unlinked:
        if h > full_hash:
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
        'workflow': workflow_context_for(full_hash, 'links'),
    })

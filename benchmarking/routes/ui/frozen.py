"""Read-only frozen set viewer routes."""

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import RedirectResponse

from benchmarking.ground_truth import (
    load_bib_ground_truth,
    load_face_ground_truth,
    load_link_ground_truth,
)
from benchmarking.label_utils import find_hash_by_prefix
from benchmarking.sets import BenchmarkSnapshot, list_snapshots
from benchmarking.templates_env import TEMPLATES

ui_frozen_router = APIRouter()


@ui_frozen_router.get('/frozen/')
async def frozen_sets_list(request: Request):
    """List all frozen sets with metadata."""
    snapshots = list_snapshots()
    return TEMPLATES.TemplateResponse(request, 'frozen_set_list.html', {
        'snapshots': snapshots,
    })


@ui_frozen_router.get('/frozen/{set_name}/')
async def frozen_set_photos(request: Request, set_name: str):
    """Thumbnail grid of photos in a frozen set."""
    try:
        snapshot = BenchmarkSnapshot.load(set_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Frozen set '{set_name}' not found")

    return TEMPLATES.TemplateResponse(request, 'frozen_set_photos.html', {
        'snapshot': snapshot,
        'set_name': set_name,
    })


@ui_frozen_router.get('/frozen/{set_name}/{content_hash}')
async def frozen_photo_detail(request: Request, set_name: str, content_hash: str):
    """Read-only composite view: faces, bibs, links all rendered."""
    try:
        snapshot = BenchmarkSnapshot.load(set_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Frozen set '{set_name}' not found")

    full_hash = find_hash_by_prefix(content_hash, snapshot.hashes)
    if not full_hash:
        raise HTTPException(status_code=404, detail='Photo not in this frozen set')

    bib_gt = load_bib_ground_truth()
    face_gt = load_face_ground_truth()
    link_gt = load_link_ground_truth()

    bib_label = bib_gt.get_photo(full_hash)
    face_label = face_gt.get_photo(full_hash)
    link_label = link_gt.get_links(full_hash)

    bib_boxes = [b.model_dump() for b in bib_label.boxes] if bib_label else []
    face_boxes = [b.model_dump() for b in face_label.boxes] if face_label else []
    links = [lnk.to_pair() for lnk in link_label]

    # Navigation within the frozen set
    try:
        idx = snapshot.hashes.index(full_hash)
    except ValueError:
        idx = 0
    total = len(snapshot.hashes)

    prev_url = (
        str(request.url_for('frozen_photo_detail', set_name=set_name, content_hash=snapshot.hashes[idx - 1][:8]))
    ) if idx > 0 else None
    next_url = (
        str(request.url_for('frozen_photo_detail', set_name=set_name, content_hash=snapshot.hashes[idx + 1][:8]))
    ) if idx < total - 1 else None

    return TEMPLATES.TemplateResponse(request, 'frozen_photo_detail.html', {
        'content_hash': full_hash,
        'set_name': set_name,
        'bib_boxes': bib_boxes,
        'face_boxes': face_boxes,
        'links': links,
        'current': idx + 1,
        'total': total,
        'prev_url': prev_url,
        'next_url': next_url,
    })

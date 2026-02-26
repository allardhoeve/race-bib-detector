"""Face labeling routes."""

import io
import logging
import random
from pathlib import Path

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, abort, send_file

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
from config import ITERATION_SPLIT_PROBABILITY

logger = logging.getLogger(__name__)

face_bp = Blueprint('face', __name__)


@face_bp.route('/faces/labels/')
def face_labels_redirect():
    """301 shim for backward compatibility."""
    return redirect(url_for('face.faces_index', **request.args), 301)


@face_bp.route('/faces/labels/<content_hash>')
def face_label_redirect(content_hash):
    """301 shim for backward compatibility."""
    return redirect(url_for('face.face_photo', content_hash=content_hash, **request.args), 301)


@face_bp.route('/faces/')
def faces_index():
    """Show first photo for face labeling based on filter."""
    filter_type = request.args.get('filter', 'all')
    hashes = get_filtered_face_hashes(filter_type)

    if not hashes:
        return render_template('empty.html')

    return redirect(url_for('face.face_photo', content_hash=hashes[0][:8], filter=filter_type))


@face_bp.route('/faces/<content_hash>')
def face_photo(content_hash):
    """Label face count/tags for a specific photo."""
    filter_type = request.args.get('filter', 'all')
    hashes = get_filtered_face_hashes(filter_type)

    if not hashes:
        return render_template('empty.html')

    full_hash = find_hash_by_prefix(content_hash, hashes)
    if not full_hash:
        return "Photo not found", 404

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
        return "Photo not in current filter", 404

    total = len(hashes)
    has_prev = idx > 0
    has_next = idx < total - 1

    prev_url = url_for('face.face_photo', content_hash=hashes[idx - 1][:8], filter=filter_type) if has_prev else None
    next_url = url_for('face.face_photo', content_hash=hashes[idx + 1][:8], filter=filter_type) if has_next else None

    # Find next unlabeled photo (in full sorted list, starting after current)
    all_hashes_sorted = sorted(load_photo_index().keys())
    def _face_is_labeled(h: str) -> bool:
        fl = face_gt.get_photo(h)
        return bool(fl and is_face_labeled(fl))
    next_unlabeled_url = find_next_unlabeled_url(
        full_hash, all_hashes_sorted, _face_is_labeled, 'face.face_photo', filter_type
    )

    runs = list_runs()
    latest_run_id = runs[0]['run_id'] if runs else None

    return render_template(
        'face_labeling.html',
        content_hash=full_hash,
        face_count=face_label.face_count if face_label else None,
        face_tags=face_label.tags if face_label else [],
        split=default_split,
        all_face_tags=sorted(ALLOWED_FACE_TAGS),
        face_box_tags=sorted(FACE_BOX_TAGS),
        current=idx + 1,
        total=total,
        has_prev=has_prev,
        has_next=has_next,
        prev_url=prev_url,
        next_url=next_url,
        next_unlabeled_url=next_unlabeled_url,
        filter=filter_type,
        latest_run_id=latest_run_id,
    )


@face_bp.route('/api/face_labels', methods=['POST'])
def save_face_label_legacy():
    """Legacy endpoint — gone. Use PUT /api/faces/<hash>."""
    return jsonify({'error': 'Use PUT /api/faces/<hash>'}), 410


@face_bp.route('/api/faces/<content_hash>', methods=['PUT'])
def save_face_label(content_hash):
    """Save face boxes/tags for a photo label. Replaces all existing data.

    Accepts ``boxes`` (list of {x,y,w,h,scope,identity} dicts) or
    falls back to empty boxes for backward compatibility.
    """
    data = request.get_json()
    face_tags = data.get('face_tags', [])

    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return jsonify({'error': 'Photo not found'}), 404

    try:
        face_service.save_face_label(
            content_hash=full_hash,
            boxes_data=data.get('boxes'),
            tags=face_tags,
        )
    except (ValueError, TypeError) as e:
        return jsonify({'error': str(e)}), 400

    return jsonify({'status': 'ok'})


@face_bp.route('/api/face_boxes/<content_hash>')
def get_face_boxes_redirect(content_hash):
    """308 shim for backward compatibility."""
    return redirect(url_for('face.get_face_boxes', content_hash=content_hash), 308)


@face_bp.route('/api/faces/<content_hash>', methods=['GET'])
def get_face_boxes(content_hash):
    """Get face boxes, suggestions, and tags."""
    result = face_service.get_face_label(content_hash)
    if result is None:
        return jsonify({'error': 'Photo not found'}), 404
    result = dict(result)
    result.pop('full_hash', None)
    return jsonify(result)


@face_bp.route('/api/face_identity_suggestions/<content_hash>')
def face_identity_suggestions_redirect(content_hash):
    """308 shim for backward compatibility."""
    qs = ('?' + request.query_string.decode()) if request.query_string else ''
    return redirect(url_for('face.face_identity_suggestions', content_hash=content_hash) + qs, 308)


@face_bp.route('/api/faces/<content_hash>/suggestions')
def face_identity_suggestions(content_hash):
    """Suggest identities for a face box using embedding similarity."""
    try:
        box_x = float(request.args['box_x'])
        box_y = float(request.args['box_y'])
        box_w = float(request.args['box_w'])
        box_h = float(request.args['box_h'])
    except (KeyError, ValueError):
        return jsonify({'error': 'Missing or invalid box_x/box_y/box_w/box_h'}), 400

    k = request.args.get('k', 5, type=int)

    result = face_service.get_identity_suggestions(content_hash, box_x, box_y, box_w, box_h, k=k)
    if result is None:
        return jsonify({'error': 'Photo not found'}), 404
    return jsonify({'suggestions': result})


@face_bp.route('/api/face_crop/<content_hash>/<int:box_index>')
def face_crop_redirect(content_hash, box_index):
    """308 shim for backward compatibility."""
    return redirect(url_for('face.face_crop', content_hash=content_hash, box_index=box_index), 308)


@face_bp.route('/api/faces/<content_hash>/crop/<int:box_index>')
def face_crop(content_hash, box_index):
    """Return a JPEG crop of a labeled face box."""
    jpeg_bytes = face_service.get_face_crop_jpeg(content_hash, box_index)
    if jpeg_bytes is None:
        abort(404)
    return send_file(io.BytesIO(jpeg_bytes), mimetype='image/jpeg')

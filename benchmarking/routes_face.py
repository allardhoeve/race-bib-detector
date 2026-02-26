"""Face labeling routes."""

import io
import logging
import random
from pathlib import Path

import cv2
import numpy as np
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, abort, send_file

from benchmarking.face_embeddings import build_embedding_index, find_top_k, EmbeddingIndex
from benchmarking.ghost import load_suggestion_store
from benchmarking.ground_truth import (
    FaceBox,
    FacePhotoLabel,
    load_bib_ground_truth,
    load_face_ground_truth,
    save_face_ground_truth,
    ALLOWED_FACE_TAGS,
    FACE_BOX_TAGS,
)
from benchmarking.identities import load_identities, add_identity, rename_identity
from benchmarking.label_utils import get_filtered_face_hashes, find_hash_by_prefix, find_next_unlabeled_url, is_face_labeled
from benchmarking.photo_index import load_photo_index, get_path_for_hash
from benchmarking.runner import list_runs
from config import ITERATION_SPLIT_PROBABILITY

logger = logging.getLogger(__name__)

PHOTOS_DIR = Path(__file__).parent.parent / "photos"

# Module-level cache for the embedding index. Reset only on process restart.
# Tests that need a fresh index should call `_embedding_index_cache.clear()`.
_embedding_index_cache: dict[str, EmbeddingIndex] = {}


def _get_embedding_index() -> EmbeddingIndex | None:
    """Build or return cached embedding index. Returns None on failure."""
    if 'index' not in _embedding_index_cache:
        try:
            from faces.embedder import get_face_embedder
            embedder = get_face_embedder()
            face_gt = load_face_ground_truth()
            index = load_photo_index()
            _embedding_index_cache['index'] = build_embedding_index(
                face_gt, PHOTOS_DIR, index, embedder
            )
            logger.info("Built embedding index: %d faces", _embedding_index_cache['index'].size)
        except Exception as e:
            logger.exception("Failed to build embedding index: %s", e)
            return None
    return _embedding_index_cache['index']


def _load_image_rgb(photo_path: Path):
    """Load a photo file and return an RGB numpy array, or None on failure."""
    image_data = photo_path.read_bytes()
    arr = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        return None
    return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)


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
def save_face_label():
    """Save face boxes/tags for a photo label.

    Accepts ``boxes`` (list of {x,y,w,h,scope,identity} dicts) or
    falls back to empty boxes for backward compatibility.
    """
    data = request.get_json()

    content_hash = data.get('content_hash')
    face_tags = data.get('face_tags', [])

    if not content_hash:
        return jsonify({'error': 'Missing content_hash'}), 400

    try:
        face_gt = load_face_ground_truth()
        if 'boxes' in data:
            boxes = [FaceBox.from_dict(b) for b in data['boxes']]
        else:
            boxes = []
        label = FacePhotoLabel(
            content_hash=content_hash,
            boxes=boxes,
            tags=face_tags,
        )
    except (ValueError, TypeError) as e:
        return jsonify({'error': str(e)}), 400

    face_gt.add_photo(label)
    save_face_ground_truth(face_gt)

    return jsonify({'status': 'ok'})


@face_bp.route('/api/face_boxes/<content_hash>')
def get_face_boxes(content_hash):
    """Get face boxes, suggestions, and tags."""
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return jsonify({'error': 'Photo not found'}), 404

    face_gt = load_face_ground_truth()
    label = face_gt.get_photo(full_hash)

    store = load_suggestion_store()
    photo_sugg = store.get(full_hash)
    suggestions = [s.to_dict() for s in photo_sugg.faces] if photo_sugg else []

    if label:
        return jsonify({
            'boxes': [b.to_dict() for b in label.boxes],
            'suggestions': suggestions,
            'tags': label.tags,
        })
    else:
        return jsonify({
            'boxes': [],
            'suggestions': suggestions,
            'tags': [],
        })


@face_bp.route('/api/identities')
def get_identities():
    return jsonify({'identities': load_identities()})


@face_bp.route('/api/identities', methods=['POST'])
def post_identity():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Missing name'}), 400
    ids = add_identity(name)
    return jsonify({'identities': ids})


@face_bp.route('/api/rename_identity', methods=['POST'])
def rename_identity_api():
    """Rename an identity across all face GT entries and the identities list."""
    data = request.get_json() or {}
    old_name = (data.get('old_name') or '').strip()
    new_name = (data.get('new_name') or '').strip()

    if not old_name or not new_name:
        return jsonify({'error': 'Missing old_name or new_name'}), 400
    if old_name == new_name:
        return jsonify({'error': 'old_name and new_name are the same'}), 400

    # Update face ground truth boxes
    face_gt = load_face_ground_truth()
    updated_count = 0
    for label in face_gt.photos.values():
        for box in label.boxes:
            if box.identity == old_name:
                box.identity = new_name
                updated_count += 1
    save_face_ground_truth(face_gt)

    # Update identities list
    ids = rename_identity(old_name, new_name)

    return jsonify({'updated_count': updated_count, 'identities': ids})


@face_bp.route('/api/face_identity_suggestions/<content_hash>')
def face_identity_suggestions(content_hash):
    """Suggest identities for a face box using embedding similarity."""
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return jsonify({'error': 'Photo not found'}), 404

    try:
        box_x = float(request.args['box_x'])
        box_y = float(request.args['box_y'])
        box_w = float(request.args['box_w'])
        box_h = float(request.args['box_h'])
    except (KeyError, ValueError):
        return jsonify({'error': 'Missing or invalid box_x/box_y/box_w/box_h'}), 400

    k = request.args.get('k', 5, type=int)

    emb_index = _get_embedding_index()
    if emb_index is None or emb_index.size == 0:
        return jsonify({'suggestions': []})

    photo_path = get_path_for_hash(full_hash, PHOTOS_DIR, index)
    if not photo_path or not photo_path.exists():
        return jsonify({'error': 'Photo file not found'}), 404

    image_rgb = _load_image_rgb(photo_path)
    if image_rgb is None:
        return jsonify({'error': 'Failed to decode image'}), 500

    h, w = image_rgb.shape[:2]
    from geometry import rect_to_bbox
    bbox = rect_to_bbox(int(box_x * w), int(box_y * h), int(box_w * w), int(box_h * h))

    from faces.embedder import get_face_embedder
    embeddings = get_face_embedder().embed(image_rgb, [bbox])
    if not embeddings:
        return jsonify({'suggestions': []})

    matches = find_top_k(embeddings[0], emb_index, k=k)
    return jsonify({'suggestions': [m.to_dict() for m in matches]})


@face_bp.route('/api/face_crop/<content_hash>/<int:box_index>')
def face_crop(content_hash, box_index):
    """Return a JPEG crop of a labeled face box."""
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        abort(404)

    face_gt = load_face_ground_truth()
    label = face_gt.get_photo(full_hash)
    if not label or box_index < 0 or box_index >= len(label.boxes):
        abort(404)

    box = label.boxes[box_index]
    if not box.has_coords:
        abort(404)

    photo_path = get_path_for_hash(full_hash, PHOTOS_DIR, index)
    if not photo_path or not photo_path.exists():
        abort(404)

    from PIL import Image

    with Image.open(photo_path) as img:
        w, h = img.size
        left = int(box.x * w)
        upper = int(box.y * h)
        right = int((box.x + box.w) * w)
        lower = int((box.y + box.h) * h)
        crop = img.crop((left, upper, right, lower))

    buf = io.BytesIO()
    crop.save(buf, format='JPEG', quality=85)
    buf.seek(0)
    return send_file(buf, mimetype='image/jpeg')

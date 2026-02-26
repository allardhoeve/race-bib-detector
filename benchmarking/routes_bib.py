"""Bib labeling routes."""

import random

from flask import Blueprint, render_template, request, jsonify, redirect, url_for

from benchmarking.ground_truth import (
    BibBox,
    BibPhotoLabel,
    load_bib_ground_truth,
    save_bib_ground_truth,
    ALLOWED_TAGS,
)
from benchmarking.ghost import load_suggestion_store
from benchmarking.label_utils import get_filtered_hashes, find_hash_by_prefix, find_next_unlabeled_url
from benchmarking.photo_index import load_photo_index
from benchmarking.runner import list_runs
from config import ITERATION_SPLIT_PROBABILITY

bib_bp = Blueprint('bib', __name__)


@bib_bp.route('/labels/')
def labels_index_redirect():
    """301 shim for backward compatibility."""
    return redirect(url_for('bib.bibs_index', **request.args), 301)


@bib_bp.route('/bibs/')
def bibs_index():
    """Show first photo based on filter."""
    filter_type = request.args.get('filter', 'all')
    hashes = get_filtered_hashes(filter_type)

    if not hashes:
        return render_template('empty.html')

    return redirect(url_for('bib.bib_photo', content_hash=hashes[0][:8], filter=filter_type))


@bib_bp.route('/labels/<content_hash>')
def labels_photo_redirect(content_hash):
    """301 shim for backward compatibility."""
    return redirect(url_for('bib.bib_photo', content_hash=content_hash, **request.args), 301)


@bib_bp.route('/bibs/<content_hash>')
def bib_photo(content_hash):
    """Label a specific photo."""
    filter_type = request.args.get('filter', 'all')
    hashes = get_filtered_hashes(filter_type)

    if not hashes:
        return render_template('empty.html')

    full_hash = find_hash_by_prefix(content_hash, hashes)
    if not full_hash:
        return "Photo not found", 404

    bib_gt = load_bib_ground_truth()
    label = bib_gt.get_photo(full_hash)

    if label:
        default_split = label.split
    else:
        default_split = 'iteration' if random.random() < ITERATION_SPLIT_PROBABILITY else 'full'

    try:
        idx = hashes.index(full_hash)
    except ValueError:
        return "Photo not in current filter", 404

    total = len(hashes)
    has_prev = idx > 0
    has_next = idx < total - 1

    prev_url = url_for('bib.bib_photo', content_hash=hashes[idx - 1][:8], filter=filter_type) if has_prev else None
    next_url = url_for('bib.bib_photo', content_hash=hashes[idx + 1][:8], filter=filter_type) if has_next else None

    # Find next unlabeled photo (in full sorted list, starting after current)
    all_hashes_sorted = sorted(load_photo_index().keys())
    def _bib_is_labeled(h: str) -> bool:
        lbl = bib_gt.get_photo(h)
        return bool(lbl and lbl.labeled)
    next_unlabeled_url = find_next_unlabeled_url(
        full_hash, all_hashes_sorted, _bib_is_labeled, 'bib.bib_photo', filter_type
    )

    # Get latest run ID for inspector link
    runs = list_runs()
    latest_run_id = runs[0]['run_id'] if runs else None

    return render_template(
        'labeling.html',
        content_hash=full_hash,
        bibs_str=', '.join(str(b) for b in label.bibs) if label else '',
        tags=label.tags if label else [],
        split=default_split,
        all_tags=sorted(ALLOWED_TAGS),
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


@bib_bp.route('/api/labels', methods=['POST'])
def save_label_legacy():
    """Legacy endpoint — gone. Use PUT /api/bibs/<hash>."""
    return jsonify({'error': 'Use PUT /api/bibs/<hash>'}), 410


@bib_bp.route('/api/bibs/<content_hash>', methods=['PUT'])
def save_bib_label(content_hash):
    """Save bib boxes + tags + split for a photo. Replaces all existing data.

    Accepts either ``boxes`` (list of {x,y,w,h,number,scope} dicts) or
    the legacy ``bibs`` (list of ints) for backward compatibility.
    """
    data = request.get_json()
    tags = data.get('tags', [])
    split = data.get('split', 'full')

    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return jsonify({'error': 'Photo not found'}), 404

    try:
        bib_gt = load_bib_ground_truth()
        if 'boxes' in data:
            boxes = [BibBox.from_dict(b) for b in data['boxes']]
        else:
            bibs = data.get('bibs', [])
            boxes = [BibBox(x=0, y=0, w=0, h=0, number=str(b), scope="bib") for b in bibs]
        label = BibPhotoLabel(
            content_hash=full_hash,
            boxes=boxes,
            tags=tags,
            split=split,
            labeled=True,
        )
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    bib_gt.add_photo(label)
    save_bib_ground_truth(bib_gt)

    return jsonify({'status': 'ok'})


@bib_bp.route('/links/')
def links_index_redirect():
    """301 shim for backward compatibility."""
    return redirect(url_for('bib.associations_index'), 301)


@bib_bp.route('/associations/')
def associations_index():
    """Show first photo for link labeling."""
    index = load_photo_index()
    hashes = sorted(index.keys())
    if not hashes:
        return render_template('empty.html')
    return redirect(url_for('bib.association_photo', content_hash=hashes[0][:8]))


@bib_bp.route('/links/<content_hash>')
def links_photo_redirect(content_hash):
    """301 shim for backward compatibility."""
    return redirect(url_for('bib.association_photo', content_hash=content_hash), 301)


@bib_bp.route('/associations/<content_hash>')
def association_photo(content_hash):
    """Link labeling page: associate bib boxes with face boxes."""
    from benchmarking.ground_truth import (
        load_bib_ground_truth, load_face_ground_truth, load_link_ground_truth,
    )
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return "Photo not found", 404

    photo_paths = index[full_hash]
    photo_path = photo_paths[0] if isinstance(photo_paths, list) else photo_paths

    bib_gt = load_bib_ground_truth()
    face_gt = load_face_ground_truth()
    link_gt = load_link_ground_truth()

    bib_label = bib_gt.get_photo(full_hash)
    face_label = face_gt.get_photo(full_hash)
    link_label = link_gt.get_links(full_hash)
    is_processed = full_hash in link_gt.photos

    bib_boxes = [b.to_dict() for b in bib_label.boxes] if bib_label else []
    face_boxes = [b.to_dict() for b in face_label.boxes] if face_label else []
    links = [lnk.to_pair() for lnk in link_label]

    all_hashes = sorted(index.keys())
    try:
        idx = all_hashes.index(full_hash)
    except ValueError:
        return "Photo not in index", 404

    total = len(all_hashes)
    prev_url = url_for('bib.association_photo', content_hash=all_hashes[idx - 1][:8]) if idx > 0 else None
    next_url = url_for('bib.association_photo', content_hash=all_hashes[idx + 1][:8]) if idx < total - 1 else None

    next_unlabeled_url = None
    for h in all_hashes[idx + 1:]:
        if h not in link_gt.photos:
            next_unlabeled_url = url_for('bib.association_photo', content_hash=h[:8])
            break

    return render_template(
        'link_labeling.html',
        content_hash=full_hash,
        photo_path=photo_path,
        bib_boxes=bib_boxes,
        face_boxes=face_boxes,
        links=links,
        is_processed=is_processed,
        current=idx + 1,
        total=total,
        prev_url=prev_url,
        next_url=next_url,
        next_unlabeled_url=next_unlabeled_url,
    )


@bib_bp.route('/api/bib_face_links/<content_hash>', methods=['GET'])
def get_bib_face_links_redirect(content_hash):
    """308 shim for backward compatibility."""
    return redirect(url_for('bib.get_associations', content_hash=content_hash), 308)


@bib_bp.route('/api/bib_face_links/<content_hash>', methods=['PUT'])
def save_bib_face_links_redirect(content_hash):
    """308 shim for backward compatibility."""
    return redirect(url_for('bib.save_associations', content_hash=content_hash), 308)


@bib_bp.route('/api/associations/<content_hash>', methods=['GET'])
def get_associations(content_hash):
    """Return the bib-face links for a photo.

    Response: {"links": [[bib_index, face_index], ...]}
    """
    from benchmarking.ground_truth import load_link_ground_truth
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return jsonify({"error": "Not found"}), 404
    link_gt = load_link_ground_truth()
    links = link_gt.get_links(full_hash)
    return jsonify({"links": [lnk.to_pair() for lnk in links]})


@bib_bp.route('/api/associations/<content_hash>', methods=['PUT'])
def save_associations(content_hash):
    """Save the bib-face links for a photo. Replaces all existing links.

    Request body: {"links": [[bib_index, face_index], ...]}
    Response: {"status": "ok", "links": [[bib_index, face_index], ...]}
    """
    from benchmarking.ground_truth import (
        BibFaceLink, load_link_ground_truth, save_link_ground_truth,
    )
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json()
    if data is None:
        return jsonify({"error": "Invalid JSON"}), 400

    raw_links = data.get("links", [])
    try:
        links = [BibFaceLink.from_pair(pair) for pair in raw_links]
    except (TypeError, IndexError, ValueError) as e:
        return jsonify({"error": f"Invalid link format: {e}"}), 400

    link_gt = load_link_ground_truth()
    link_gt.set_links(full_hash, links)
    save_link_ground_truth(link_gt)
    return jsonify({"status": "ok", "links": [lnk.to_pair() for lnk in links]})


@bib_bp.route('/api/bib_boxes/<content_hash>')
def get_bib_boxes_redirect(content_hash):
    """308 shim for backward compatibility."""
    return redirect(url_for('bib.get_bib_boxes', content_hash=content_hash), 308)


@bib_bp.route('/api/bibs/<content_hash>', methods=['GET'])
def get_bib_boxes(content_hash):
    """Get bib boxes, suggestions, tags, split, and labeled status."""
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return jsonify({'error': 'Photo not found'}), 404

    bib_gt = load_bib_ground_truth()
    label = bib_gt.get_photo(full_hash)

    store = load_suggestion_store()
    photo_sugg = store.get(full_hash)
    suggestions = [s.to_dict() for s in photo_sugg.bibs] if photo_sugg else []

    if label:
        return jsonify({
            'boxes': [b.to_dict() for b in label.boxes],
            'suggestions': suggestions,
            'tags': label.tags,
            'split': label.split,
            'labeled': label.labeled,
        })
    else:
        return jsonify({
            'boxes': [],
            'suggestions': suggestions,
            'tags': [],
            'split': 'full',
            'labeled': False,
        })

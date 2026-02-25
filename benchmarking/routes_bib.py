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
from benchmarking.label_utils import get_filtered_hashes, find_hash_by_prefix
from benchmarking.photo_index import load_photo_index
from benchmarking.runner import list_runs
from config import ITERATION_SPLIT_PROBABILITY

bib_bp = Blueprint('bib', __name__)


@bib_bp.route('/labels/')
def labels_index():
    """Show first photo based on filter."""
    filter_type = request.args.get('filter', 'all')
    hashes = get_filtered_hashes(filter_type)

    if not hashes:
        return render_template('empty.html')

    return redirect(url_for('bib.label_photo', content_hash=hashes[0][:8], filter=filter_type))


@bib_bp.route('/labels/<content_hash>')
def label_photo(content_hash):
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

    prev_url = url_for('bib.label_photo', content_hash=hashes[idx - 1][:8], filter=filter_type) if has_prev else None
    next_url = url_for('bib.label_photo', content_hash=hashes[idx + 1][:8], filter=filter_type) if has_next else None

    # Find next unlabeled photo (in full sorted list, starting after current)
    all_hashes_sorted = sorted(load_photo_index().keys())
    next_unlabeled_url = None
    try:
        all_idx = all_hashes_sorted.index(full_hash)
        for h in all_hashes_sorted[all_idx + 1:]:
            lbl = bib_gt.get_photo(h)
            if not lbl or not lbl.labeled:
                next_unlabeled_url = url_for('bib.label_photo', content_hash=h[:8], filter=filter_type)
                break
    except ValueError:
        pass

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
def save_label():
    """Save a photo label.

    Accepts either ``boxes`` (list of {x,y,w,h,number,scope} dicts) or
    the legacy ``bibs`` (list of ints) for backward compatibility.
    """
    data = request.get_json()

    content_hash = data.get('content_hash')
    tags = data.get('tags', [])
    split = data.get('split', 'full')

    if not content_hash:
        return jsonify({'error': 'Missing content_hash'}), 400

    try:
        bib_gt = load_bib_ground_truth()
        if 'boxes' in data:
            boxes = [BibBox.from_dict(b) for b in data['boxes']]
        else:
            bibs = data.get('bibs', [])
            boxes = [BibBox(x=0, y=0, w=0, h=0, number=str(b), scope="bib") for b in bibs]
        label = BibPhotoLabel(
            content_hash=content_hash,
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


@bib_bp.route('/api/bib_boxes/<content_hash>')
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

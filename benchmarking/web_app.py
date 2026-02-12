#!/usr/bin/env python3
"""
Unified Flask application for benchmark labeling and inspection.

Routes:
- /labels/ - Labeling UI for annotating photos
- /faces/labels/ - Face labeling UI for annotating face counts/tags
- /benchmark/ - List of benchmark runs
- /benchmark/<run_id>/ - Inspection UI for a specific run
"""

import argparse
import logging
import json
import random
import sys
from pathlib import Path

import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import (
    Flask,
    render_template,
    send_from_directory,
    send_file,
    request,
    jsonify,
    redirect,
    url_for,
    abort,
)

from benchmarking.ground_truth import (
    BibBox,
    BibPhotoLabel,
    FaceBox,
    FacePhotoLabel,
    load_bib_ground_truth,
    save_bib_ground_truth,
    load_face_ground_truth,
    save_face_ground_truth,
    ALLOWED_TAGS,
    ALLOWED_FACE_TAGS,
    FACE_BOX_TAGS,
)
from benchmarking.face_embeddings import build_embedding_index, find_top_k, EmbeddingIndex
from benchmarking.ghost import load_suggestion_store
from benchmarking.identities import load_identities, add_identity, rename_identity
from benchmarking.photo_index import load_photo_index, get_path_for_hash
from benchmarking.runner import (
    list_runs,
    get_run,
    RESULTS_DIR,
)
from config import ITERATION_SPLIT_PROBABILITY
from logging_utils import add_logging_args, configure_logging

logger = logging.getLogger(__name__)

# Photos directory
PHOTOS_DIR = Path(__file__).parent.parent / "photos"


# =============================================================================
# FLASK APP
# =============================================================================

def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / 'templates'),
    )

    # -------------------------------------------------------------------------
    # Index / Root
    # -------------------------------------------------------------------------
    @app.route('/')
    def index():
        """Landing page for label UIs."""
        return render_template('labels_home.html')

    @app.route('/faces/')
    def faces_root():
        """Redirect to face labels."""
        return redirect(url_for('face_labels_index'))

    # -------------------------------------------------------------------------
    # Labeling Routes
    # -------------------------------------------------------------------------
    @app.route('/labels/')
    def labels_index():
        """Show first photo based on filter."""
        filter_type = request.args.get('filter', 'all')
        hashes = get_filtered_hashes(filter_type)

        if not hashes:
            return render_template('empty.html')

        return redirect(url_for('label_photo', content_hash=hashes[0][:8], filter=filter_type))

    @app.route('/labels/<content_hash>')
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

        prev_url = url_for('label_photo', content_hash=hashes[idx - 1][:8], filter=filter_type) if has_prev else None
        next_url = url_for('label_photo', content_hash=hashes[idx + 1][:8], filter=filter_type) if has_next else None

        # Find next unlabeled photo (in full sorted list, starting after current)
        all_hashes_sorted = sorted(load_photo_index().keys())
        next_unlabeled_url = None
        try:
            all_idx = all_hashes_sorted.index(full_hash)
            for h in all_hashes_sorted[all_idx + 1:]:
                lbl = bib_gt.get_photo(h)
                if not lbl or not lbl.labeled:
                    next_unlabeled_url = url_for('label_photo', content_hash=h[:8], filter=filter_type)
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

    @app.route('/api/labels', methods=['POST'])
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

    @app.route('/faces/labels/')
    def face_labels_index():
        """Show first photo for face labeling based on filter."""
        filter_type = request.args.get('filter', 'all')
        hashes = get_filtered_face_hashes(filter_type)

        if not hashes:
            return render_template('empty.html')

        return redirect(url_for('face_label_photo', content_hash=hashes[0][:8], filter=filter_type))

    @app.route('/faces/labels/<content_hash>')
    def face_label_photo(content_hash):
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

        prev_url = url_for('face_label_photo', content_hash=hashes[idx - 1][:8], filter=filter_type) if has_prev else None
        next_url = url_for('face_label_photo', content_hash=hashes[idx + 1][:8], filter=filter_type) if has_next else None

        # Find next unlabeled photo (in full sorted list, starting after current)
        all_hashes_sorted = sorted(load_photo_index().keys())
        next_unlabeled_url = None
        try:
            all_idx = all_hashes_sorted.index(full_hash)
            for h in all_hashes_sorted[all_idx + 1:]:
                fl = face_gt.get_photo(h)
                if not fl or not is_face_labeled(fl):
                    next_unlabeled_url = url_for('face_label_photo', content_hash=h[:8], filter=filter_type)
                    break
        except ValueError:
            pass

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

    @app.route('/api/face_labels', methods=['POST'])
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

    # -------------------------------------------------------------------------
    # Box API endpoints (canvas UI)
    # -------------------------------------------------------------------------
    @app.route('/api/bib_boxes/<content_hash>')
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

    @app.route('/api/face_boxes/<content_hash>')
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

    @app.route('/api/identities')
    def get_identities():
        return jsonify({'identities': load_identities()})

    @app.route('/api/identities', methods=['POST'])
    def post_identity():
        data = request.get_json()
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'error': 'Missing name'}), 400
        ids = add_identity(name)
        return jsonify({'identities': ids})

    @app.route('/api/rename_identity', methods=['POST'])
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

    # -------------------------------------------------------------------------
    # Face identity suggestion endpoint
    # -------------------------------------------------------------------------
    _embedding_index_cache: dict[str, EmbeddingIndex] = {}

    @app.route('/api/face_identity_suggestions/<content_hash>')
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

        # Build or retrieve cached embedding index
        if 'index' not in _embedding_index_cache:
            try:
                from faces.embedder import get_face_embedder
                embedder = get_face_embedder()
                face_gt = load_face_ground_truth()
                _embedding_index_cache['index'] = build_embedding_index(
                    face_gt, PHOTOS_DIR, index, embedder
                )
                logger.info(
                    "Built embedding index: %d faces",
                    _embedding_index_cache['index'].size,
                )
            except Exception as e:
                logger.exception("Failed to build embedding index: %s", e)
                return jsonify({'suggestions': []})

        emb_index = _embedding_index_cache['index']
        if emb_index.size == 0:
            return jsonify({'suggestions': []})

        # Load photo and compute query embedding
        photo_path = get_path_for_hash(full_hash, PHOTOS_DIR, index)
        if not photo_path or not photo_path.exists():
            return jsonify({'error': 'Photo file not found'}), 404

        import cv2 as _cv2
        image_data = photo_path.read_bytes()
        image_array = _cv2.imdecode(
            np.frombuffer(image_data, np.uint8), _cv2.IMREAD_COLOR
        )
        if image_array is None:
            return jsonify({'error': 'Failed to decode image'}), 500
        image_rgb = _cv2.cvtColor(image_array, _cv2.COLOR_BGR2RGB)
        h, w = image_rgb.shape[:2]

        # Convert normalised coords to pixel bbox polygon
        from geometry import rect_to_bbox
        px = int(box_x * w)
        py = int(box_y * h)
        pw = int(box_w * w)
        ph = int(box_h * h)
        bbox = rect_to_bbox(px, py, pw, ph)

        from faces.embedder import get_face_embedder
        embedder = get_face_embedder()
        embeddings = embedder.embed(image_rgb, [bbox])
        if not embeddings:
            return jsonify({'suggestions': []})

        matches = find_top_k(embeddings[0], emb_index, k=k)
        return jsonify({'suggestions': [m.to_dict() for m in matches]})

    # -------------------------------------------------------------------------
    # Face crop endpoint (for identity suggestion hover previews)
    # -------------------------------------------------------------------------
    @app.route('/api/face_crop/<content_hash>/<int:box_index>')
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
        import io

        img = Image.open(photo_path)
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

    # -------------------------------------------------------------------------
    # Benchmark Routes
    # -------------------------------------------------------------------------
    @app.route('/benchmark/')
    def benchmark_list():
        """List all benchmark runs."""
        runs = list_runs()
        return render_template('benchmark_list.html', runs=runs)

    @app.route('/benchmark/<run_id>/')
    def benchmark_inspect(run_id):
        """Inspect a specific benchmark run."""
        run = get_run(run_id)
        if not run:
            return "Run not found", 404

        filter_type = request.args.get('filter', 'all')
        idx = request.args.get('idx', 0, type=int)
        hash_query = request.args.get('hash', '')

        filtered = filter_results(run.photo_results, filter_type)

        if not filtered:
            return "No photos match the filter.", 404

        if hash_query:
            for i, r in enumerate(filtered):
                if r.content_hash.startswith(hash_query):
                    idx = i
                    break

        idx = max(0, min(idx, len(filtered) - 1))

        photo_results_json = json.dumps([{
            'content_hash': r.content_hash,
            'expected_bibs': r.expected_bibs,
            'detected_bibs': r.detected_bibs,
            'tp': r.tp,
            'fp': r.fp,
            'fn': r.fn,
            'status': r.status,
            'detection_time_ms': r.detection_time_ms,
            'tags': r.tags,
            'artifact_paths': r.artifact_paths,
            'preprocess_metadata': r.preprocess_metadata,
        } for r in filtered])

        all_runs = list_runs()

        # Get pipeline summary
        pipeline_summary = "unknown"
        passes_summary = "unknown"
        if run.metadata.pipeline_config:
            pipeline_summary = run.metadata.pipeline_config.summary()
        if run.metadata.face_pipeline_config:
            passes_summary = run.metadata.face_pipeline_config.summary_passes()

        return render_template(
            'benchmark_inspect.html',
            run=run,
            filtered_results=filtered,
            current_idx=idx,
            filter=filter_type,
            photo_results_json=photo_results_json,
            all_runs=all_runs,
            pipeline_summary=pipeline_summary,
            passes_summary=passes_summary,
        )

    # -------------------------------------------------------------------------
    # Shared Routes
    # -------------------------------------------------------------------------
    @app.route('/photo/<content_hash>')
    def serve_photo(content_hash):
        """Serve photo by content hash."""
        index = load_photo_index()

        full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
        if not full_hash:
            return "Not found", 404

        path = get_path_for_hash(full_hash, PHOTOS_DIR, index)
        if not path or not path.exists():
            return "Not found", 404

        return send_file(path)

    @app.route('/artifact/<run_id>/<hash_prefix>/<image_type>')
    def serve_artifact(run_id, hash_prefix, image_type):
        """Serve artifact image from run directory."""
        artifact_dir = RESULTS_DIR / run_id / "images" / hash_prefix

        filename_map = {
            'original': 'original.jpg',
            'grayscale': 'grayscale.jpg',
            'clahe': 'clahe.jpg',
            'resize': 'resize.jpg',
            'candidates': 'candidates.jpg',
            'detections': 'detections.jpg',
        }

        filename = filename_map.get(image_type)
        if not filename:
            abort(404)

        artifact_path = artifact_dir / filename
        if not artifact_path.exists():
            abort(404)

        return send_file(artifact_path)

    # -------------------------------------------------------------------------
    # Static files & test route
    # -------------------------------------------------------------------------
    @app.route('/static/<path:filename>')
    def serve_static(filename):
        """Serve static assets (JS, CSS, HTML)."""
        static_dir = Path(__file__).parent / 'static'
        return send_from_directory(static_dir, filename)

    @app.route('/test/labeling')
    def test_labeling():
        """Serve the browser integration test page."""
        static_dir = Path(__file__).parent / 'static'
        return send_from_directory(static_dir, 'test_labeling.html')

    return app


# =============================================================================
# HELPERS
# =============================================================================

def get_filtered_hashes(filter_type: str) -> list[str]:
    """Get photo hashes based on filter."""
    index = load_photo_index()
    all_hashes = set(index.keys())

    if filter_type == 'all':
        return sorted(all_hashes)

    gt = load_bib_ground_truth()
    labeled_hashes = {
        content_hash
        for content_hash, label in gt.photos.items()
        if label.labeled
    }

    if filter_type == 'unlabeled':
        return sorted(all_hashes - labeled_hashes)
    elif filter_type == 'labeled':
        return sorted(all_hashes & labeled_hashes)
    else:
        return sorted(all_hashes)


def is_face_labeled(label: FacePhotoLabel) -> bool:
    """Check if a photo has face labeling data."""
    return bool(label.boxes) or bool(label.tags)


def get_filtered_face_hashes(filter_type: str) -> list[str]:
    """Get photo hashes based on face label filter."""
    index = load_photo_index()
    all_hashes = set(index.keys())

    if filter_type == 'all':
        return sorted(all_hashes)

    gt = load_face_ground_truth()
    labeled_hashes = {
        content_hash
        for content_hash, label in gt.photos.items()
        if is_face_labeled(label)
    }

    if filter_type == 'unlabeled':
        return sorted(all_hashes - labeled_hashes)
    elif filter_type == 'labeled':
        return sorted(all_hashes & labeled_hashes)
    else:
        return sorted(all_hashes)


def find_hash_by_prefix(prefix: str, hashes) -> str | None:
    """Find full hash from prefix."""
    if isinstance(hashes, set):
        hashes = list(hashes)

    matches = [h for h in hashes if h.startswith(prefix)]
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        for h in matches:
            if h == prefix:
                return h
        return matches[0]
    return None


def filter_results(results, filter_type):
    """Filter photo results by status."""
    if filter_type == 'all':
        return results
    elif filter_type == 'pass':
        return [r for r in results if r.status == 'PASS']
    elif filter_type == 'partial':
        return [r for r in results if r.status == 'PARTIAL']
    elif filter_type == 'miss':
        return [r for r in results if r.status == 'MISS']
    return results


# =============================================================================
# MAIN
# =============================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch the benchmark labeling/inspection UI (port 30002)."
    )
    add_logging_args(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the web server."""
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level, args.verbose, args.quiet)
    index = load_photo_index()
    if not index:
        logger.error("No photo index found. Run 'python -m benchmarking.cli scan' first.")
        return 1

    app = create_app()

    logger.info("Starting Benchmark Web UI...")
    logger.info("Found %s photos in index", len(index))
    logger.info("Routes:")
    logger.info("  /labels/              - Label photos")
    logger.info("  /faces/labels/        - Label face counts/tags")
    logger.info("  /benchmark/           - List benchmark runs")
    logger.info("  /benchmark/<run_id>/  - Inspect a run")
    logger.info("Open http://localhost:30002 in your browser")
    logger.info("Press Ctrl+C to stop")
    app.run(host='localhost', port=30002, debug=False)
    return 0


if __name__ == '__main__':
    sys.exit(main())

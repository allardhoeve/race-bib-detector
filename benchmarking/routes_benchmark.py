"""Benchmark inspection routes."""

import json

from flask import Blueprint, jsonify, render_template, request, abort, send_file

from benchmarking.label_utils import filter_results
from benchmarking.photo_index import load_photo_index
from benchmarking.runner import list_runs, get_run, RESULTS_DIR

benchmark_bp = Blueprint('benchmark', __name__)


@benchmark_bp.route('/benchmark/')
def benchmark_list():
    """List all benchmark runs."""
    runs = list_runs()
    return render_template('benchmark_list.html', runs=runs)


@benchmark_bp.route('/benchmark/<run_id>/')
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


@benchmark_bp.route('/staging/')
def staging():
    from benchmarking.completeness import get_all_completeness
    rows = get_all_completeness()
    index = load_photo_index()
    return render_template(
        "staging.html",
        rows=rows,
        index=index,
    )


@benchmark_bp.route('/api/freeze', methods=['POST'])
def api_freeze():
    from benchmarking.sets import freeze
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    description = data.get("description", "")
    hashes = data.get("hashes", [])

    if not name:
        return jsonify({"error": "name is required"}), 400
    if not hashes:
        return jsonify({"error": "hashes list is empty"}), 400

    index = load_photo_index()
    # Flatten list-of-paths to single path per hash
    flat_index = {h: (paths[0] if isinstance(paths, list) else paths)
                  for h, paths in index.items() if h in hashes}

    try:
        snapshot = freeze(
            name=name,
            hashes=sorted(flat_index.keys()),
            index=flat_index,
            description=description,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 409

    return jsonify(snapshot.metadata.to_dict()), 200


@benchmark_bp.route('/artifact/<run_id>/<hash_prefix>/<image_type>')
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

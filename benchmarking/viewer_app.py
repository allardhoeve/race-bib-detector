#!/usr/bin/env python3
"""
Flask application for benchmark inspection UI.

A visual tool for reviewing benchmark results, comparing detections against
ground truth, and viewing pipeline intermediate images.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template_string, send_file, request, jsonify, redirect, url_for, abort

from benchmarking.runner import BenchmarkRun, RESULTS_DIR
from benchmarking.photo_index import load_photo_index, get_path_for_hash

# Photos directory
PHOTOS_DIR = Path(__file__).parent.parent / "photos"


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Benchmark Inspector - {{ run.metadata.run_id }}</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            padding: 10px 20px;
            background: #16213e;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #0f3460;
        }
        .run-info {
            display: flex;
            align-items: center;
            gap: 20px;
        }
        .run-id {
            font-family: monospace;
            color: #0f9b0f;
        }
        .metrics {
            display: flex;
            gap: 15px;
            font-size: 14px;
        }
        .metric {
            padding: 4px 10px;
            background: #0f3460;
            border-radius: 4px;
        }
        .metric-label { color: #888; }
        .metric-value { font-weight: bold; }
        .nav-info {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .nav-btn {
            background: #0f3460;
            color: #eee;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }
        .nav-btn:hover { background: #1a4a7a; }
        .nav-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .position { color: #888; font-size: 14px; }
        .main {
            flex: 1;
            display: flex;
            overflow: hidden;
        }
        .sidebar {
            width: 280px;
            background: #16213e;
            overflow-y: auto;
            border-right: 1px solid #0f3460;
        }
        .photo-list {
            list-style: none;
        }
        .photo-item {
            padding: 10px 15px;
            border-bottom: 1px solid #0f3460;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .photo-item:hover { background: #1a4a7a; }
        .photo-item.active { background: #0f3460; border-left: 3px solid #0f9b0f; }
        .photo-hash {
            font-family: monospace;
            font-size: 12px;
        }
        .photo-status {
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 11px;
            font-weight: bold;
        }
        .status-PASS { background: #0f9b0f; color: white; }
        .status-PARTIAL { background: #f0ad4e; color: black; }
        .status-MISS { background: #d9534f; color: white; }
        .content {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .image-tabs {
            display: flex;
            gap: 5px;
            padding: 10px;
            background: #0d0d1a;
            border-bottom: 1px solid #0f3460;
            flex-wrap: wrap;
        }
        .image-tab {
            padding: 8px 16px;
            background: #1a1a2e;
            border: 1px solid #0f3460;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            color: #888;
        }
        .image-tab:hover { background: #0f3460; color: #eee; }
        .image-tab.active { background: #0f3460; color: #0f9b0f; border-color: #0f9b0f; }
        .image-panel {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            background: #0d0d1a;
            overflow: auto;
        }
        .image-panel img {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
        }
        .details-panel {
            padding: 15px;
            background: #16213e;
            border-top: 1px solid #0f3460;
        }
        .details-row {
            display: flex;
            gap: 30px;
            font-size: 14px;
        }
        .detail-item {
            display: flex;
            gap: 8px;
        }
        .detail-label { color: #888; }
        .detail-value { color: #eee; }
        .bib-list {
            display: flex;
            gap: 5px;
            flex-wrap: wrap;
        }
        .bib {
            padding: 2px 8px;
            border-radius: 3px;
            font-family: monospace;
            font-size: 13px;
        }
        .bib-expected { background: #0f3460; }
        .bib-detected { background: #1a4a7a; }
        .bib-tp { background: #0f9b0f; color: white; }
        .bib-fp { background: #d9534f; color: white; }
        .bib-fn { background: #f0ad4e; color: black; }
        .filter-section {
            padding: 10px 15px;
            border-bottom: 1px solid #0f3460;
            background: #1a1a2e;
        }
        .filter-select {
            width: 100%;
            padding: 8px;
            background: #16213e;
            border: 1px solid #0f3460;
            color: #eee;
            border-radius: 4px;
        }
        .keyboard-hint {
            font-size: 12px;
            color: #666;
            text-align: center;
            padding: 10px;
        }
        .tags-list {
            display: flex;
            gap: 5px;
            flex-wrap: wrap;
        }
        .tag {
            padding: 2px 6px;
            background: #0f3460;
            border-radius: 3px;
            font-size: 11px;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="run-info">
            <span class="run-id">{{ run.metadata.run_id }}</span>
            <div class="metrics">
                <span class="metric">
                    <span class="metric-label">P:</span>
                    <span class="metric-value">{{ "%.1f"|format(run.metrics.precision * 100) }}%</span>
                </span>
                <span class="metric">
                    <span class="metric-label">R:</span>
                    <span class="metric-value">{{ "%.1f"|format(run.metrics.recall * 100) }}%</span>
                </span>
                <span class="metric">
                    <span class="metric-label">F1:</span>
                    <span class="metric-value">{{ "%.1f"|format(run.metrics.f1 * 100) }}%</span>
                </span>
                <span class="metric">
                    <span class="metric-label">Photos:</span>
                    <span class="metric-value">{{ run.metrics.total_photos }}</span>
                </span>
            </div>
        </div>
        <div class="nav-info">
            <button class="nav-btn" onclick="navigate('prev')" id="prevBtn">&#8592; Prev</button>
            <span class="position"><span id="currentPos">{{ current_idx + 1 }}</span> / {{ filtered_results|length }}</span>
            <button class="nav-btn" onclick="navigate('next')" id="nextBtn">Next &#8594;</button>
        </div>
    </div>

    <div class="main">
        <div class="sidebar">
            <div class="filter-section">
                <select class="filter-select" id="filter" onchange="applyFilter()">
                    <option value="all" {{ 'selected' if filter == 'all' else '' }}>All photos ({{ run.metrics.total_photos }})</option>
                    <option value="pass" {{ 'selected' if filter == 'pass' else '' }}>PASS ({{ run.metrics.pass_count }})</option>
                    <option value="partial" {{ 'selected' if filter == 'partial' else '' }}>PARTIAL ({{ run.metrics.partial_count }})</option>
                    <option value="miss" {{ 'selected' if filter == 'miss' else '' }}>MISS ({{ run.metrics.miss_count }})</option>
                </select>
            </div>
            <ul class="photo-list">
                {% for result in filtered_results %}
                <li class="photo-item {{ 'active' if loop.index0 == current_idx else '' }}"
                    onclick="selectPhoto({{ loop.index0 }})"
                    data-idx="{{ loop.index0 }}"
                    data-hash="{{ result.content_hash[:16] }}">
                    <span class="photo-hash">{{ result.content_hash[:16] }}...</span>
                    <span class="photo-status status-{{ result.status }}">{{ result.status }}</span>
                </li>
                {% endfor %}
            </ul>
        </div>

        <div class="content">
            <div class="image-tabs" id="imageTabs">
                <button class="image-tab active" data-image="original" onclick="showImage('original')">Original</button>
                <button class="image-tab" data-image="grayscale" onclick="showImage('grayscale')">Grayscale</button>
                <button class="image-tab" data-image="resize" onclick="showImage('resize')">Resized</button>
                <button class="image-tab" data-image="candidates" onclick="showImage('candidates')">Candidates</button>
                <button class="image-tab" data-image="detections" onclick="showImage('detections')">Detections</button>
            </div>

            <div class="image-panel">
                <img id="mainImage" src="" alt="Photo">
            </div>

            <div class="details-panel">
                <div class="details-row">
                    <div class="detail-item">
                        <span class="detail-label">Status:</span>
                        <span class="detail-value" id="detailStatus"></span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Expected:</span>
                        <div class="bib-list" id="expectedBibs"></div>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Detected:</span>
                        <div class="bib-list" id="detectedBibs"></div>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">TP/FP/FN:</span>
                        <span class="detail-value" id="detailCounts"></span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Time:</span>
                        <span class="detail-value" id="detailTime"></span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Tags:</span>
                        <div class="tags-list" id="detailTags"></div>
                    </div>
                    <div class="detail-item">
                        <a href="#" id="editLink" target="_blank" style="color: #0f9b0f;">Edit Labels →</a>
                    </div>
                </div>
            </div>

            <div class="keyboard-hint">
                &#8592; &#8594; navigate | 1-5 switch image tabs
            </div>
        </div>
    </div>

    <script>
        // Photo results data
        const photoResults = {{ photo_results_json | safe }};
        const runId = '{{ run.metadata.run_id }}';
        let currentIdx = {{ current_idx }};
        let currentImageType = 'original';

        function selectPhoto(idx) {
            if (idx < 0 || idx >= photoResults.length) return;

            currentIdx = idx;

            // Update active state in sidebar
            document.querySelectorAll('.photo-item').forEach((el, i) => {
                el.classList.toggle('active', i === idx);
            });

            // Update position display
            document.getElementById('currentPos').textContent = idx + 1;

            // Update nav buttons
            document.getElementById('prevBtn').disabled = idx === 0;
            document.getElementById('nextBtn').disabled = idx === photoResults.length - 1;

            // Scroll active item into view
            const activeItem = document.querySelector('.photo-item.active');
            if (activeItem) {
                activeItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }

            // Update details and image
            updateDetails();
            updateImage();

            // Update URL without reload
            history.replaceState(null, '', `?filter=${document.getElementById('filter').value}&idx=${idx}`);
        }

        function updateDetails() {
            const result = photoResults[currentIdx];

            // Status
            document.getElementById('detailStatus').innerHTML =
                `<span class="photo-status status-${result.status}">${result.status}</span>`;

            // Expected bibs
            const expectedHtml = result.expected_bibs.map(bib => {
                const isMatch = result.detected_bibs.includes(bib);
                const cls = isMatch ? 'bib-tp' : 'bib-fn';
                return `<span class="bib ${cls}">${bib}</span>`;
            }).join('') || '<span style="color:#666">none</span>';
            document.getElementById('expectedBibs').innerHTML = expectedHtml;

            // Detected bibs
            const detectedHtml = result.detected_bibs.map(bib => {
                const isMatch = result.expected_bibs.includes(bib);
                const cls = isMatch ? 'bib-tp' : 'bib-fp';
                return `<span class="bib ${cls}">${bib}</span>`;
            }).join('') || '<span style="color:#666">none</span>';
            document.getElementById('detectedBibs').innerHTML = detectedHtml;

            // Counts
            document.getElementById('detailCounts').textContent =
                `${result.tp} / ${result.fp} / ${result.fn}`;

            // Time
            document.getElementById('detailTime').textContent =
                `${result.detection_time_ms.toFixed(0)}ms`;

            // Tags
            const tagsHtml = result.tags.map(tag =>
                `<span class="tag">${tag}</span>`
            ).join('') || '<span style="color:#666">none</span>';
            document.getElementById('detailTags').innerHTML = tagsHtml;

            // Edit link - use first 16 chars of hash (consistent with labeling UI)
            const hashPrefix = result.content_hash.substring(0, 16);
            document.getElementById('editLink').href =
                `http://localhost:30002/label/${hashPrefix}`;
        }

        function updateImage() {
            const result = photoResults[currentIdx];
            const hash = result.content_hash;
            const hashPrefix = hash.substring(0, 16);

            let imagePath;
            if (currentImageType === 'original') {
                // Original photo from photos directory
                imagePath = `/photo/${hash}`;
            } else {
                // Artifact from run directory
                imagePath = `/artifact/${runId}/${hashPrefix}/${currentImageType}`;
            }

            document.getElementById('mainImage').src = imagePath;
        }

        function showImage(imageType) {
            currentImageType = imageType;

            // Update tab state
            document.querySelectorAll('.image-tab').forEach(tab => {
                tab.classList.toggle('active', tab.dataset.image === imageType);
            });

            updateImage();
        }

        function navigate(direction) {
            const newIdx = direction === 'prev' ? currentIdx - 1 : currentIdx + 1;
            if (newIdx >= 0 && newIdx < photoResults.length) {
                selectPhoto(newIdx);
            }
        }

        function applyFilter() {
            const filter = document.getElementById('filter').value;
            window.location.href = `?filter=${filter}`;
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft') {
                navigate('prev');
            } else if (e.key === 'ArrowRight') {
                navigate('next');
            } else if (e.key >= '1' && e.key <= '5') {
                const tabs = ['original', 'grayscale', 'resize', 'candidates', 'detections'];
                const idx = parseInt(e.key) - 1;
                if (idx < tabs.length) {
                    showImage(tabs[idx]);
                }
            }
        });

        // Initialize
        updateDetails();
        updateImage();
    </script>
</body>
</html>
"""


def create_app(run: BenchmarkRun) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Store run in app context
    app.config['BENCHMARK_RUN'] = run

    @app.route('/')
    def index():
        """Show inspection UI."""
        filter_type = request.args.get('filter', 'all')
        idx = request.args.get('idx', 0, type=int)
        hash_query = request.args.get('hash', '')

        # Filter results
        filtered = filter_results(run.photo_results, filter_type)

        if not filtered:
            return "No photos match the filter.", 404

        # If hash query provided, find matching photo
        if hash_query:
            for i, r in enumerate(filtered):
                if r.content_hash.startswith(hash_query):
                    idx = i
                    break

        # Clamp index
        idx = max(0, min(idx, len(filtered) - 1))

        # Prepare JSON for JavaScript
        import json
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
        } for r in filtered])

        return render_template_string(
            HTML_TEMPLATE,
            run=run,
            filtered_results=filtered,
            current_idx=idx,
            filter=filter_type,
            photo_results_json=photo_results_json,
        )

    @app.route('/photo/<content_hash>')
    def serve_photo(content_hash):
        """Serve original photo by content hash."""
        index = load_photo_index()

        # Find full hash from prefix
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

        # Map image type to filename
        filename_map = {
            'original': 'original.jpg',
            'grayscale': 'grayscale.jpg',
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

    return app


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


def main(run: BenchmarkRun):
    """Run the inspection web server."""
    app = create_app(run)

    print("Starting Benchmark Inspector...")
    print(f"Run ID: {run.metadata.run_id}")
    print(f"Split: {run.metadata.split}")
    print(f"Photos: {run.metrics.total_photos}")
    print("Open http://localhost:30003 in your browser")
    print("Press Ctrl+C to stop")
    app.run(host='localhost', port=30003, debug=False)
    return 0


if __name__ == '__main__':
    # For testing, load latest run
    from benchmarking.runner import get_latest_run
    run = get_latest_run()
    if run:
        sys.exit(main(run))
    else:
        print("No benchmark runs found.")
        sys.exit(1)

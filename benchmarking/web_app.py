#!/usr/bin/env python3
"""
Unified Flask application for benchmark labeling and inspection.

Routes:
- /labels/ - Labeling UI for annotating photos
- /benchmark/ - List of benchmark runs
- /benchmark/<run_id>/ - Inspection UI for a specific run
"""

import json
import random
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import (
    Flask,
    render_template_string,
    send_from_directory,
    send_file,
    request,
    jsonify,
    redirect,
    url_for,
    abort,
)

from benchmarking.ground_truth import (
    load_ground_truth,
    save_ground_truth,
    PhotoLabel,
    ALLOWED_TAGS,
    ALLOWED_SPLITS,
)
from benchmarking.photo_index import load_photo_index, get_path_for_hash
from benchmarking.runner import (
    BenchmarkRun,
    list_runs,
    get_run,
    get_latest_run,
    RESULTS_DIR,
)
from config import ITERATION_SPLIT_PROBABILITY

# Photos directory
PHOTOS_DIR = Path(__file__).parent.parent / "photos"

# Common styles shared between UIs
COMMON_STYLES = """
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
    text-decoration: none;
}
.nav-btn:hover { background: #1a4a7a; }
.nav-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.nav-link {
    color: #0f9b0f;
    text-decoration: none;
    padding: 8px 16px;
}
.nav-link:hover { text-decoration: underline; }
.position { color: #888; font-size: 14px; }
.main {
    flex: 1;
    display: flex;
    overflow: hidden;
    min-height: 0;
}
.sidebar {
    width: 280px;
    background: #16213e;
    overflow-y: auto;
    border-right: 1px solid #0f3460;
}
.image-panel {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    background: #0d0d1a;
    overflow: hidden;
    min-height: 0;
}
.image-panel img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
}
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
.photo-list { list-style: none; }
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
.photo-hash { font-family: monospace; font-size: 12px; }
.photo-status {
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 11px;
    font-weight: bold;
}
.status-PASS { background: #0f9b0f; color: white; }
.status-PARTIAL { background: #f0ad4e; color: black; }
.status-MISS { background: #d9534f; color: white; }
.status-labeled { background: #0f9b0f; color: white; }
.status-unlabeled { background: #555; color: white; }
"""


# =============================================================================
# LABELING UI TEMPLATE
# =============================================================================

LABELING_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Labeling - {{ current }} / {{ total }}</title>
    <style>
        """ + COMMON_STYLES + """
        .form-panel {
            width: 350px;
            padding: 20px;
            background: #16213e;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        .form-section h3 {
            margin-bottom: 10px;
            color: #0f9b0f;
            font-size: 14px;
            text-transform: uppercase;
        }
        .bibs-input {
            width: 100%;
            padding: 12px;
            font-size: 18px;
            border: 2px solid #0f3460;
            border-radius: 4px;
            background: #1a1a2e;
            color: #eee;
        }
        .bibs-input:focus {
            outline: none;
            border-color: #0f9b0f;
        }
        .tags-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
        }
        .tag-checkbox {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px;
            background: #1a1a2e;
            border-radius: 4px;
            cursor: pointer;
        }
        .tag-checkbox:hover { background: #252545; }
        .tag-checkbox input { width: 18px; height: 18px; }
        .tag-checkbox label { cursor: pointer; font-size: 13px; }
        .split-buttons { display: flex; gap: 10px; }
        .split-btn {
            flex: 1;
            padding: 10px;
            border: 2px solid #0f3460;
            background: #1a1a2e;
            color: #eee;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }
        .split-btn:hover { border-color: #1a4a7a; }
        .split-btn.active { border-color: #0f9b0f; background: #0f3460; }
        .save-btn {
            padding: 15px;
            background: #0f9b0f;
            color: white;
            border: none;
            border-radius: 4px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
        }
        .save-btn:hover { background: #0d8a0d; }
        .status {
            text-align: center;
            padding: 10px;
            border-radius: 4px;
            font-size: 14px;
        }
        .status.success { background: #0f3460; color: #0f9b0f; }
        .status.error { background: #3d0a0a; color: #ff6b6b; }
        .hash-display {
            font-family: monospace;
            font-size: 11px;
            color: #666;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="nav-info">
            <a href="{{ url_for('benchmark_list') }}" class="nav-link">← Benchmarks</a>
            <button class="nav-btn" onclick="navigate('prev')" {{ 'disabled' if not has_prev else '' }}>← Prev</button>
            <span class="position">{{ current }} / {{ total }}</span>
            <button class="nav-btn" onclick="navigate('next')" {{ 'disabled' if not has_next else '' }}>Next →</button>
        </div>
        <div class="filter-section" style="background: transparent; border: none; padding: 0;">
            <select class="filter-select" style="width: auto;" id="filter" onchange="applyFilter()">
                <option value="all" {{ 'selected' if filter == 'all' else '' }}>All photos</option>
                <option value="unlabeled" {{ 'selected' if filter == 'unlabeled' else '' }}>Unlabeled only</option>
                <option value="labeled" {{ 'selected' if filter == 'labeled' else '' }}>Labeled only</option>
            </select>
        </div>
    </div>

    <div class="main">
        <div class="image-panel">
            <img src="{{ url_for('serve_photo', content_hash=content_hash) }}" alt="Photo">
        </div>

        <div class="form-panel">
            <div class="form-section">
                <h3>Bib Numbers</h3>
                <input type="text" class="bibs-input" id="bibs" placeholder="e.g. 123, 456"
                       value="{{ bibs_str }}" autofocus>
            </div>

            <div class="form-section">
                <h3>Tags</h3>
                <div class="tags-grid">
                    {% for tag in all_tags %}
                    <div class="tag-checkbox">
                        <input type="checkbox" id="tag_{{ tag }}" name="tags" value="{{ tag }}"
                               {{ 'checked' if tag in tags else '' }}>
                        <label for="tag_{{ tag }}">{{ tag.replace('_', ' ') }}</label>
                    </div>
                    {% endfor %}
                </div>
            </div>

            <div class="form-section">
                <h3>Split</h3>
                <div class="split-buttons">
                    <button type="button" class="split-btn {{ 'active' if split == 'iteration' else '' }}"
                            onclick="setSplit('iteration')">Iteration</button>
                    <button type="button" class="split-btn {{ 'active' if split == 'full' else '' }}"
                            onclick="setSplit('full')">Full</button>
                </div>
            </div>

            <button class="save-btn" onclick="save()">Save & Next (Enter)</button>

            <div id="status" class="status" style="display: none;"></div>

            <div class="hash-display">
                {{ content_hash[:16] }}...
                {% if latest_run_id %}
                <a href="{{ url_for('benchmark_inspect', run_id=latest_run_id, hash=content_hash[:16]) }}"
                   style="color: #0f9b0f; margin-left: 10px;">View in Inspector →</a>
                {% endif %}
            </div>

            <div class="keyboard-hint">
                ⌘← ⌘→ navigate | Enter save | Esc clear | ⌘O obscured | ⌘N no bib | ⌘B blurry
            </div>
        </div>
    </div>

    <script>
        let currentSplit = '{{ split }}';
        const contentHash = '{{ content_hash }}';

        function setSplit(split) {
            currentSplit = split;
            document.querySelectorAll('.split-btn').forEach(btn => {
                btn.classList.toggle('active', btn.textContent.toLowerCase() === split);
            });
        }

        function getSelectedTags() {
            return Array.from(document.querySelectorAll('input[name="tags"]:checked'))
                        .map(cb => cb.value);
        }

        function getBibs() {
            const input = document.getElementById('bibs').value;
            if (!input.trim()) return [];
            return input.split(/[\\s,]+/)
                       .map(s => parseInt(s.trim(), 10))
                       .filter(n => !isNaN(n));
        }

        function showStatus(message, isError) {
            const status = document.getElementById('status');
            status.textContent = message;
            status.className = 'status ' + (isError ? 'error' : 'success');
            status.style.display = 'block';
            setTimeout(() => { status.style.display = 'none'; }, 2000);
        }

        async function save() {
            const data = {
                content_hash: contentHash,
                bibs: getBibs(),
                tags: getSelectedTags(),
                split: currentSplit
            };

            try {
                const response = await fetch('{{ url_for("save_label") }}', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                if (response.ok) {
                    showStatus('Saved!', false);
                    setTimeout(() => navigate('next'), 300);
                } else {
                    const err = await response.json();
                    showStatus('Error: ' + err.error, true);
                }
            } catch (e) {
                showStatus('Error: ' + e.message, true);
            }
        }

        function navigate(direction) {
            const prevUrl = {{ prev_url|tojson }};
            const nextUrl = {{ next_url|tojson }};
            const url = direction === 'prev' ? prevUrl : nextUrl;
            if (url) window.location.href = url;
        }

        function applyFilter() {
            const newFilter = document.getElementById('filter').value;
            window.location.href = '{{ url_for("labels_index") }}?filter=' + newFilter;
        }

        function toggleTag(tagName) {
            const checkbox = document.getElementById('tag_' + tagName);
            if (checkbox) checkbox.checked = !checkbox.checked;
        }

        document.addEventListener('keydown', (e) => {
            const mod = e.metaKey || e.ctrlKey;

            if (mod && e.key === 'ArrowLeft') { e.preventDefault(); navigate('prev'); return; }
            if (mod && e.key === 'ArrowRight') { e.preventDefault(); navigate('next'); return; }
            if (mod && e.key === 'o') { e.preventDefault(); toggleTag('obscured_bib'); return; }
            if (mod && e.key === 'n') { e.preventDefault(); toggleTag('no_bib'); return; }
            if (mod && e.key === 'b') { e.preventDefault(); toggleTag('blurry_bib'); return; }

            if (e.target.tagName === 'INPUT' && e.key !== 'Enter' && e.key !== 'Escape') return;

            if (e.key === 'ArrowLeft') navigate('prev');
            else if (e.key === 'ArrowRight') navigate('next');
            else if (e.key === 'Enter') { e.preventDefault(); save(); }
            else if (e.key === 'Escape') {
                document.getElementById('bibs').value = '';
                document.getElementById('bibs').focus();
            }
        });

        document.getElementById('bibs').focus();
    </script>
</body>
</html>
"""


# =============================================================================
# BENCHMARK LIST TEMPLATE
# =============================================================================

BENCHMARK_LIST_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Benchmark Runs</title>
    <style>
        """ + COMMON_STYLES + """
        .content {
            flex: 1;
            padding: 40px;
            overflow-y: auto;
        }
        h1 {
            color: #0f9b0f;
            margin-bottom: 30px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }
        th, td {
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #0f3460;
        }
        th {
            background: #16213e;
            color: #0f9b0f;
            font-weight: 600;
        }
        tr:hover { background: #16213e; }
        .run-link {
            color: #0f9b0f;
            text-decoration: none;
            font-family: monospace;
        }
        .run-link:hover { text-decoration: underline; }
        .baseline-badge {
            background: #0f9b0f;
            color: white;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 11px;
            margin-left: 8px;
        }
        .pipeline-badge {
            background: #0f3460;
            color: #eee;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 12px;
            font-family: monospace;
        }
        .metric { font-family: monospace; }
        .no-runs {
            text-align: center;
            padding: 60px;
            color: #666;
        }
        .no-runs code {
            display: block;
            margin-top: 20px;
            padding: 15px;
            background: #16213e;
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="nav-info">
            <a href="{{ url_for('labels_index') }}" class="nav-link">← Labels</a>
            <span style="color: #0f9b0f; font-weight: bold;">Benchmark Runs</span>
        </div>
    </div>

    <div class="content">
        {% if runs %}
        <table>
            <thead>
                <tr>
                    <th>Run ID</th>
                    <th>Date</th>
                    <th>Split</th>
                    <th>Photos</th>
                    <th>Precision</th>
                    <th>Recall</th>
                    <th>F1</th>
                    <th>Commit</th>
                    <th>Pipeline</th>
                </tr>
            </thead>
            <tbody>
                {% for run in runs %}
                <tr>
                    <td>
                        <a href="{{ url_for('benchmark_inspect', run_id=run.run_id) }}" class="run-link">
                            {{ run.run_id }}
                        </a>
                        {% if run.is_baseline %}<span class="baseline-badge">baseline</span>{% endif %}
                    </td>
                    <td>{{ run.timestamp[:10] }}</td>
                    <td>{{ run.split }}</td>
                    <td class="metric">{{ run.total_photos }}</td>
                    <td class="metric">{{ "%.1f%%"|format(run.precision * 100) }}</td>
                    <td class="metric">{{ "%.1f%%"|format(run.recall * 100) }}</td>
                    <td class="metric">{{ "%.1f%%"|format(run.f1 * 100) }}</td>
                    <td style="font-family: monospace;">{{ run.git_commit }}</td>
                    <td><span class="pipeline-badge">{{ run.pipeline or 'unknown' }}</span></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="no-runs">
            <h2>No benchmark runs yet</h2>
            <p>Run a benchmark to create one:</p>
            <code>python -m benchmarking.cli benchmark --split=full</code>
        </div>
        {% endif %}
    </div>
</body>
</html>
"""


# =============================================================================
# BENCHMARK INSPECT TEMPLATE
# =============================================================================

BENCHMARK_INSPECT_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Inspect - {{ run.metadata.run_id }}</title>
    <style>
        """ + COMMON_STYLES + """
        .run-selector {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .run-select {
            padding: 6px 10px;
            background: #1a1a2e;
            border: 1px solid #0f3460;
            color: #eee;
            border-radius: 4px;
            font-family: monospace;
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
        .pipeline-info { background: #1a4a7a; }
        .content {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            min-height: 0;
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
        .details-panel {
            padding: 15px;
            background: #16213e;
            border-top: 1px solid #0f3460;
        }
        .details-row {
            display: flex;
            gap: 30px;
            font-size: 14px;
            flex-wrap: wrap;
        }
        .detail-item {
            display: flex;
            gap: 8px;
            align-items: center;
        }
        .detail-label { color: #888; }
        .bib-list { display: flex; gap: 5px; flex-wrap: wrap; }
        .bib {
            padding: 2px 8px;
            border-radius: 3px;
            font-family: monospace;
            font-size: 13px;
        }
        .bib-tp { background: #0f9b0f; color: white; }
        .bib-fp { background: #d9534f; color: white; }
        .bib-fn { background: #f0ad4e; color: black; }
        .tags-list { display: flex; gap: 5px; flex-wrap: wrap; }
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
        <div class="nav-info">
            <a href="{{ url_for('benchmark_list') }}" class="nav-link">← Runs</a>
            <div class="run-selector">
                <select class="run-select" id="runSelect" onchange="changeRun()">
                    {% for r in all_runs %}
                    <option value="{{ r.run_id }}" {{ 'selected' if r.run_id == run.metadata.run_id else '' }}>
                        {{ r.run_id }} ({{ r.timestamp[:10] }}) - {{ r.split }} [{{ r.pipeline or 'unknown' }}]
                    </option>
                    {% endfor %}
                </select>
            </div>
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
                <span class="metric pipeline-info">
                    <span class="metric-label">Pipeline:</span>
                    <span class="metric-value">{{ pipeline_summary }}</span>
                </span>
            </div>
        </div>
        <div class="nav-info">
            <button class="nav-btn" onclick="navigate('prev')" id="prevBtn">← Prev</button>
            <span class="position"><span id="currentPos">{{ current_idx + 1 }}</span> / {{ filtered_results|length }}</span>
            <button class="nav-btn" onclick="navigate('next')" id="nextBtn">Next →</button>
        </div>
    </div>

    <div class="main">
        <div class="sidebar">
            <div class="filter-section">
                <select class="filter-select" id="filter" onchange="applyFilter()">
                    <option value="all" {{ 'selected' if filter == 'all' else '' }}>All ({{ run.metrics.total_photos }})</option>
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
            <div class="image-tabs">
                <button class="image-tab active" data-image="original" onclick="showImage('original')">Original</button>
                <button class="image-tab" data-image="grayscale" onclick="showImage('grayscale')">Grayscale</button>
                <button class="image-tab" data-image="clahe" onclick="showImage('clahe')">CLAHE</button>
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
                        <span id="detailStatus"></span>
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
                        <span id="detailCounts"></span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Time:</span>
                        <span id="detailTime"></span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Tags:</span>
                        <div class="tags-list" id="detailTags"></div>
                    </div>
                    <div class="detail-item">
                        <a href="#" id="editLink" class="nav-link" style="padding: 0;">Edit Labels →</a>
                    </div>
                </div>
            </div>

            <div class="keyboard-hint">
                ← → navigate | 1-6 switch tabs
            </div>
        </div>
    </div>

    <script>
        const photoResults = {{ photo_results_json | safe }};
        const runId = '{{ run.metadata.run_id }}';
        let currentIdx = {{ current_idx }};
        let currentImageType = 'original';

        function selectPhoto(idx) {
            if (idx < 0 || idx >= photoResults.length) return;
            currentIdx = idx;

            document.querySelectorAll('.photo-item').forEach((el, i) => {
                el.classList.toggle('active', i === idx);
            });

            document.getElementById('currentPos').textContent = idx + 1;
            document.getElementById('prevBtn').disabled = idx === 0;
            document.getElementById('nextBtn').disabled = idx === photoResults.length - 1;

            const activeItem = document.querySelector('.photo-item.active');
            if (activeItem) activeItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

            updateDetails();
            updateImage();

            history.replaceState(null, '', `?filter=${document.getElementById('filter').value}&idx=${idx}`);
        }

        function updateDetails() {
            const result = photoResults[currentIdx];

            document.getElementById('detailStatus').innerHTML =
                `<span class="photo-status status-${result.status}">${result.status}</span>`;

            const expectedHtml = result.expected_bibs.map(bib => {
                const isMatch = result.detected_bibs.includes(bib);
                return `<span class="bib ${isMatch ? 'bib-tp' : 'bib-fn'}">${bib}</span>`;
            }).join('') || '<span style="color:#666">none</span>';
            document.getElementById('expectedBibs').innerHTML = expectedHtml;

            const detectedHtml = result.detected_bibs.map(bib => {
                const isMatch = result.expected_bibs.includes(bib);
                return `<span class="bib ${isMatch ? 'bib-tp' : 'bib-fp'}">${bib}</span>`;
            }).join('') || '<span style="color:#666">none</span>';
            document.getElementById('detectedBibs').innerHTML = detectedHtml;

            document.getElementById('detailCounts').textContent = `${result.tp} / ${result.fp} / ${result.fn}`;
            document.getElementById('detailTime').textContent = `${result.detection_time_ms.toFixed(0)}ms`;

            const tagsHtml = result.tags.map(tag => `<span class="tag">${tag}</span>`).join('') || '<span style="color:#666">none</span>';
            document.getElementById('detailTags').innerHTML = tagsHtml;

            const hashPrefix = result.content_hash.substring(0, 16);
            document.getElementById('editLink').href = `{{ url_for('labels_index') }}${hashPrefix}?filter=all`;
        }

        function updateImage() {
            const result = photoResults[currentIdx];
            const hash = result.content_hash;
            const hashPrefix = hash.substring(0, 16);

            let imagePath;
            if (currentImageType === 'original') {
                imagePath = `{{ url_for('serve_photo', content_hash='HASH') }}`.replace('HASH', hash);
            } else {
                imagePath = `{{ url_for('serve_artifact', run_id='RUN', hash_prefix='HASH', image_type='TYPE') }}`
                    .replace('RUN', runId)
                    .replace('HASH', hashPrefix)
                    .replace('TYPE', currentImageType);
            }
            document.getElementById('mainImage').src = imagePath;
        }

        function showImage(imageType) {
            currentImageType = imageType;
            document.querySelectorAll('.image-tab').forEach(tab => {
                tab.classList.toggle('active', tab.dataset.image === imageType);
            });
            updateImage();
        }

        function navigate(direction) {
            const newIdx = direction === 'prev' ? currentIdx - 1 : currentIdx + 1;
            if (newIdx >= 0 && newIdx < photoResults.length) selectPhoto(newIdx);
        }

        function applyFilter() {
            const filter = document.getElementById('filter').value;
            window.location.href = `{{ url_for('benchmark_inspect', run_id=run.metadata.run_id) }}?filter=${filter}`;
        }

        function changeRun() {
            const newRunId = document.getElementById('runSelect').value;
            window.location.href = `{{ url_for('benchmark_list') }}${newRunId}/`;
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft') navigate('prev');
            else if (e.key === 'ArrowRight') navigate('next');
            else if (e.key >= '1' && e.key <= '6') {
                const tabs = ['original', 'grayscale', 'clahe', 'resize', 'candidates', 'detections'];
                const idx = parseInt(e.key) - 1;
                if (idx < tabs.length) showImage(tabs[idx]);
            }
        });

        updateDetails();
        updateImage();
    </script>
</body>
</html>
"""


EMPTY_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>No Photos</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            text-align: center;
        }
        .message { max-width: 500px; }
        h1 { color: #0f9b0f; margin-bottom: 20px; }
        code {
            background: #0f3460;
            padding: 10px 15px;
            border-radius: 4px;
            display: block;
            margin: 20px 0;
        }
    </style>
</head>
<body>
    <div class="message">
        <h1>No Photos Found</h1>
        <p>Run the scanner first to index photos:</p>
        <code>python -m benchmarking.cli scan</code>
    </div>
</body>
</html>
"""


# =============================================================================
# FLASK APP
# =============================================================================

def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # -------------------------------------------------------------------------
    # Index / Root
    # -------------------------------------------------------------------------
    @app.route('/')
    def index():
        """Redirect to labels."""
        return redirect(url_for('labels_index'))

    # -------------------------------------------------------------------------
    # Labeling Routes
    # -------------------------------------------------------------------------
    @app.route('/labels/')
    def labels_index():
        """Show first photo based on filter."""
        filter_type = request.args.get('filter', 'all')
        hashes = get_filtered_hashes(filter_type)

        if not hashes:
            return render_template_string(EMPTY_TEMPLATE)

        return redirect(url_for('label_photo', content_hash=hashes[0][:16], filter=filter_type))

    @app.route('/labels/<content_hash>')
    def label_photo(content_hash):
        """Label a specific photo."""
        filter_type = request.args.get('filter', 'all')
        hashes = get_filtered_hashes(filter_type)

        if not hashes:
            return render_template_string(EMPTY_TEMPLATE)

        full_hash = find_hash_by_prefix(content_hash, hashes)
        if not full_hash:
            return "Photo not found", 404

        gt = load_ground_truth()
        label = gt.get_photo(full_hash)

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

        prev_url = url_for('label_photo', content_hash=hashes[idx - 1][:16], filter=filter_type) if has_prev else None
        next_url = url_for('label_photo', content_hash=hashes[idx + 1][:16], filter=filter_type) if has_next else None

        # Get latest run ID for inspector link
        runs = list_runs()
        latest_run_id = runs[0]['run_id'] if runs else None

        return render_template_string(
            LABELING_TEMPLATE,
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
            filter=filter_type,
            latest_run_id=latest_run_id,
        )

    @app.route('/api/labels', methods=['POST'])
    def save_label():
        """Save a photo label."""
        data = request.get_json()

        content_hash = data.get('content_hash')
        bibs = data.get('bibs', [])
        tags = data.get('tags', [])
        split = data.get('split', 'full')

        if not content_hash:
            return jsonify({'error': 'Missing content_hash'}), 400

        try:
            label = PhotoLabel(
                content_hash=content_hash,
                bibs=bibs,
                tags=tags,
                split=split,
            )
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

        gt = load_ground_truth()
        gt.add_photo(label)
        save_ground_truth(gt)

        return jsonify({'status': 'ok'})

    # -------------------------------------------------------------------------
    # Benchmark Routes
    # -------------------------------------------------------------------------
    @app.route('/benchmark/')
    def benchmark_list():
        """List all benchmark runs."""
        runs = list_runs()
        return render_template_string(BENCHMARK_LIST_TEMPLATE, runs=runs)

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
        } for r in filtered])

        all_runs = list_runs()

        # Get pipeline summary
        pipeline_summary = "unknown"
        if run.metadata.pipeline_config:
            pipeline_summary = run.metadata.pipeline_config.summary()

        return render_template_string(
            BENCHMARK_INSPECT_TEMPLATE,
            run=run,
            filtered_results=filtered,
            current_idx=idx,
            filter=filter_type,
            photo_results_json=photo_results_json,
            all_runs=all_runs,
            pipeline_summary=pipeline_summary,
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

    gt = load_ground_truth()
    labeled_hashes = set(gt.photos.keys())

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

def main():
    """Run the web server."""
    index = load_photo_index()
    if not index:
        print("No photo index found. Run 'python -m benchmarking.cli scan' first.")
        return 1

    app = create_app()

    print("Starting Benchmark Web UI...")
    print(f"Found {len(index)} photos in index")
    print()
    print("Routes:")
    print("  /labels/              - Label photos")
    print("  /benchmark/           - List benchmark runs")
    print("  /benchmark/<run_id>/  - Inspect a run")
    print()
    print("Open http://localhost:30002 in your browser")
    print("Press Ctrl+C to stop")
    app.run(host='localhost', port=30002, debug=False)
    return 0


if __name__ == '__main__':
    sys.exit(main())

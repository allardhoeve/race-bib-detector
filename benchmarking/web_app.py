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
# LABELS HOME TEMPLATE
# =============================================================================

LABELS_HOME_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Benchmark Labeling</title>
    <style>
        """ + COMMON_STYLES + """
        .content {
            flex: 1;
            padding: 60px;
            display: flex;
            flex-direction: column;
            gap: 30px;
        }
        h1 {
            color: #0f9b0f;
            font-size: 28px;
        }
        .cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 20px;
        }
        .card {
            padding: 20px;
            border-radius: 8px;
            background: #16213e;
            border: 1px solid #0f3460;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .card h2 {
            font-size: 18px;
            color: #0f9b0f;
        }
        .card p {
            color: #bbb;
            font-size: 14px;
        }
        .card a {
            display: inline-block;
            margin-top: 10px;
            color: #0f9b0f;
            text-decoration: none;
            font-weight: 600;
        }
        .card a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="header">
        <div class="nav-info">
            <span style="color: #0f9b0f; font-weight: bold;">Benchmark Labeling</span>
        </div>
    </div>

    <div class="content">
        <h1>Choose a labeling mode</h1>
        <div class="cards">
            <div class="card">
                <h2>Bib Labels</h2>
                <p>Label bib numbers and bib-related tags for benchmark scoring.</p>
                <a href="{{ url_for('labels_index') }}">Start Bib Labeling →</a>
            </div>
            <div class="card">
                <h2>Face Labels</h2>
                <p>Label face counts and face-specific tags for face detection checks.</p>
                <a href="{{ url_for('face_labels_index') }}">Start Face Labeling →</a>
            </div>
            <div class="card">
                <h2>Benchmarks</h2>
                <p>Inspect benchmark runs and compare pipeline passes.</p>
                <a href="{{ url_for('benchmark_list') }}">View Benchmarks →</a>
            </div>
        </div>
    </div>
</body>
</html>
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
            gap: 15px;
        }
        .form-section h3 {
            margin-bottom: 8px;
            color: #0f9b0f;
            font-size: 14px;
            text-transform: uppercase;
        }
        .image-panel {
            position: relative;
            padding: 0;
        }
        .canvas-container {
            position: absolute;
            inset: 0;
        }
        .canvas-container img {
            width: 100%;
            height: 100%;
            object-fit: contain;
        }
        .canvas-container canvas {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
        }
        .box-list {
            list-style: none;
            max-height: 150px;
            overflow-y: auto;
        }
        .box-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 6px 8px;
            border-bottom: 1px solid #0f3460;
            cursor: pointer;
            font-size: 13px;
        }
        .box-item:hover { background: #252545; }
        .box-item.selected { background: #0f3460; border-left: 3px solid #0f9b0f; }
        .box-item .box-label { font-family: monospace; }
        .box-item .box-delete {
            color: #ff4444;
            cursor: pointer;
            padding: 2px 6px;
            font-size: 16px;
        }
        .box-editor {
            padding: 10px;
            background: #1a1a2e;
            border-radius: 4px;
            display: none;
        }
        .box-editor.visible { display: block; }
        .box-editor label { font-size: 12px; color: #888; display: block; margin-bottom: 4px; }
        .box-editor input[type=text] {
            width: 100%;
            padding: 8px;
            font-size: 16px;
            border: 2px solid #0f3460;
            border-radius: 4px;
            background: #16213e;
            color: #eee;
            margin-bottom: 8px;
        }
        .box-editor input[type=text]:focus { outline: none; border-color: #0f9b0f; }
        .tag-radios { display: flex; gap: 8px; flex-wrap: wrap; }
        .tag-radios label {
            display: flex;
            align-items: center;
            gap: 4px;
            padding: 4px 8px;
            background: #16213e;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            color: #eee;
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
            <a href="{{ url_for('face_labels_index') }}" class="nav-link">Face Labels →</a>
            <button class="nav-btn" onclick="navigate('prev')" {{ 'disabled' if not has_prev else '' }}>← Prev</button>
            <span class="position">{{ current }} / {{ total }}</span>
            <button class="nav-btn" onclick="navigate('next')" {{ 'disabled' if not has_next else '' }}>Next →</button>
            {% if next_unlabeled_url %}
            <button class="nav-btn" onclick="navigateUnlabeled()">Next unlabeled →→</button>
            {% endif %}
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
            <div class="canvas-container">
                <img id="photo" src="{{ url_for('serve_photo', content_hash=content_hash) }}" alt="Photo">
                <canvas id="canvas"></canvas>
            </div>
        </div>

        <div class="form-panel">
            <div class="form-section">
                <h3>Bib Boxes</h3>
                <ul class="box-list" id="boxList"></ul>
            </div>

            <div class="box-editor" id="boxEditor">
                <label>Bib Number</label>
                <input type="text" id="boxNumber" placeholder="e.g. 123">
                <label>Tag</label>
                <div class="tag-radios" id="boxTagRadios">
                    <label><input type="radio" name="boxTag" value="bib" checked> bib</label>
                    <label><input type="radio" name="boxTag" value="not_bib"> not bib</label>
                    <label><input type="radio" name="boxTag" value="bib_partial"> partial</label>
                </div>
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
                {{ content_hash[:8] }}...
                {% if latest_run_id %}
                <a href="{{ url_for('benchmark_inspect', run_id=latest_run_id, hash=content_hash[:8]) }}"
                   style="color: #0f9b0f; margin-left: 10px;">View in Inspector →</a>
                {% endif %}
            </div>

            <div class="keyboard-hint">
                ← → navigate | Enter save | Del delete box | Tab accept suggestion | O obscured | N no bib | B blurry
            </div>
        </div>
    </div>

    <script src="{{ url_for('serve_static', filename='labeling.js') }}"></script>
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

        function showStatus(message, isError) {
            const status = document.getElementById('status');
            status.textContent = message;
            status.className = 'status ' + (isError ? 'error' : 'success');
            status.style.display = 'block';
            setTimeout(() => { status.style.display = 'none'; }, 2000);
        }

        // --- Box list rendering ---
        function renderBoxList(boxes) {
            const list = document.getElementById('boxList');
            list.innerHTML = '';
            boxes.forEach((box, i) => {
                const li = document.createElement('li');
                li.className = 'box-item' + (i === LabelingUI.getState().selectedIdx ? ' selected' : '');
                li.innerHTML = '<span class="box-label">' +
                    (box.number || '?') + ' [' + (box.tag || 'bib') + ']</span>' +
                    '<span class="box-delete" data-idx="' + i + '">×</span>';
                li.addEventListener('click', function(e) {
                    if (e.target.classList.contains('box-delete')) {
                        LabelingUI.getState().selectedIdx = parseInt(e.target.dataset.idx);
                        LabelingUI.deleteSelected();
                    } else {
                        LabelingUI.selectBox(i);
                    }
                });
                list.appendChild(li);
            });
        }

        function onBoxSelected(idx, box) {
            const editor = document.getElementById('boxEditor');
            if (idx < 0 || !box) {
                editor.classList.remove('visible');
                return;
            }
            editor.classList.add('visible');
            document.getElementById('boxNumber').value = box.number || '';
            const radios = document.querySelectorAll('input[name="boxTag"]');
            radios.forEach(r => { r.checked = r.value === (box.tag || 'bib'); });

            // Update box list selection
            document.querySelectorAll('.box-item').forEach((el, i) => {
                el.classList.toggle('selected', i === idx);
            });

            // Focus number input
            document.getElementById('boxNumber').focus();
        }

        // Update box when editor changes
        document.getElementById('boxNumber').addEventListener('input', function() {
            const state = LabelingUI.getState();
            if (state.selectedIdx >= 0) {
                state.boxes[state.selectedIdx].number = this.value;
                renderBoxList(state.boxes);
                LabelingUI.render();
            }
        });

        document.querySelectorAll('input[name="boxTag"]').forEach(radio => {
            radio.addEventListener('change', function() {
                const state = LabelingUI.getState();
                if (state.selectedIdx >= 0) {
                    state.boxes[state.selectedIdx].tag = this.value;
                    renderBoxList(state.boxes);
                    LabelingUI.render();
                }
            });
        });

        // --- Save ---
        async function save() {
            const state = LabelingUI.getState();
            const data = {
                content_hash: contentHash,
                boxes: state.boxes.map(b => ({
                    x: b.x, y: b.y, w: b.w, h: b.h,
                    number: b.number || '',
                    tag: b.tag || 'bib'
                })),
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

        function navigateUnlabeled() {
            const url = {{ next_unlabeled_url|tojson }};
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
            if (e.target.tagName === 'INPUT' && e.key !== 'Enter' && e.key !== 'Escape') return;

            if (e.key === 'o') { e.preventDefault(); toggleTag('obscured_bib'); return; }
            if (e.key === 'n') { e.preventDefault(); toggleTag('no_bib'); return; }
            if (e.key === 'b') { e.preventDefault(); toggleTag('blurry_bib'); return; }

            if (e.key === 'ArrowLeft') navigate('prev');
            else if (e.key === 'ArrowRight') navigate('next');
            else if (e.key === 'Enter') { e.preventDefault(); save(); }
        });

        // --- Init canvas UI ---
        const img = document.getElementById('photo');
        const canvas = document.getElementById('canvas');

        function startUI() {
            LabelingUI.init({
                mode: 'bib',
                contentHash: contentHash,
                imgEl: img,
                canvasEl: canvas,
                onBoxesChanged: renderBoxList,
                onBoxSelected: onBoxSelected,
            });
        }

        if (img.complete && img.naturalWidth) {
            startUI();
        } else {
            img.addEventListener('load', startUI);
        }
    </script>
</body>
</html>
"""


# =============================================================================
# FACE LABELING UI TEMPLATE
# =============================================================================

FACE_LABELING_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Face Labeling - {{ current }} / {{ total }}</title>
    <style>
        """ + COMMON_STYLES + """
        .form-panel {
            width: 350px;
            padding: 20px;
            background: #16213e;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 15px;
        }
        .form-section h3 {
            margin-bottom: 8px;
            color: #0f9b0f;
            font-size: 14px;
            text-transform: uppercase;
        }
        .image-panel {
            position: relative;
            padding: 0;
        }
        .canvas-container {
            position: absolute;
            inset: 0;
        }
        .canvas-container img {
            width: 100%;
            height: 100%;
            object-fit: contain;
        }
        .canvas-container canvas {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
        }
        .box-list {
            list-style: none;
            max-height: 150px;
            overflow-y: auto;
        }
        .box-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 6px 8px;
            border-bottom: 1px solid #0f3460;
            cursor: pointer;
            font-size: 13px;
        }
        .box-item:hover { background: #252545; }
        .box-item.selected { background: #0f3460; border-left: 3px solid #0f9b0f; }
        .box-item .box-label { font-family: monospace; }
        .box-item .box-delete {
            color: #ff4444;
            cursor: pointer;
            padding: 2px 6px;
            font-size: 16px;
        }
        .box-editor {
            padding: 10px;
            background: #1a1a2e;
            border-radius: 4px;
            display: none;
        }
        .box-editor.visible { display: block; }
        .box-editor label { font-size: 12px; color: #888; display: block; margin-bottom: 4px; }
        .box-editor input[type=text] {
            width: 100%;
            padding: 8px;
            font-size: 14px;
            border: 2px solid #0f3460;
            border-radius: 4px;
            background: #16213e;
            color: #eee;
            margin-bottom: 8px;
        }
        .box-editor input[type=text]:focus { outline: none; border-color: #0f9b0f; }
        .tag-radios { display: flex; gap: 8px; flex-wrap: wrap; }
        .tag-radios label {
            display: flex;
            align-items: center;
            gap: 4px;
            padding: 4px 8px;
            background: #16213e;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            color: #eee;
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
        .face-count-display {
            font-size: 13px;
            color: #888;
            padding: 4px 0;
        }
        .suggestion-chip {
            position: relative;
            padding: 3px 8px;
            background: #0f3460;
            border: 1px solid #1a4a7a;
            border-radius: 12px;
            cursor: pointer;
            font-size: 12px;
            color: #ccc;
            white-space: nowrap;
        }
        .suggestion-chip:hover { background: #1a4a7a; color: #fff; }
        .crop-tooltip {
            display: none;
            position: absolute;
            bottom: 100%;
            left: 50%;
            transform: translateX(-50%);
            margin-bottom: 6px;
            border: 2px solid #1a4a7a;
            border-radius: 4px;
            background: #16213e;
            padding: 2px;
            z-index: 100;
        }
        .crop-tooltip img {
            display: block;
            max-width: 96px;
            max-height: 96px;
        }
        .suggestion-chip:hover .crop-tooltip { display: block; }
        .anon-btn {
            background: #0f3460;
            color: #eee;
            border: none;
            padding: 8px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            white-space: nowrap;
        }
        .anon-btn:hover { background: #1a4a7a; }
    </style>
</head>
<body>
    <div class="header">
        <div class="nav-info">
            <a href="{{ url_for('benchmark_list') }}" class="nav-link">← Benchmarks</a>
            <a href="{{ url_for('labels_index') }}" class="nav-link">Bib Labels →</a>
            <button class="nav-btn" onclick="navigate('prev')" {{ 'disabled' if not has_prev else '' }}>← Prev</button>
            <span class="position">{{ current }} / {{ total }}</span>
            <button class="nav-btn" onclick="navigate('next')" {{ 'disabled' if not has_next else '' }}>Next →</button>
            {% if next_unlabeled_url %}
            <button class="nav-btn" onclick="navigateUnlabeled()">Next unlabeled →→</button>
            {% endif %}
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
            <div class="canvas-container">
                <img id="photo" src="{{ url_for('serve_photo', content_hash=content_hash) }}" alt="Photo">
                <canvas id="canvas"></canvas>
            </div>
        </div>

        <div class="form-panel">
            <div class="form-section">
                <h3>Face Boxes</h3>
                <ul class="box-list" id="boxList"></ul>
                <div class="face-count-display" id="faceCountDisplay">Keep faces: 0</div>
            </div>

            <div class="box-editor" id="boxEditor">
                <label>Scope</label>
                <div class="tag-radios" id="scopeRadios">
                    <label><input type="radio" name="faceScope" value="keep" checked> keep</label>
                    <label><input type="radio" name="faceScope" value="exclude"> exclude</label>
                    <label><input type="radio" name="faceScope" value="uncertain"> uncertain</label>
                </div>
                <label>Identity</label>
                <div style="display:flex;gap:6px;align-items:center;">
                    <input type="text" id="faceIdentity" placeholder="e.g. Alice" list="identityList" style="flex:1;margin-bottom:0;">
                    <button type="button" id="assignAnonBtn" class="anon-btn" onclick="assignAnonymous()">Anon</button>
                </div>
                <datalist id="identityList"></datalist>
                <div id="identitySuggestions" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;"></div>
                <label style="margin-top: 8px;">Box Tags</label>
                <div class="tags-grid" id="boxTagsGrid">
                    {% for tag in face_box_tags %}
                    <div class="tag-checkbox">
                        <input type="checkbox" id="box_tag_{{ tag }}" name="box_tags" value="{{ tag }}">
                        <label for="box_tag_{{ tag }}">{{ tag.replace('_', ' ') }}</label>
                    </div>
                    {% endfor %}
                </div>
            </div>

            <div class="form-section">
                <h3>Photo Tags</h3>
                <div class="tags-grid">
                    {% for tag in all_face_tags %}
                    <div class="tag-checkbox">
                        <input type="checkbox" id="face_tag_{{ tag }}" name="face_tags" value="{{ tag }}"
                               {{ 'checked' if tag in face_tags else '' }}>
                        <label for="face_tag_{{ tag }}">{{ tag.replace('_', ' ') }}</label>
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
                {{ content_hash[:8] }}...
                {% if latest_run_id %}
                <a href="{{ url_for('benchmark_inspect', run_id=latest_run_id, hash=content_hash[:8]) }}"
                   style="color: #0f9b0f; margin-left: 10px;">View in Inspector →</a>
                {% endif %}
            </div>

            <div class="keyboard-hint">
                ← → navigate | Enter save | Del delete box | Tab accept suggestion |
                N no faces | L light
            </div>
        </div>
    </div>

    <script src="{{ url_for('serve_static', filename='labeling.js') }}"></script>
    <script>
        let currentSplit = '{{ split }}';
        const contentHash = '{{ content_hash }}';

        function setSplit(split) {
            currentSplit = split;
            document.querySelectorAll('.split-btn').forEach(btn => {
                btn.classList.toggle('active', btn.textContent.toLowerCase() === split);
            });
        }

        function getSelectedFaceTags() {
            return Array.from(document.querySelectorAll('input[name="face_tags"]:checked'))
                        .map(cb => cb.value);
        }

        function showStatus(message, isError) {
            const status = document.getElementById('status');
            status.textContent = message;
            status.className = 'status ' + (isError ? 'error' : 'success');
            status.style.display = 'block';
            setTimeout(() => { status.style.display = 'none'; }, 2000);
        }

        // --- Identity autocomplete ---
        function loadIdentities() {
            fetch('/api/identities')
                .then(r => r.json())
                .then(data => {
                    const dl = document.getElementById('identityList');
                    dl.innerHTML = '';
                    (data.identities || []).forEach(id => {
                        const opt = document.createElement('option');
                        opt.value = id;
                        dl.appendChild(opt);
                    });
                });
        }

        // --- Assign anonymous identity ---
        async function assignAnonymous() {
            const state = LabelingUI.getState();
            if (state.selectedIdx < 0) return;
            const resp = await fetch('/api/identities');
            const data = await resp.json();
            const existing = (data.identities || [])
                .filter(id => /^anon-\\d+$/.test(id))
                .map(id => parseInt(id.split('-')[1], 10));
            const next = existing.length ? Math.max(...existing) + 1 : 1;
            const name = 'anon-' + next;
            document.getElementById('faceIdentity').value = name;
            state.boxes[state.selectedIdx].identity = name;
            await fetch('/api/identities', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name })
            });
            renderBoxList(state.boxes);
            LabelingUI.render();
            loadIdentities();
        }

        // --- Identity suggestions ---
        let _suggestAbort = null;
        function fetchIdentitySuggestions(box) {
            const container = document.getElementById('identitySuggestions');
            container.innerHTML = '';
            if (!box || !box.w || !box.h) return;
            if (_suggestAbort) _suggestAbort.abort();
            _suggestAbort = new AbortController();
            const params = new URLSearchParams({
                box_x: box.x, box_y: box.y, box_w: box.w, box_h: box.h, k: 5
            });
            fetch('/api/face_identity_suggestions/' + contentHash + '?' + params,
                  {signal: _suggestAbort.signal})
                .then(r => r.json())
                .then(data => {
                    container.innerHTML = '';
                    (data.suggestions || []).forEach(s => {
                        const chip = document.createElement('span');
                        chip.className = 'suggestion-chip';
                        chip.textContent = s.identity + ' ' + Math.round(s.similarity * 100) + '%';
                        if (s.content_hash && s.box_index !== undefined) {
                            const tooltip = document.createElement('span');
                            tooltip.className = 'crop-tooltip';
                            const img = document.createElement('img');
                            img.src = '/api/face_crop/' + s.content_hash + '/' + s.box_index;
                            img.alt = s.identity;
                            tooltip.appendChild(img);
                            chip.appendChild(tooltip);
                        }
                        chip.addEventListener('click', function() {
                            document.getElementById('faceIdentity').value = s.identity;
                            const state = LabelingUI.getState();
                            if (state.selectedIdx >= 0) {
                                state.boxes[state.selectedIdx].identity = s.identity;
                                renderBoxList(state.boxes);
                                LabelingUI.render();
                            }
                        });
                        container.appendChild(chip);
                    });
                })
                .catch(e => { if (e.name !== 'AbortError') console.warn('Suggestion fetch failed:', e); });
        }

        // --- Box list rendering ---
        function renderBoxList(boxes) {
            const list = document.getElementById('boxList');
            list.innerHTML = '';
            boxes.forEach((box, i) => {
                const li = document.createElement('li');
                li.className = 'box-item' + (i === LabelingUI.getState().selectedIdx ? ' selected' : '');
                let label = (box.identity || box.scope || 'keep');
                const boxTags = box.tags || [];
                if (boxTags.length) label += ' [' + boxTags.join(',') + ']';
                li.innerHTML = '<span class="box-label">' + label + '</span>' +
                    '<span class="box-delete" data-idx="' + i + '">×</span>';
                li.addEventListener('click', function(e) {
                    if (e.target.classList.contains('box-delete')) {
                        LabelingUI.getState().selectedIdx = parseInt(e.target.dataset.idx);
                        LabelingUI.deleteSelected();
                    } else {
                        LabelingUI.selectBox(i);
                    }
                });
                list.appendChild(li);
            });

            // Update face count display
            const keepCount = boxes.filter(b => (b.scope || 'keep') === 'keep').length;
            document.getElementById('faceCountDisplay').textContent = 'Keep faces: ' + keepCount;
        }

        function onBoxSelected(idx, box) {
            const editor = document.getElementById('boxEditor');
            if (idx < 0 || !box) {
                editor.classList.remove('visible');
                return;
            }
            editor.classList.add('visible');
            const radios = document.querySelectorAll('input[name="faceScope"]');
            radios.forEach(r => { r.checked = r.value === (box.scope || 'keep'); });
            document.getElementById('faceIdentity').value = box.identity || '';

            // Set box tag checkboxes
            const boxTags = box.tags || [];
            document.querySelectorAll('input[name="box_tags"]').forEach(cb => {
                cb.checked = boxTags.includes(cb.value);
            });

            document.querySelectorAll('.box-item').forEach((el, i) => {
                el.classList.toggle('selected', i === idx);
            });

            document.getElementById('faceIdentity').focus();

            // Fetch identity suggestions if identity is empty
            if (!box.identity) {
                fetchIdentitySuggestions(box);
            } else {
                document.getElementById('identitySuggestions').innerHTML = '';
            }
        }

        // Update box when editor changes
        document.getElementById('faceIdentity').addEventListener('input', function() {
            const state = LabelingUI.getState();
            if (state.selectedIdx >= 0) {
                state.boxes[state.selectedIdx].identity = this.value;
                renderBoxList(state.boxes);
                LabelingUI.render();
            }
        });

        document.querySelectorAll('input[name="faceScope"]').forEach(radio => {
            radio.addEventListener('change', function() {
                const state = LabelingUI.getState();
                if (state.selectedIdx >= 0) {
                    state.boxes[state.selectedIdx].scope = this.value;
                    renderBoxList(state.boxes);
                    LabelingUI.render();
                }
            });
        });

        document.querySelectorAll('input[name="box_tags"]').forEach(cb => {
            cb.addEventListener('change', function() {
                const state = LabelingUI.getState();
                if (state.selectedIdx >= 0) {
                    const tags = Array.from(document.querySelectorAll('input[name="box_tags"]:checked'))
                        .map(c => c.value);
                    state.boxes[state.selectedIdx].tags = tags;
                    renderBoxList(state.boxes);
                    LabelingUI.render();
                }
            });
        });

        // --- Save ---
        async function save() {
            const state = LabelingUI.getState();

            // Auto-add new identities
            const newIdentities = state.boxes
                .filter(b => b.identity && b.identity.trim())
                .map(b => b.identity.trim());
            for (const name of new Set(newIdentities)) {
                await fetch('/api/identities', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name })
                });
            }

            const data = {
                content_hash: contentHash,
                boxes: state.boxes.map(b => ({
                    x: b.x, y: b.y, w: b.w, h: b.h,
                    scope: b.scope || 'keep',
                    identity: b.identity || undefined,
                    tags: (b.tags && b.tags.length) ? b.tags : undefined
                })),
                face_tags: getSelectedFaceTags(),
                split: currentSplit
            };

            try {
                const response = await fetch('{{ url_for("save_face_label") }}', {
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

        function navigateUnlabeled() {
            const url = {{ next_unlabeled_url|tojson }};
            if (url) window.location.href = url;
        }

        function applyFilter() {
            const newFilter = document.getElementById('filter').value;
            window.location.href = '{{ url_for("face_labels_index") }}?filter=' + newFilter;
        }

        function toggleFaceTag(tagName) {
            const checkbox = document.getElementById('face_tag_' + tagName);
            if (checkbox) checkbox.checked = !checkbox.checked;
        }

        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT' && e.key !== 'Enter' && e.key !== 'Escape') return;

            if (e.key === 'n') { e.preventDefault(); toggleFaceTag('no_faces'); return; }
            if (e.key === 'l') { e.preventDefault(); toggleFaceTag('light_faces'); return; }

            if (e.key === 'ArrowLeft') navigate('prev');
            else if (e.key === 'ArrowRight') navigate('next');
            else if (e.key === 'Enter') { e.preventDefault(); save(); }
        });

        // --- Init canvas UI ---
        const img = document.getElementById('photo');
        const canvas = document.getElementById('canvas');

        function startUI() {
            LabelingUI.init({
                mode: 'face',
                contentHash: contentHash,
                imgEl: img,
                canvasEl: canvas,
                onBoxesChanged: renderBoxList,
                onBoxSelected: onBoxSelected,
            });
            loadIdentities();
        }

        if (img.complete && img.naturalWidth) {
            startUI();
        } else {
            img.addEventListener('load', startUI);
        }
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
                    <th>Passes</th>
                    <th>Note</th>
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
                    <td><span class="pipeline-badge">{{ run.passes or 'unknown' }}</span></td>
                    <td>{{ run.note or '' }}</td>
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
        .note-info { background: #16213e; border: 1px solid #0f3460; }
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
        .image-tab.declined {
            background: #141426;
            border-color: #2a2a40;
            color: #555;
            cursor: not-allowed;
            opacity: 0.7;
        }
        .image-tab.declined:hover { background: #141426; color: #555; }
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
                        {{ r.run_id }} ({{ r.timestamp[:10] }}) - {{ r.split }} [{{ r.pipeline or 'unknown' }} | {{ r.passes or 'unknown' }}]{% if r.note %} - {{ r.note }}{% endif %}
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
                <span class="metric pipeline-info">
                    <span class="metric-label">Passes:</span>
                    <span class="metric-value">{{ passes_summary }}</span>
                </span>
                {% if run.metadata.note %}
                <span class="metric note-info">
                    <span class="metric-label">Note:</span>
                    <span class="metric-value">{{ run.metadata.note }}</span>
                </span>
                {% endif %}
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
                    data-hash="{{ result.content_hash[:8] }}">
                    <span class="photo-hash">{{ result.content_hash[:8] }}...</span>
                    <span class="photo-status status-{{ result.status }}">{{ result.status }}</span>
                </li>
                {% endfor %}
            </ul>
        </div>

        <div class="content">
            <div class="image-tabs" id="imageTabs">
                <!-- Tabs are dynamically generated based on available artifacts -->
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
                ← → navigate | 1-N switch tabs
            </div>
        </div>
    </div>

    <script>
        const photoResults = {{ photo_results_json | safe }};
        const runId = '{{ run.metadata.run_id }}';
        let currentIdx = {{ current_idx }};
        let currentImageType = 'original';
        let availableTabs = [];

        // All possible tabs in order, with display names
        const allTabs = [
            { key: 'original', label: 'Original', alwaysShow: true },
            { key: 'grayscale', label: 'Grayscale', alwaysShow: false },
            { key: 'clahe', label: 'CLAHE', alwaysShow: false },
            { key: 'resize', label: 'Resized', alwaysShow: false },
            { key: 'candidates', label: 'Candidates', alwaysShow: false },
            { key: 'detections', label: 'Detections', alwaysShow: false },
        ];

        function updateTabs() {
            const result = photoResults[currentIdx];
            const artifacts = result.artifact_paths || {};
            const preprocess = result.preprocess_metadata || {};
            const steps = preprocess.steps || {};
            const claheStep = steps.clahe || {};
            const claheDeclined = claheStep.status === 'declined';

            const displayTabs = allTabs.filter(tab =>
                tab.alwaysShow || artifacts[tab.key] || (tab.key === 'clahe' && claheDeclined)
            );
            availableTabs = displayTabs
                .filter(tab => tab.alwaysShow || artifacts[tab.key])
                .map(tab => tab.key);

            // Render tabs
            const tabsContainer = document.getElementById('imageTabs');
            tabsContainer.innerHTML = displayTabs
                .map((tab) => {
                    const hasArtifact = Boolean(artifacts[tab.key]);
                    const isDeclined = tab.key === 'clahe' && claheDeclined && !hasArtifact;
                    const isActive = tab.key === currentImageType;
                    const shortcutIndex = availableTabs.indexOf(tab.key);
                    const shortcut = shortcutIndex === -1 ? null : shortcutIndex + 1;
                    const classes = [
                        'image-tab',
                        isActive ? 'active' : '',
                        isDeclined ? 'declined' : '',
                    ].filter(Boolean).join(' ');
                    const claheMetrics = claheStep.metrics || {};
                    const rangeValue = claheMetrics.dynamic_range ?? 'n/a';
                    const thresholdValue = claheMetrics.threshold ?? 'n/a';
                    const title = isDeclined
                        ? `CLAHE declined (range=${rangeValue}, threshold=${thresholdValue})`
                        : '';
                    const onclick = isDeclined ? '' : `onclick="showImage('${tab.key}')"`;
                    const disabled = isDeclined ? 'disabled' : '';
                    const shortcutText = shortcut === null ? '' : ` <span style="color:#666;font-size:11px">(${shortcut})</span>`;
                    const declinedText = isDeclined ? ' <span style="color:#555;font-size:11px">(declined)</span>' : '';
                    return `<button class="${classes}" data-image="${tab.key}" ${onclick} ${disabled} title="${title}">${tab.label}${declinedText}${shortcutText}</button>`;
                }).join('');

            // If current image type is not available, switch to original
            if (!availableTabs.includes(currentImageType)) {
                currentImageType = 'original';
            }
        }

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

            updateTabs();
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

            const hashPrefix = result.content_hash.substring(0, 8);
            document.getElementById('editLink').href = `{{ url_for('labels_index') }}${hashPrefix}?filter=all`;
        }

        function updateImage() {
            const result = photoResults[currentIdx];
            const hash = result.content_hash;
            const hashPrefix = hash.substring(0, 8);

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
            else if (e.key >= '1' && e.key <= '9') {
                const idx = parseInt(e.key) - 1;
                if (idx < availableTabs.length) showImage(availableTabs[idx]);
            }
        });

        updateTabs();
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
        """Landing page for label UIs."""
        return render_template_string(LABELS_HOME_TEMPLATE)

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
            return render_template_string(EMPTY_TEMPLATE)

        return redirect(url_for('label_photo', content_hash=hashes[0][:8], filter=filter_type))

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
            next_unlabeled_url=next_unlabeled_url,
            filter=filter_type,
            latest_run_id=latest_run_id,
        )

    @app.route('/api/labels', methods=['POST'])
    def save_label():
        """Save a photo label.

        Accepts either ``boxes`` (list of {x,y,w,h,number,tag} dicts) or
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
                boxes = [BibBox(x=0, y=0, w=0, h=0, number=str(b), tag="bib") for b in bibs]
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
            return render_template_string(EMPTY_TEMPLATE)

        return redirect(url_for('face_label_photo', content_hash=hashes[0][:8], filter=filter_type))

    @app.route('/faces/labels/<content_hash>')
    def face_label_photo(content_hash):
        """Label face count/tags for a specific photo."""
        filter_type = request.args.get('filter', 'all')
        hashes = get_filtered_face_hashes(filter_type)

        if not hashes:
            return render_template_string(EMPTY_TEMPLATE)

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

        return render_template_string(
            FACE_LABELING_TEMPLATE,
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

        return render_template_string(
            BENCHMARK_INSPECT_TEMPLATE,
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

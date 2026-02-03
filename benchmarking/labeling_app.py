#!/usr/bin/env python3
"""
Flask application for benchmark labeling UI.

A fast, simple interface for labeling photos with bib numbers and tags.
"""

import random
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template_string, send_from_directory, request, jsonify, redirect, url_for

from benchmarking.ground_truth import (
    load_ground_truth,
    save_ground_truth,
    PhotoLabel,
    ALLOWED_TAGS,
    ALLOWED_SPLITS,
)
from benchmarking.photo_index import load_photo_index, get_path_for_hash
from config import ITERATION_SPLIT_PROBABILITY

# Photos directory
PHOTOS_DIR = Path(__file__).parent.parent / "photos"


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Benchmark Labeling - {{ current }} / {{ total }}</title>
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
        .image-panel {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            background: #0d0d1a;
        }
        .image-panel img {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
        }
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
        .split-buttons {
            display: flex;
            gap: 10px;
        }
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
        .split-btn.active {
            border-color: #0f9b0f;
            background: #0f3460;
        }
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
        .save-btn:disabled { background: #555; cursor: not-allowed; }
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
            word-break: break-all;
        }
        .keyboard-hint {
            font-size: 12px;
            color: #666;
            text-align: center;
            padding: 10px;
            border-top: 1px solid #0f3460;
        }
        .filter-section {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        .filter-select {
            padding: 6px 10px;
            background: #1a1a2e;
            border: 1px solid #0f3460;
            color: #eee;
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="nav-info">
            <button class="nav-btn" onclick="navigate('prev')" {{ 'disabled' if not has_prev else '' }}>← Prev</button>
            <span class="position">{{ current }} / {{ total }}</span>
            <button class="nav-btn" onclick="navigate('next')" {{ 'disabled' if not has_next else '' }}>Next →</button>
        </div>
        <div class="filter-section">
            <label>Filter:</label>
            <select class="filter-select" id="filter" onchange="applyFilter()">
                <option value="all" {{ 'selected' if filter == 'all' else '' }}>All photos</option>
                <option value="unlabeled" {{ 'selected' if filter == 'unlabeled' else '' }}>Unlabeled only</option>
                <option value="labeled" {{ 'selected' if filter == 'labeled' else '' }}>Labeled only</option>
            </select>
        </div>
    </div>

    <div class="main">
        <div class="image-panel">
            <img src="/photo_image/{{ content_hash }}" alt="Photo">
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

            <div class="hash-display">{{ content_hash }}</div>

            <div class="keyboard-hint">
                ⌘← ⌘→ navigate | Enter save | Esc clear | ⌘O obscured | ⌘N no bib | ⌘B blurry
            </div>
        </div>
    </div>

    <script>
        let currentSplit = '{{ split }}';
        const contentHash = '{{ content_hash }}';
        const filter = '{{ filter }}';

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
            // Split on comma, space, or any combination
            return input.split(/[\s,]+/)
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
                const response = await fetch('/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                if (response.ok) {
                    showStatus('Saved!', false);
                    // Auto-advance to next after short delay
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
            const url = direction === 'prev' ? '{{ prev_url }}' : '{{ next_url }}';
            if (url) window.location.href = url;
        }

        function applyFilter() {
            const newFilter = document.getElementById('filter').value;
            window.location.href = '/?filter=' + newFilter;
        }

        function toggleTag(tagName) {
            const checkbox = document.getElementById('tag_' + tagName);
            if (checkbox) {
                checkbox.checked = !checkbox.checked;
            }
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            const mod = e.metaKey || e.ctrlKey;

            // Cmd/Ctrl + Arrow always navigates, even in input
            if (mod && e.key === 'ArrowLeft') {
                e.preventDefault();
                navigate('prev');
                return;
            }
            if (mod && e.key === 'ArrowRight') {
                e.preventDefault();
                navigate('next');
                return;
            }

            // Cmd/Ctrl + letter for quick tag toggles (work even in input)
            if (mod && e.key === 'o') {
                e.preventDefault();
                toggleTag('obscured_bib');
                return;
            }
            if (mod && e.key === 'n') {
                e.preventDefault();
                toggleTag('no_bib');
                return;
            }
            if (mod && e.key === 'b') {
                e.preventDefault();
                toggleTag('blurry_bib');
                return;
            }

            // Don't intercept other keys when typing in input
            if (e.target.tagName === 'INPUT' && e.key !== 'Enter' && e.key !== 'Escape') {
                return;
            }

            if (e.key === 'ArrowLeft') {
                navigate('prev');
            } else if (e.key === 'ArrowRight') {
                navigate('next');
            } else if (e.key === 'Enter') {
                e.preventDefault();
                save();
            } else if (e.key === 'Escape') {
                document.getElementById('bibs').value = '';
                document.getElementById('bibs').focus();
            }
        });

        // Focus bibs input on load
        document.getElementById('bibs').focus();
    </script>
</body>
</html>
"""

EMPTY_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Benchmark Labeling</title>
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


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    @app.route('/')
    def index():
        """Show first photo based on filter."""
        filter_type = request.args.get('filter', 'all')
        hashes = get_filtered_hashes(filter_type)

        if not hashes:
            return render_template_string(EMPTY_TEMPLATE)

        return redirect(url_for('label_photo', content_hash=hashes[0][:16], filter=filter_type))

    @app.route('/label/<content_hash>')
    def label_photo(content_hash):
        """Label a specific photo."""
        filter_type = request.args.get('filter', 'all')
        hashes = get_filtered_hashes(filter_type)

        if not hashes:
            return render_template_string(EMPTY_TEMPLATE)

        # Find full hash from prefix
        full_hash = find_hash_by_prefix(content_hash, hashes)
        if not full_hash:
            return "Photo not found", 404

        # Get existing label if any
        gt = load_ground_truth()
        label = gt.get_photo(full_hash)

        # For new photos, randomly assign split based on configured probability
        if label:
            default_split = label.split
        else:
            default_split = 'iteration' if random.random() < ITERATION_SPLIT_PROBABILITY else 'full'

        # Find position
        try:
            idx = hashes.index(full_hash)
        except ValueError:
            return "Photo not in current filter", 404

        total = len(hashes)
        has_prev = idx > 0
        has_next = idx < total - 1

        prev_url = url_for('label_photo', content_hash=hashes[idx - 1][:16], filter=filter_type) if has_prev else None
        next_url = url_for('label_photo', content_hash=hashes[idx + 1][:16], filter=filter_type) if has_next else None

        return render_template_string(
            HTML_TEMPLATE,
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
        )

    @app.route('/photo_image/<content_hash>')
    def serve_photo(content_hash):
        """Serve photo by content hash."""
        index = load_photo_index()

        # Find full hash from prefix
        full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
        if not full_hash:
            return "Not found", 404

        path = get_path_for_hash(full_hash, PHOTOS_DIR, index)
        if not path or not path.exists():
            return "Not found", 404

        return send_from_directory(path.parent, path.name)

    @app.route('/save', methods=['POST'])
    def save_label():
        """Save a photo label."""
        data = request.get_json()

        content_hash = data.get('content_hash')
        bibs = data.get('bibs', [])
        tags = data.get('tags', [])
        split = data.get('split', 'full')

        if not content_hash:
            return jsonify({'error': 'Missing content_hash'}), 400

        # Validate
        try:
            label = PhotoLabel(
                content_hash=content_hash,
                bibs=bibs,
                tags=tags,
                split=split,
            )
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

        # Save
        gt = load_ground_truth()
        gt.add_photo(label)
        save_ground_truth(gt)

        return jsonify({'status': 'ok'})

    return app


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
        # Try exact match first
        for h in matches:
            if h == prefix:
                return h
        return matches[0]  # Return first match
    return None


def main():
    """Run the labeling web server."""
    # Check if index exists
    index = load_photo_index()
    if not index:
        print("No photo index found. Run 'python -m benchmarking.cli scan' first.")
        return 1

    app = create_app()

    print("Starting Benchmark Labeling UI...")
    print(f"Found {len(index)} photos in index")
    print("Open http://localhost:30002 in your browser")
    print("Press Ctrl+C to stop")
    app.run(host='localhost', port=30002, debug=False)
    return 0


if __name__ == '__main__':
    sys.exit(main())

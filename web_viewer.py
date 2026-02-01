#!/usr/bin/env python
"""Web interface for viewing scanned photos and detected bib numbers."""

from pathlib import Path

from flask import Flask, render_template_string, send_from_directory, abort

from db import get_connection, migrate_add_photo_hash
from utils import GRAY_BBOX_DIR

app = Flask(__name__)

# Path to the cache directory
CACHE_DIR = Path(__file__).parent / "cache"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bib Scanner - Photo {{ current }} of {{ total }}</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }

        header {
            text-align: center;
            padding: 20px 0 30px;
        }

        h1 {
            font-size: 1.8rem;
            font-weight: 600;
            color: #fff;
            margin-bottom: 8px;
        }

        .subtitle {
            color: #8892b0;
            font-size: 1rem;
        }

        .main-content {
            display: flex;
            gap: 30px;
            align-items: flex-start;
        }

        .image-section {
            flex: 1;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 20px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .image-tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 16px;
        }

        .image-tab {
            flex: 1;
            padding: 12px 16px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            color: #8892b0;
            cursor: pointer;
            text-align: center;
            font-size: 0.9rem;
            transition: all 0.2s;
        }

        .image-tab:hover {
            background: rgba(255, 255, 255, 0.1);
        }

        .image-tab.active {
            background: rgba(100, 255, 218, 0.15);
            border-color: #64ffda;
            color: #64ffda;
        }

        .image-container {
            position: relative;
            width: 100%;
            border-radius: 12px;
            overflow: hidden;
            background: #0a0a0a;
        }

        .image-container img {
            width: 100%;
            height: auto;
            display: block;
        }

        .image-view {
            display: none;
        }

        .image-view.active {
            display: block;
        }

        .sidebar {
            width: 320px;
            flex-shrink: 0;
        }

        .bib-card {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 24px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            margin-bottom: 20px;
        }

        .bib-card h2 {
            font-size: 1rem;
            color: #8892b0;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 16px;
        }

        .bib-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .bib-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: rgba(255, 255, 255, 0.08);
            padding: 16px 20px;
            border-radius: 12px;
            transition: transform 0.2s, background 0.2s;
        }

        .bib-item:hover {
            transform: translateX(4px);
            background: rgba(255, 255, 255, 0.12);
        }

        .bib-number {
            font-size: 2rem;
            font-weight: 700;
            color: #64ffda;
        }

        .confidence {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
        }

        .confidence-label {
            font-size: 0.75rem;
            color: #8892b0;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .confidence-value {
            font-size: 1.25rem;
            font-weight: 600;
        }

        .confidence-high { color: #64ffda; }
        .confidence-medium { color: #ffd93d; }
        .confidence-low { color: #ff6b6b; }

        .confidence-bar {
            width: 80px;
            height: 4px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 2px;
            margin-top: 6px;
            overflow: hidden;
        }

        .confidence-fill {
            height: 100%;
            border-radius: 2px;
            transition: width 0.3s ease;
        }

        .no-bibs {
            text-align: center;
            padding: 30px;
            color: #8892b0;
        }

        .no-bibs-icon {
            font-size: 3rem;
            margin-bottom: 12px;
            opacity: 0.5;
        }

        .navigation {
            display: flex;
            gap: 12px;
        }

        .nav-btn {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 16px 24px;
            border: none;
            border-radius: 12px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            text-decoration: none;
        }

        .nav-btn-prev {
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
        }

        .nav-btn-prev:hover:not(.disabled) {
            background: rgba(255, 255, 255, 0.2);
        }

        .nav-btn-next {
            background: #64ffda;
            color: #1a1a2e;
        }

        .nav-btn-next:hover:not(.disabled) {
            background: #4ad4b5;
            transform: translateY(-2px);
        }

        .nav-btn.disabled {
            opacity: 0.3;
            cursor: not-allowed;
            pointer-events: none;
        }

        .nav-arrow {
            font-size: 1.2rem;
        }

        .photo-info {
            margin-top: 16px;
            padding: 16px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            font-size: 0.85rem;
            color: #8892b0;
        }

        .photo-info-row {
            display: flex;
            justify-content: space-between;
            padding: 4px 0;
        }

        .photo-info-label {
            color: #5a6480;
        }

        .keyboard-hint {
            text-align: center;
            margin-top: 20px;
            padding: 12px;
            background: rgba(255, 255, 255, 0.03);
            border-radius: 8px;
            font-size: 0.8rem;
            color: #5a6480;
        }

        kbd {
            display: inline-block;
            padding: 4px 8px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
            font-family: monospace;
            margin: 0 4px;
        }

        @media (max-width: 900px) {
            .main-content {
                flex-direction: column;
            }

            .sidebar {
                width: 100%;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Bib Number Scanner</h1>
            <p class="subtitle">Photo {{ current }} of {{ total }}</p>
        </header>

        <div class="main-content">
            <div class="image-section">
                {% if photo.cache_path %}
                <div class="image-tabs">
                    <div class="image-tab active" onclick="showImage('original')">Original</div>
                    <div class="image-tab {% if not photo.has_gray_bbox %}disabled{% endif %}" onclick="showImage('bbox')" {% if not photo.has_gray_bbox %}style="opacity: 0.4; cursor: not-allowed;"{% endif %}>
                        Bounding Boxes {% if not photo.has_gray_bbox %}(none){% endif %}
                    </div>
                </div>
                {% endif %}

                <div class="image-container">
                    {% if photo.is_local %}
                    <div id="view-original" class="image-view active">
                        <img src="/local/{{ photo.photo_hash }}" alt="Photo {{ current }}">
                    </div>
                    <div id="view-bbox" class="image-view">
                        {% if photo.has_gray_bbox %}
                        <img src="/cache/gray_bounding/{{ photo.cache_filename }}" alt="Photo {{ current }} with bounding boxes">
                        {% else %}
                        <div style="padding: 100px; text-align: center; color: #8892b0;">
                            <p>No bounding box image available</p>
                        </div>
                        {% endif %}
                    </div>
                    {% elif photo.cache_path %}
                    <div id="view-original" class="image-view active">
                        <img src="/cache/{{ photo.cache_filename }}" alt="Photo {{ current }}">
                    </div>
                    <div id="view-bbox" class="image-view">
                        {% if photo.has_gray_bbox %}
                        <img src="/cache/gray_bounding/{{ photo.cache_filename }}" alt="Photo {{ current }} with bounding boxes">
                        {% else %}
                        <div style="padding: 100px; text-align: center; color: #8892b0;">
                            <p>No bounding box image available</p>
                        </div>
                        {% endif %}
                    </div>
                    {% else %}
                    <div style="padding: 100px; text-align: center; color: #8892b0;">
                        <p>Image not cached locally</p>
                        <p style="margin-top: 10px; font-size: 0.8rem;">
                            <a href="{{ photo.photo_url }}=w1200" target="_blank" style="color: #64ffda;">View on Google Photos</a>
                        </p>
                    </div>
                    {% endif %}
                </div>

                <div class="photo-info">
                    <div class="photo-info-row">
                        <span class="photo-info-label">Photo Hash</span>
                        <span style="font-family: monospace; color: #64ffda;">{{ photo.photo_hash }}</span>
                    </div>
                    <div class="photo-info-row">
                        <span class="photo-info-label">Scanned</span>
                        <span>{{ photo.scanned_at or 'Unknown' }}</span>
                    </div>
                </div>
            </div>

            <div class="sidebar">
                <div class="bib-card">
                    <h2>Detected Bibs</h2>
                    {% if bibs %}
                    <div class="bib-list">
                        {% for bib in bibs %}
                        <div class="bib-item">
                            <span class="bib-number">{{ bib.bib_number }}</span>
                            <div class="confidence">
                                <span class="confidence-label">Confidence</span>
                                <span class="confidence-value {% if bib.confidence >= 0.8 %}confidence-high{% elif bib.confidence >= 0.5 %}confidence-medium{% else %}confidence-low{% endif %}">
                                    {{ "%.0f"|format(bib.confidence * 100) }}%
                                </span>
                                <div class="confidence-bar">
                                    <div class="confidence-fill {% if bib.confidence >= 0.8 %}confidence-high{% elif bib.confidence >= 0.5 %}confidence-medium{% else %}confidence-low{% endif %}"
                                         style="width: {{ bib.confidence * 100 }}%; background: currentColor;"></div>
                                </div>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                    {% else %}
                    <div class="no-bibs">
                        <div class="no-bibs-icon">🏃</div>
                        <p>No bib numbers detected</p>
                    </div>
                    {% endif %}
                </div>

                <div class="navigation">
                    <a href="/photo/{{ prev_hash }}" class="nav-btn nav-btn-prev {% if not has_prev %}disabled{% endif %}">
                        <span class="nav-arrow">←</span>
                        <span>Previous</span>
                    </a>
                    <a href="/photo/{{ next_hash }}" class="nav-btn nav-btn-next {% if not has_next %}disabled{% endif %}">
                        <span>Next</span>
                        <span class="nav-arrow">→</span>
                    </a>
                </div>

                <div class="keyboard-hint">
                    Use <kbd>←</kbd> <kbd>→</kbd> arrow keys to navigate
                </div>
            </div>
        </div>
    </div>

    <script>
        function showImage(view) {
            // Don't switch to unavailable views
            if (view === 'bbox' && !{{ 'true' if photo.has_gray_bbox else 'false' }}) {
                return;
            }

            // Update tabs
            document.querySelectorAll('.image-tab').forEach(tab => tab.classList.remove('active'));
            event.target.classList.add('active');

            // Update views
            document.querySelectorAll('.image-view').forEach(v => v.classList.remove('active'));
            document.getElementById('view-' + view).classList.add('active');
        }

        document.addEventListener('keydown', function(e) {
            if (e.key === 'ArrowLeft' && {{ 'true' if has_prev else 'false' }}) {
                window.location.href = '/photo/{{ prev_hash }}';
            } else if (e.key === 'ArrowRight' && {{ 'true' if has_next else 'false' }}) {
                window.location.href = '/photo/{{ next_hash }}';
            } else if (e.key === 'b' || e.key === 'B') {
                // Toggle bounding box view with 'b' key
                const bboxTab = document.querySelectorAll('.image-tab')[1];
                const originalTab = document.querySelectorAll('.image-tab')[0];
                if (bboxTab && !bboxTab.style.opacity) {
                    if (document.getElementById('view-bbox').classList.contains('active')) {
                        originalTab.click();
                    } else {
                        bboxTab.click();
                    }
                }
            }
        });
    </script>
</body>
</html>
"""

EMPTY_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bib Scanner - No Photos</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
        }
        .message {
            text-align: center;
            padding: 40px;
        }
        .icon {
            font-size: 4rem;
            margin-bottom: 20px;
            opacity: 0.5;
        }
        h1 {
            font-size: 1.5rem;
            margin-bottom: 12px;
        }
        p {
            color: #8892b0;
        }
        code {
            display: block;
            margin-top: 20px;
            padding: 16px 24px;
            background: rgba(255,255,255,0.1);
            border-radius: 8px;
            font-family: monospace;
        }
    </style>
</head>
<body>
    <div class="message">
        <div class="icon">📷</div>
        <h1>No Photos Scanned Yet</h1>
        <p>Run the scanner first to add photos to the database.</p>
        <code>python scan_album.py &lt;album_url&gt;</code>
    </div>
</body>
</html>
"""


def get_all_photo_hashes():
    """Get all photo hashes in order (by id for consistent ordering)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT photo_hash FROM photos ORDER BY id")
    hashes = [row[0] for row in cursor.fetchall()]
    conn.close()
    return hashes


def get_photo_with_bibs(photo_hash):
    """Get photo details and its bib detections by hash."""
    conn = get_connection()
    cursor = conn.cursor()

    # Get photo details
    cursor.execute(
        "SELECT id, photo_hash, album_url, photo_url, thumbnail_url, cache_path, scanned_at FROM photos WHERE photo_hash = ?",
        (photo_hash,)
    )
    photo_row = cursor.fetchone()

    if not photo_row:
        conn.close()
        return None, []

    photo = dict(photo_row)

    # Determine if this is a local file or cached remote image
    photo_url = photo['photo_url']
    is_local = photo_url.startswith('/') or photo_url.startswith('file://')

    if is_local:
        # Local file - use photo_url directly
        # Clean up file:// prefix if present
        local_path = photo_url.replace('file://', '') if photo_url.startswith('file://') else photo_url
        photo['is_local'] = True
        photo['local_path'] = local_path
        photo['cache_filename'] = Path(photo['cache_path']).name if photo['cache_path'] else None
    else:
        # Remote image - use cache
        photo['is_local'] = False
        photo['local_path'] = None
        if photo['cache_path']:
            photo['cache_filename'] = Path(photo['cache_path']).name
        else:
            photo['cache_filename'] = None

    # Check if grayscale bounding box image exists
    if photo['cache_filename']:
        gray_bbox_path = GRAY_BBOX_DIR / photo['cache_filename']
        photo['has_gray_bbox'] = gray_bbox_path.exists()
    else:
        photo['has_gray_bbox'] = False

    # Get bib detections for this photo
    cursor.execute(
        "SELECT bib_number, confidence, bbox_json FROM bib_detections WHERE photo_id = ? ORDER BY confidence DESC",
        (photo['id'],)
    )
    bibs = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return photo, bibs


@app.route('/')
def index():
    """Redirect to first photo or show empty state."""
    photo_hashes = get_all_photo_hashes()
    if not photo_hashes:
        return render_template_string(EMPTY_TEMPLATE)
    return app.redirect(f'/photo/{photo_hashes[0]}')


@app.route('/photo/<photo_hash>')
def view_photo(photo_hash):
    """View a specific photo with its bib detections by hash."""
    photo_hashes = get_all_photo_hashes()

    if not photo_hashes:
        return render_template_string(EMPTY_TEMPLATE)

    photo, bibs = get_photo_with_bibs(photo_hash)

    if not photo:
        abort(404)

    # Find position in list
    try:
        current_index = photo_hashes.index(photo_hash)
    except ValueError:
        abort(404)

    total = len(photo_hashes)
    has_prev = current_index > 0
    has_next = current_index < total - 1
    prev_hash = photo_hashes[current_index - 1] if has_prev else photo_hash
    next_hash = photo_hashes[current_index + 1] if has_next else photo_hash

    return render_template_string(
        HTML_TEMPLATE,
        photo=photo,
        bibs=bibs,
        current=current_index + 1,
        total=total,
        has_prev=has_prev,
        has_next=has_next,
        prev_hash=prev_hash,
        next_hash=next_hash,
    )


@app.route('/cache/<filename>')
def serve_cache(filename):
    """Serve cached images."""
    return send_from_directory(CACHE_DIR, filename)


@app.route('/local/<photo_hash>')
def serve_local(photo_hash):
    """Serve local image files by their photo hash."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT photo_url FROM photos WHERE photo_hash = ?", (photo_hash,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        abort(404)

    photo_url = row[0]
    # Handle file:// prefix if present
    local_path = photo_url.replace('file://', '') if photo_url.startswith('file://') else photo_url

    # Verify path exists and is a file
    path = Path(local_path)
    if not path.is_file():
        abort(404)

    return send_from_directory(path.parent, path.name)


@app.route('/cache/gray_bounding/<filename>')
def serve_gray_bbox(filename):
    """Serve grayscale bounding box images."""
    return send_from_directory(GRAY_BBOX_DIR, filename)


def main():
    """Run the web server."""
    # Ensure database has photo hashes (migrate if needed)
    conn = get_connection()
    migrate_add_photo_hash(conn)
    conn.close()

    print("Starting Bib Scanner Web Viewer...")
    print("Open http://localhost:30001 in your browser")
    print("Press Ctrl+C to stop")
    app.run(host='localhost', port=30001, debug=False)


if __name__ == '__main__':
    main()

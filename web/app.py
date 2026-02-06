"""
Flask application for the bib scanner web interface.
"""

import json
import logging
from pathlib import Path

from flask import Flask, render_template_string, send_from_directory, abort

from db import get_connection, migrate_add_photo_hash
from logging_utils import configure_logging
from utils import compute_bbox_hash
from .templates import HTML_TEMPLATE, EMPTY_TEMPLATE

logger = logging.getLogger(__name__)

# Paths
CACHE_DIR = Path(__file__).parent.parent / "cache"
GRAY_BBOX_DIR = CACHE_DIR / "gray_bounding"
CANDIDATES_DIR = CACHE_DIR / "candidates"
SNIPPETS_DIR = CACHE_DIR / "snippets"


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

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

    @app.route('/cache/snippets/<filename>')
    def serve_snippet(filename):
        """Serve bib snippet images."""
        return send_from_directory(SNIPPETS_DIR, filename)

    @app.route('/cache/candidates/<filename>')
    def serve_candidates(filename):
        """Serve candidate visualization images."""
        return send_from_directory(CANDIDATES_DIR, filename)

    return app


def get_all_photo_hashes() -> list[str]:
    """Get all photo hashes in order (by id for consistent ordering)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT photo_hash FROM photos ORDER BY id")
    hashes = [row[0] for row in cursor.fetchall()]
    conn.close()
    return hashes


def get_photo_with_bibs(photo_hash: str) -> tuple[dict | None, list[dict]]:
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
        # Check if candidates visualization exists
        candidates_path = CANDIDATES_DIR / photo['cache_filename']
        photo['has_candidates'] = candidates_path.exists()
    else:
        photo['has_gray_bbox'] = False
        photo['has_candidates'] = False

    # Get bib detections for this photo
    cursor.execute(
        "SELECT bib_number, confidence, bbox_json FROM bib_detections WHERE photo_id = ? ORDER BY confidence DESC",
        (photo['id'],)
    )
    bibs = [dict(row) for row in cursor.fetchall()]

    # Add snippet paths for each bib (using bbox hash for unique identification)
    if photo['cache_filename']:
        cache_stem = Path(photo['cache_filename']).stem
        for bib in bibs:
            # Parse bbox from JSON and compute hash
            bbox = json.loads(bib['bbox_json']) if bib['bbox_json'] else None
            if bbox:
                bbox_hash = compute_bbox_hash(bbox)
                snippet_filename = f"{cache_stem}_bib{bib['bib_number']}_{bbox_hash}.jpg"
                snippet_path = SNIPPETS_DIR / snippet_filename
                bib['snippet_filename'] = snippet_filename if snippet_path.exists() else None
            else:
                bib['snippet_filename'] = None

    # Check if any snippets exist for this photo
    photo['has_snippets'] = any(bib.get('snippet_filename') for bib in bibs)

    conn.close()
    return photo, bibs


def main():
    """Run the web server."""
    configure_logging()
    # Ensure database has photo hashes (migrate if needed)
    conn = get_connection()
    migrate_add_photo_hash(conn)
    conn.close()

    app = create_app()

    logger.info("Starting Bib Scanner Web Viewer...")
    logger.info("Open http://localhost:30001 in your browser")
    logger.info("Press Ctrl+C to stop")
    app.run(host='localhost', port=30001, debug=False)


if __name__ == '__main__':
    main()

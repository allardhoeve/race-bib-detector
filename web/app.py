"""
Flask application for the bib scanner web interface.
"""

import argparse
import json
import logging
from pathlib import Path

from flask import Flask, render_template_string, send_from_directory, abort

from db import get_connection, migrate_add_photo_hash
from logging_utils import configure_logging, add_logging_args
from utils import compute_bbox_hash
from .templates import HTML_TEMPLATE, EMPTY_TEMPLATE, FACE_CLUSTERS_TEMPLATE

logger = logging.getLogger(__name__)

# Paths
CACHE_DIR = Path(__file__).parent.parent / "cache"
GRAY_BBOX_DIR = CACHE_DIR / "gray_bounding"
CANDIDATES_DIR = CACHE_DIR / "candidates"
SNIPPETS_DIR = CACHE_DIR / "snippets"
FACE_SNIPPETS_DIR = CACHE_DIR / "faces" / "snippets"
FACE_BOXED_DIR = CACHE_DIR / "faces" / "boxed"
FACE_CANDIDATES_DIR = CACHE_DIR / "faces" / "candidates"
FACE_EVIDENCE_DIR = CACHE_DIR / "faces" / "evidence"


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

        photo, bibs, faces = get_photo_with_bibs(photo_hash)

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
            faces=faces,
            current=current_index + 1,
            total=total,
            has_prev=has_prev,
            has_next=has_next,
            prev_hash=prev_hash,
            next_hash=next_hash,
        )

    @app.route('/faces')
    def view_faces():
        """Browse face clusters and unclustered faces."""
        clusters, unclustered_faces = get_face_clusters_and_faces()
        return render_template_string(
            FACE_CLUSTERS_TEMPLATE,
            clusters=clusters,
            unclustered_faces=unclustered_faces,
        )

    @app.route('/cache/<filename>')
    def serve_cache(filename):
        """Serve cached images."""
        return send_from_directory(CACHE_DIR, filename)

    @app.route('/local/<photo_hash>')
    def serve_local(photo_hash):
        """Serve cached image files by their photo hash (legacy route)."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT cache_path FROM photos WHERE photo_hash = ?", (photo_hash,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            abort(404)

        cache_path = row[0]
        if not cache_path:
            abort(404)

        path = Path(cache_path)
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

    @app.route('/cache/faces/snippets/<filename>')
    def serve_face_snippet(filename):
        """Serve face snippet images."""
        return send_from_directory(FACE_SNIPPETS_DIR, filename)

    @app.route('/cache/faces/boxed/<filename>')
    def serve_face_boxed(filename):
        """Serve face boxed preview images."""
        return send_from_directory(FACE_BOXED_DIR, filename)

    @app.route('/cache/faces/candidates/<filename>')
    def serve_face_candidates(filename):
        """Serve face candidates preview images."""
        return send_from_directory(FACE_CANDIDATES_DIR, filename)

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


def get_photo_with_bibs(photo_hash: str) -> tuple[dict | None, list[dict], list[dict]]:
    """Get photo details and its bib detections by hash."""
    conn = get_connection()
    cursor = conn.cursor()

    # Get photo details
    cursor.execute(
        "SELECT id, photo_hash, album_id, photo_url, thumbnail_url, cache_path, scanned_at FROM photos WHERE photo_hash = ?",
        (photo_hash,)
    )
    photo_row = cursor.fetchone()

    if not photo_row:
        conn.close()
        return None, [], []

    photo = dict(photo_row)

    cache_path = Path(photo['cache_path']) if photo['cache_path'] else None
    if cache_path and cache_path.is_file():
        photo['cache_filename'] = cache_path.name
        photo['original_url'] = f"/local/{photo_hash}"
    else:
        photo['cache_filename'] = None
        photo['original_url'] = None

    # Check if grayscale bounding box image exists
    if photo['cache_filename']:
        gray_bbox_path = GRAY_BBOX_DIR / photo['cache_filename']
        photo['has_gray_bbox'] = gray_bbox_path.exists()
        # Check if candidates visualization exists
        candidates_path = CANDIDATES_DIR / photo['cache_filename']
        photo['has_candidates'] = candidates_path.exists()
        face_candidates_path = FACE_CANDIDATES_DIR / photo['cache_filename']
        photo['has_face_candidates'] = face_candidates_path.exists()
    else:
        photo['has_gray_bbox'] = False
        photo['has_candidates'] = False
        photo['has_face_candidates'] = False

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

    # Get face detections for this photo
    cursor.execute(
        """
        SELECT face_index, snippet_path, preview_path, model_name, model_version, bbox_json
        FROM face_detections
        WHERE photo_id = ?
        ORDER BY face_index
        """,
        (photo['id'],)
    )
    faces = [dict(row) for row in cursor.fetchall()]
    for face in faces:
        snippet_path = face.get("snippet_path")
        preview_path = face.get("preview_path")
        face["snippet_filename"] = Path(snippet_path).name if snippet_path else None
        face["preview_filename"] = Path(preview_path).name if preview_path else None

    photo['has_faces'] = any(face.get("snippet_filename") for face in faces)

    conn.close()
    return photo, bibs, faces


def get_face_clusters_and_faces() -> tuple[list[dict], list[dict]]:
    """Get face clusters and unclustered face detections."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT fc.id,
               fc.album_id,
               a.label AS album_label,
               fc.model_name,
               fc.model_version,
               fc.size,
               fc.avg_similarity,
               fc.min_similarity,
               fc.max_similarity,
               fc.created_at
        FROM face_clusters fc
        LEFT JOIN albums a ON a.album_id = fc.album_id
        ORDER BY fc.created_at DESC
        """
    )
    clusters = [dict(row) for row in cursor.fetchall()]

    cursor.execute(
        """
        SELECT fd.id, fd.face_index, fd.snippet_path, fd.preview_path, p.photo_hash
        FROM face_detections fd
        JOIN photos p ON p.id = fd.photo_id
        LEFT JOIN face_cluster_members fcm ON fcm.face_id = fd.id
        WHERE fcm.id IS NULL
        ORDER BY fd.detected_at DESC
        LIMIT 200
        """
    )
    unclustered_faces = [dict(row) for row in cursor.fetchall()]
    for face in unclustered_faces:
        snippet_path = face.get("snippet_path")
        preview_path = face.get("preview_path")
        face["snippet_filename"] = Path(snippet_path).name if snippet_path else None
        face["preview_filename"] = Path(preview_path).name if preview_path else None

    conn.close()
    return clusters, unclustered_faces


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch the bib scanner web viewer (port 30001)."
    )
    add_logging_args(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the web server."""
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level, args.verbose, args.quiet)
    # Ensure database has photo hashes (migrate if needed)
    conn = get_connection()
    migrate_add_photo_hash(conn)
    conn.close()

    app = create_app()

    logger.info("Starting Bib Scanner Web Viewer...")
    logger.info("Open http://localhost:30001 in your browser")
    logger.info("Press Ctrl+C to stop")
    app.run(host='localhost', port=30001, debug=False)
    return 0


if __name__ == '__main__':
    main()

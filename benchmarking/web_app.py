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
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template, send_file, redirect, url_for

from benchmarking.photo_index import load_photo_index, get_path_for_hash
from benchmarking.routes_bib import bib_bp
from benchmarking.routes_benchmark import benchmark_bp
from benchmarking.routes_face import face_bp
from benchmarking.routes_identities import identities_bp
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
        static_folder=str(Path(__file__).parent / 'static'),
    )

    app.register_blueprint(bib_bp)
    app.register_blueprint(face_bp)
    app.register_blueprint(identities_bp)
    app.register_blueprint(benchmark_bp)

    # -------------------------------------------------------------------------
    # Index / Root
    # -------------------------------------------------------------------------
    @app.route('/')
    def index():
        """Landing page — numbered labeling workflow with per-step progress."""
        from benchmarking.ground_truth import load_bib_ground_truth, load_face_ground_truth
        from benchmarking.label_utils import is_face_labeled

        photo_index = load_photo_index()
        total = len(photo_index)

        bib_gt = load_bib_ground_truth()
        face_gt = load_face_ground_truth()

        bib_labeled = sum(1 for lbl in bib_gt.photos.values() if lbl.labeled)
        face_labeled = sum(1 for lbl in face_gt.photos.values() if is_face_labeled(lbl))

        try:
            from benchmarking.ground_truth import load_link_ground_truth
            link_gt = load_link_ground_truth()
            links_labeled = len(link_gt.photos)
        except (ImportError, AttributeError):
            links_labeled = None  # template renders as "N/A"

        return render_template(
            'labels_home.html',
            total=total,
            bib_labeled=bib_labeled,
            face_labeled=face_labeled,
            links_labeled=links_labeled,
        )

    # -------------------------------------------------------------------------
    # Shared Routes
    # -------------------------------------------------------------------------
    @app.route('/photo/<content_hash>')
    def serve_photo_redirect(content_hash):
        """301 shim for backward compatibility."""
        return redirect(url_for('serve_photo', content_hash=content_hash), 301)

    @app.route('/media/photos/<content_hash>')
    def serve_photo(content_hash):
        """Serve photo by content hash."""
        from benchmarking.label_utils import find_hash_by_prefix
        index = load_photo_index()

        full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
        if not full_hash:
            return "Not found", 404

        path = get_path_for_hash(full_hash, PHOTOS_DIR, index)
        if not path or not path.exists():
            return "Not found", 404

        return send_file(path)

    # -------------------------------------------------------------------------
    # Test route
    # -------------------------------------------------------------------------
    @app.route('/test/labeling')
    def test_labeling():
        """Redirect to the browser integration test page."""
        return redirect(url_for('static', filename='test_labeling.html'))

    return app


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

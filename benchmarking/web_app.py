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

from flask import Flask, render_template, send_file, send_from_directory, redirect, url_for

from benchmarking.photo_index import load_photo_index, get_path_for_hash
from benchmarking.routes_bib import bib_bp
from benchmarking.routes_benchmark import benchmark_bp
from benchmarking.routes_face import face_bp
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

    app.register_blueprint(bib_bp)
    app.register_blueprint(face_bp)
    app.register_blueprint(benchmark_bp)

    # -------------------------------------------------------------------------
    # Index / Root
    # -------------------------------------------------------------------------
    @app.route('/')
    def index():
        """Landing page for label UIs."""
        return render_template('labels_home.html')

    # -------------------------------------------------------------------------
    # Shared Routes
    # -------------------------------------------------------------------------
    @app.route('/photo/<content_hash>')
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

"""Serve command CLI parsing and control flow."""

from __future__ import annotations

import argparse
import logging

logger = logging.getLogger(__name__)


def add_serve_subparser(subparsers: argparse._SubParsersAction) -> None:
    serve_parser = subparsers.add_parser(
        "serve",
        help="Launch photo viewer website (port 30001)",
    )
    serve_parser.set_defaults(_cmd=cmd_serve)


def cmd_serve(args: argparse.Namespace) -> int:
    """Launch the photo viewer web server."""
    from db import get_connection, migrate_add_photo_hash
    from web import create_app

    conn = get_connection()
    migrate_add_photo_hash(conn)
    conn.close()

    app = create_app()

    logger.info("Starting Bib Scanner Web Viewer...")
    logger.info("Open http://localhost:30001 in your browser")
    logger.info("Press Ctrl+C to stop")
    app.run(host="localhost", port=30001, debug=False)
    return 0

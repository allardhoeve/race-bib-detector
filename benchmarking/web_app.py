#!/usr/bin/env python3
"""
Unified web application for benchmark labeling and inspection.

Routes:
- /labels/ - Labeling UI for annotating photos
- /faces/labels/ - Face labeling UI for annotating face counts/tags
- /benchmark/ - List of benchmark runs
- /benchmark/<run_id>/ - Inspection UI for a specific run
- /docs/ - Swagger UI (OpenAPI)
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarking.app import create_app  # noqa: F401  re-exported for backward compat
from benchmarking.photo_index import load_photo_index
from logging_utils import add_logging_args, configure_logging

logger = logging.getLogger(__name__)


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
    import uvicorn

    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level, args.verbose, args.quiet)
    index = load_photo_index()
    if not index:
        logger.error("No photo index found. Run 'python -m benchmarking.cli scan' first.")
        return 1

    logger.info("Starting Benchmark Web UI...")
    logger.info("Found %s photos in index", len(index))
    logger.info("Routes:")
    logger.info("  /labels/              - Label photos")
    logger.info("  /faces/labels/        - Label face counts/tags")
    logger.info("  /benchmark/           - List benchmark runs")
    logger.info("  /benchmark/<run_id>/  - Inspect a run")
    logger.info("  /docs/                - Swagger UI")
    logger.info("Open http://localhost:30002 in your browser")
    logger.info("Press Ctrl+C to stop")
    uvicorn.run("benchmarking.app:app", host="localhost", port=30002, reload=False)
    return 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python
"""Web interface for viewing scanned photos and detected bib numbers."""

import argparse
import logging

from web import main as web_main
from logging_utils import add_logging_args, configure_logging

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch the bib scanner web viewer (port 30001)."
    )
    add_logging_args(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level, args.verbose, args.quiet)
    web_main()
    return 0


if __name__ == '__main__':
    main()

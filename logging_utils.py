"""Shared logging configuration helpers."""

from __future__ import annotations

import logging
import sys
from typing import Iterable

LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}

LOG_LEVEL_CHOICES: Iterable[str] = tuple(LOG_LEVELS.keys())

def add_logging_args(parser) -> None:
    """Add standard logging options to an argparse parser."""
    parser.add_argument(
        "--log-level",
        choices=LOG_LEVEL_CHOICES,
        help="Set log verbosity (debug, info, warning, error, critical)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase log verbosity (use -vv for more detail)",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="count",
        default=0,
        help="Reduce log verbosity (use -qq for errors only)",
    )


def resolve_log_level(
    log_level: str | None = None,
    verbose: int = 0,
    quiet: int = 0,
) -> int:
    """Resolve a numeric log level from explicit or modifier flags."""
    if log_level:
        return LOG_LEVELS[log_level.lower()]

    offset = verbose - quiet
    if offset >= 1:
        return logging.DEBUG
    if offset == 0:
        return logging.INFO
    if offset == -1:
        return logging.WARNING
    return logging.ERROR


def configure_logging(
    log_level: str | None = None,
    verbose: int = 0,
    quiet: int = 0,
) -> int:
    """Configure root logging and return the active level."""
    level = resolve_log_level(log_level=log_level, verbose=verbose, quiet=quiet)
    root_logger = logging.getLogger()

    if root_logger.handlers:
        root_logger.setLevel(level)
        for handler in root_logger.handlers:
            handler.setLevel(level)
        return level

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    return level

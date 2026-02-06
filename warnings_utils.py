"""Warnings helpers to keep runtime output clean."""

from __future__ import annotations

import warnings


def suppress_torch_mps_pin_memory_warning() -> None:
    """Suppress noisy pin_memory warnings on MPS-backed systems."""
    warnings.filterwarnings(
        "ignore",
        message=r".*pin_memory.*MPS.*",
        category=UserWarning,
        module=r"torch\.utils\.data\.dataloader",
    )

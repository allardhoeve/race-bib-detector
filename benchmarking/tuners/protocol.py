"""Tuner protocol and shared result type (task-060)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class TunerResult(BaseModel):
    """A single parameter-combination result from any tuner."""

    params: dict[str, Any]
    metrics: dict[str, float]


@runtime_checkable
class Tuner(Protocol):
    """Shared interface for all tuning strategies."""

    def tune(
        self,
        *,
        split: str = "iteration",
        metric: str = "face_f1",
        verbose: bool = True,
    ) -> list[TunerResult]: ...

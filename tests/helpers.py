"""Shared test helpers — factories and fakes reused across test modules."""

from __future__ import annotations

from pipeline.types import FaceCandidateTrace


def make_face_trace(embedding: list[float] | None = None) -> FaceCandidateTrace:
    """Factory for an accepted FaceCandidateTrace with optional embedding."""
    return FaceCandidateTrace(
        x=0.1, y=0.1, w=0.2, h=0.2,
        confidence=0.9,
        passed=True,
        accepted=True,
        pixel_bbox=(10, 10, 30, 30),
        embedding=embedding,
    )

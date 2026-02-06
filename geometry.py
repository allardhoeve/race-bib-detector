"""Shared geometry utilities for quadrilateral bounding boxes."""

from __future__ import annotations

# Bounding box as list of 4 [x, y] points defining a quadrilateral
Bbox = list[list[int]]


def rect_to_bbox(x: int, y: int, w: int, h: int) -> Bbox:
    """Convert rectangle (x, y, w, h) to a quadrilateral bbox."""
    return [
        [x, y],
        [x + w, y],
        [x + w, y + h],
        [x, y + h],
    ]


def bbox_to_rect(bbox: Bbox) -> tuple[int, int, int, int]:
    """Convert a quadrilateral bbox to a bounding rectangle (x1, y1, x2, y2)."""
    x_coords = [p[0] for p in bbox]
    y_coords = [p[1] for p in bbox]
    x1, y1, x2, y2 = min(x_coords), min(y_coords), max(x_coords), max(y_coords)
    return x1, y1, x2, y2


def scale_bbox(bbox: Bbox, factor: float) -> Bbox:
    """Scale a bbox by a given factor."""
    return [[int(p[0] * factor), int(p[1] * factor)] for p in bbox]

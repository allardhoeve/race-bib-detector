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


def rect_iou(
    rect_a: tuple[int, int, int, int],
    rect_b: tuple[int, int, int, int],
) -> float:
    """Compute intersection-over-union between two rectangles (x1, y1, x2, y2)."""
    ax1, ay1, ax2, ay2 = rect_a
    bx1, by1, bx2, by2 = rect_b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    denom = area_a + area_b - inter_area
    if denom <= 0:
        return 0.0
    return inter_area / denom

"""Bounding box geometry utilities."""

from geometry import Bbox, bbox_to_rect, scale_bbox


def bbox_area(bbox: Bbox) -> float:
    """Calculate the area of a bounding box (quadrilateral).

    Uses the shoelace formula for polygon area.

    Args:
        bbox: List of [x, y] points defining the quadrilateral.

    Returns:
        Area of the bounding box.
    """
    n = len(bbox)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += bbox[i][0] * bbox[j][1]
        area -= bbox[j][0] * bbox[i][1]
    return abs(area) / 2.0


def rect_intersection_area(rect1: tuple[int, int, int, int], rect2: tuple[int, int, int, int]) -> float:
    """Calculate intersection area of two rectangles.

    Args:
        rect1: Tuple of (x_min, y_min, x_max, y_max).
        rect2: Tuple of (x_min, y_min, x_max, y_max).

    Returns:
        Area of intersection, or 0 if no intersection.
    """
    x1 = max(rect1[0], rect2[0])
    y1 = max(rect1[1], rect2[1])
    x2 = min(rect1[2], rect2[2])
    y2 = min(rect1[3], rect2[3])

    if x2 <= x1 or y2 <= y1:
        return 0.0
    return (x2 - x1) * (y2 - y1)


def rect_area(rect: tuple[int, int, int, int]) -> float:
    """Calculate area of a rectangle.

    Args:
        rect: Tuple of (x_min, y_min, x_max, y_max).

    Returns:
        Area of the rectangle.
    """
    return (rect[2] - rect[0]) * (rect[3] - rect[1])


def bbox_iou(bbox1: Bbox, bbox2: Bbox) -> float:
    """Calculate Intersection over Union (IoU) for two bounding boxes.

    Args:
        bbox1: First bounding box as list of [x, y] points.
        bbox2: Second bounding box as list of [x, y] points.

    Returns:
        IoU value between 0 and 1.
    """
    rect1 = bbox_to_rect(bbox1)
    rect2 = bbox_to_rect(bbox2)

    intersection = rect_intersection_area(rect1, rect2)
    if intersection == 0:
        return 0.0

    area1 = rect_area(rect1)
    area2 = rect_area(rect2)
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0


def bbox_overlap_ratio(bbox1: Bbox, bbox2: Bbox) -> float:
    """Calculate how much of the smaller box is covered by intersection.

    This catches cases where a small box is entirely inside a larger box,
    which would have low IoU but high overlap ratio.

    Args:
        bbox1: First bounding box as list of [x, y] points.
        bbox2: Second bounding box as list of [x, y] points.

    Returns:
        Overlap ratio between 0 and 1.
    """
    rect1 = bbox_to_rect(bbox1)
    rect2 = bbox_to_rect(bbox2)

    intersection = rect_intersection_area(rect1, rect2)
    if intersection == 0:
        return 0.0

    # Use the smaller box's area as denominator
    smaller_area = min(rect_area(rect1), rect_area(rect2))
    return intersection / smaller_area if smaller_area > 0 else 0.0


def scale_bboxes(bboxes: list[Bbox], factor: float) -> list[Bbox]:
    """Scale a list of bounding boxes by a factor.

    Args:
        bboxes: List of bounding boxes, each a list of [x, y] points.
        factor: Scale factor to apply to all coordinates.

    Returns:
        New list of bounding boxes with scaled coordinates.
    """
    return [scale_bbox(bbox, factor) for bbox in bboxes]

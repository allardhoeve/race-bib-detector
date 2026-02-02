"""
Detection filtering functions.

Filters for removing false positives and duplicate detections.
"""

from config import (
    MIN_DETECTION_AREA_RATIO,
    IOU_OVERLAP_THRESHOLD,
    COVERAGE_OVERLAP_THRESHOLD,
    SUBSTRING_CONFIDENCE_RATIO,
)

from .bbox import bbox_area, bbox_iou, bbox_overlap_ratio
from .validation import is_substring_bib


def choose_detection_to_remove(
    det1: dict,
    det2: dict,
    idx1: int,
    idx2: int,
) -> int | None:
    """Decide which of two overlapping detections to remove.

    Decision logic:
    1. If one bib is a substring of the other, keep the longer one
       (unless shorter has much higher confidence)
    2. Otherwise prefer more digits
    3. If same digit count, prefer higher confidence

    Args:
        det1: First detection dict with 'bib_number', 'confidence'
        det2: Second detection dict with 'bib_number', 'confidence'
        idx1: Index of first detection
        idx2: Index of second detection

    Returns:
        Index of detection to remove, or None if neither should be removed
    """
    bib1, bib2 = det1["bib_number"], det2["bib_number"]
    conf1, conf2 = det1["confidence"], det2["confidence"]

    # Check substring relationship
    # When one is substring of another, prefer longer UNLESS shorter has much higher confidence
    if is_substring_bib(bib1, bib2):
        # bib1 is substring of bib2 - keep bib2 (longer) unless bib1 has much higher confidence
        if conf1 > conf2 * SUBSTRING_CONFIDENCE_RATIO:
            return idx2  # Remove longer, keep shorter high-confidence
        return idx1  # Remove shorter, keep longer

    if is_substring_bib(bib2, bib1):
        # bib2 is substring of bib1 - keep bib1 (longer) unless bib2 has much higher confidence
        if conf2 > conf1 * SUBSTRING_CONFIDENCE_RATIO:
            return idx1  # Remove longer, keep shorter high-confidence
        return idx2  # Remove shorter, keep longer

    # No substring relationship - prefer more digits
    if len(bib2) > len(bib1):
        return idx1
    if len(bib1) > len(bib2):
        return idx2

    # Same length - keep higher confidence
    if conf2 > conf1:
        return idx1
    return idx2


def detections_overlap(
    det1: dict,
    det2: dict,
    iou_threshold: float,
    overlap_threshold: float,
) -> bool:
    """Check if two detections overlap significantly.

    Args:
        det1: First detection dict with 'bbox'
        det2: Second detection dict with 'bbox'
        iou_threshold: IoU threshold for considering boxes as overlapping
        overlap_threshold: Overlap ratio threshold for considering boxes as overlapping

    Returns:
        True if detections overlap above either threshold
    """
    iou = bbox_iou(det1["bbox"], det2["bbox"])
    overlap_ratio = bbox_overlap_ratio(det1["bbox"], det2["bbox"])
    return iou >= iou_threshold or overlap_ratio >= overlap_threshold


def filter_small_detections(
    detections: list[dict],
    white_region_area: float,
    min_ratio: float | None = None,
) -> list[dict]:
    """Filter out detections that are too small relative to the white region.

    A legitimate bib number (even single digit like "1") should occupy at least
    ~10-15% of the white bib region. Tiny detections are usually noise.

    Args:
        detections: List of detection dicts with 'bbox' key.
        white_region_area: Area of the white region being scanned.
        min_ratio: Minimum ratio of detection area to region area.

    Returns:
        Filtered list of detections.
    """
    if min_ratio is None:
        min_ratio = MIN_DETECTION_AREA_RATIO

    if white_region_area <= 0:
        return detections

    filtered = []
    for det in detections:
        det_area = bbox_area(det["bbox"])
        ratio = det_area / white_region_area
        if ratio >= min_ratio:
            filtered.append(det)
    return filtered


def filter_overlapping_detections(
    detections: list[dict],
    iou_threshold: float | None = None,
    overlap_threshold: float | None = None,
) -> list[dict]:
    """Filter overlapping detections, keeping the longer/better one.

    When two detections overlap significantly:
    - If one bib is a substring of the other (e.g., "6" vs "620"), keep the longer one
    - Otherwise, keep the one with more digits
    - If same digit count, keep higher confidence

    Uses both IoU and overlap ratio to catch both partial overlaps and
    cases where a small box is entirely inside a larger one.

    Args:
        detections: List of detection dicts with 'bib_number', 'confidence', 'bbox'.
        iou_threshold: IoU threshold for considering boxes as overlapping.
        overlap_threshold: Overlap ratio threshold for considering boxes as overlapping.

    Returns:
        Filtered list of detections.
    """
    if iou_threshold is None:
        iou_threshold = IOU_OVERLAP_THRESHOLD
    if overlap_threshold is None:
        overlap_threshold = COVERAGE_OVERLAP_THRESHOLD

    if len(detections) <= 1:
        return detections

    to_remove = set()

    for i, det1 in enumerate(detections):
        if i in to_remove:
            continue

        for j, det2 in enumerate(detections):
            if j <= i or j in to_remove:
                continue

            if not detections_overlap(det1, det2, iou_threshold, overlap_threshold):
                continue

            remove_idx = choose_detection_to_remove(det1, det2, i, j)
            if remove_idx is not None:
                to_remove.add(remove_idx)
                if remove_idx == i:
                    break  # det1 removed, move to next i

    return [det for i, det in enumerate(detections) if i not in to_remove]

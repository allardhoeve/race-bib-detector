"""
Detection filtering functions.

Filters for removing false positives and duplicate detections.
"""

from .bbox import bbox_area, bbox_iou, bbox_overlap_ratio
from .validation import is_substring_bib


def filter_small_detections(
    detections: list[dict],
    white_region_area: float,
    min_ratio: float = 0.10,
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
    iou_threshold: float = 0.3,
    overlap_threshold: float = 0.7,
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
    if len(detections) <= 1:
        return detections

    # Mark detections to remove
    to_remove = set()

    for i, det1 in enumerate(detections):
        if i in to_remove:
            continue

        for j, det2 in enumerate(detections):
            if j <= i or j in to_remove:
                continue

            iou = bbox_iou(det1["bbox"], det2["bbox"])
            overlap_ratio = bbox_overlap_ratio(det1["bbox"], det2["bbox"])

            # Consider boxes overlapping if either IoU or overlap ratio exceeds threshold
            if iou < iou_threshold and overlap_ratio < overlap_threshold:
                continue

            # Detections overlap - decide which to keep
            bib1, bib2 = det1["bib_number"], det2["bib_number"]

            # Check substring relationship
            if is_substring_bib(bib1, bib2):
                # bib1 is substring of bib2, remove bib1
                to_remove.add(i)
                break
            elif is_substring_bib(bib2, bib1):
                # bib2 is substring of bib1, remove bib2
                to_remove.add(j)
                continue

            # No substring relationship - prefer more digits, then higher confidence
            if len(bib2) > len(bib1):
                to_remove.add(i)
                break
            elif len(bib1) > len(bib2):
                to_remove.add(j)
                continue
            else:
                # Same length - keep higher confidence
                if det2["confidence"] > det1["confidence"]:
                    to_remove.add(i)
                    break
                else:
                    to_remove.add(j)

    return [det for i, det in enumerate(detections) if i not in to_remove]

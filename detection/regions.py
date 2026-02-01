"""
White region detection for candidate bib areas.

Bibs are typically white rectangles with dark numbers. This module finds
candidate white regions that could contain bib numbers.
"""

import cv2
import numpy as np


def find_white_regions(image_array: np.ndarray, min_area: int = 1000) -> list[tuple]:
    """Find white rectangular regions that could be bib numbers.

    Args:
        image_array: RGB image as numpy array.
        min_area: Minimum contour area to consider.

    Returns:
        List of (x, y, w, h) tuples for candidate regions.
    """
    # Convert to grayscale
    gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)

    # Threshold to find white regions (bibs are white/light colored)
    # Use adaptive threshold to handle varying lighting
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

    # Find contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    img_height, img_width = image_array.shape[:2]

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue

        # Get bounding rectangle
        x, y, w, h = cv2.boundingRect(contour)

        # Filter by aspect ratio (bibs are roughly square or wider than tall)
        aspect_ratio = w / h if h > 0 else 0
        if aspect_ratio < 0.5 or aspect_ratio > 4:
            continue

        # Filter by size relative to image (not too small, not too large)
        relative_area = (w * h) / (img_width * img_height)
        if relative_area < 0.001 or relative_area > 0.3:
            continue

        # Add padding around the region
        padding = int(min(w, h) * 0.1)
        x = max(0, x - padding)
        y = max(0, y - padding)
        w = min(img_width - x, w + 2 * padding)
        h = min(img_height - y, h + 2 * padding)

        candidates.append((x, y, w, h))

    return candidates

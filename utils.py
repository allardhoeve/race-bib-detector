"""Shared utility functions for bib number recognizer."""

import json
import re
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import requests

from config import PHOTO_URL_WIDTH, THUMBNAIL_URL_WIDTH, SNIPPET_PADDING_RATIO

CACHE_DIR = Path(__file__).parent / "cache"
GRAY_BBOX_DIR = CACHE_DIR / "gray_bounding"
SNIPPETS_DIR = CACHE_DIR / "snippets"


def clean_photo_url(url: str) -> dict:
    """Clean a Google Photos URL and return base, full-res, and thumbnail URLs.

    Returns dict with keys: base_url, photo_url, thumbnail_url
    """
    # Remove size parameters to get base URL
    base_url = re.sub(r'=w\d+.*$', '', url)
    base_url = re.sub(r'=s\d+.*$', '', base_url)

    return {
        "base_url": base_url,
        "photo_url": base_url + f"=w{PHOTO_URL_WIDTH}",
        "thumbnail_url": base_url + f"=w{THUMBNAIL_URL_WIDTH}",
    }


def get_full_res_url(photo_url: str) -> str:
    """Convert a photo URL to full resolution (original size)."""
    base_url = re.sub(r'=w\d+.*$', '', photo_url)
    base_url = re.sub(r'=s\d+.*$', '', base_url)
    return base_url + "=w0"


def download_image(url: str, timeout: int = 30) -> bytes:
    """Download an image and return its bytes."""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content


def download_image_to_file(url: str, output_path: Path, timeout: int = 60) -> bool:
    """Download an image to a file path. Returns True on success."""
    try:
        response = requests.get(url, timeout=timeout, stream=True)
        response.raise_for_status()

        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"\nError downloading {url}: {e}")
        return False


def get_gray_bbox_path(cache_path: Path) -> Path:
    """Get the grayscale bounding box image path for a given cache path."""
    return GRAY_BBOX_DIR / cache_path.name


def compute_bbox_hash(bbox: list) -> str:
    """Compute a short hash from a bounding box for unique identification.

    Args:
        bbox: Bounding box as [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]

    Returns:
        8-character hash string
    """
    import hashlib
    bbox_str = str(bbox)
    return hashlib.sha256(bbox_str.encode()).hexdigest()[:8]


def get_snippet_path(cache_path: Path, bib_number: str, bbox: list) -> Path:
    """Get the snippet image path for a detected bib.

    Args:
        cache_path: Path to the cached photo
        bib_number: The detected bib number
        bbox: Bounding box coordinates (used to generate unique hash)

    Returns:
        Path to the snippet image file
    """
    stem = cache_path.stem
    bbox_hash = compute_bbox_hash(bbox)
    return SNIPPETS_DIR / f"{stem}_bib{bib_number}_{bbox_hash}.jpg"


def save_bib_snippet(
    image: np.ndarray,
    bbox: list,
    output_path: Path,
    padding_ratio: float | None = None,
) -> bool:
    """Save a cropped snippet of a detected bib region.

    Args:
        image: Source image (RGB or grayscale numpy array)
        bbox: Bounding box as [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        output_path: Where to save the snippet
        padding_ratio: Extra padding around the bounding box (defaults to SNIPPET_PADDING_RATIO)

    Returns:
        True on success
    """
    if padding_ratio is None:
        padding_ratio = SNIPPET_PADDING_RATIO

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Get bounding rectangle from quadrilateral
        x_coords = [p[0] for p in bbox]
        y_coords = [p[1] for p in bbox]
        x_min, x_max = min(x_coords), max(x_coords)
        y_min, y_max = min(y_coords), max(y_coords)

        # Add padding
        width = x_max - x_min
        height = y_max - y_min
        pad_x = int(width * padding_ratio)
        pad_y = int(height * padding_ratio)

        # Ensure we stay within image bounds
        img_height, img_width = image.shape[:2]
        x_min = max(0, x_min - pad_x)
        y_min = max(0, y_min - pad_y)
        x_max = min(img_width, x_max + pad_x)
        y_max = min(img_height, y_max + pad_y)

        # Crop the region
        snippet = image[y_min:y_max, x_min:x_max]

        # Convert to BGR if needed for cv2
        if len(snippet.shape) == 2:
            # Grayscale
            cv2.imwrite(str(output_path), snippet)
        elif snippet.shape[2] == 3:
            # RGB -> BGR for cv2
            cv2.imwrite(str(output_path), cv2.cvtColor(snippet, cv2.COLOR_RGB2BGR))
        else:
            cv2.imwrite(str(output_path), snippet)

        return True

    except Exception as e:
        print(f"Error saving bib snippet: {e}")
        return False


def draw_bounding_boxes_on_gray(
    gray_image: np.ndarray,
    detections: list[dict],
    output_path: Path,
) -> bool:
    """Draw bounding boxes on a grayscale image and save it.

    Args:
        gray_image: Grayscale image as numpy array (2D or 3D single channel)
        detections: List of detection dicts with 'bib_number', 'confidence', 'bbox'
        output_path: Where to save the annotated image

    Returns:
        True on success
    """
    try:
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert grayscale to BGR for colored annotations
        if gray_image.ndim == 2:
            image = cv2.cvtColor(gray_image, cv2.COLOR_GRAY2BGR)
        else:
            image = gray_image.copy()

        # Draw each detection
        for det in detections:
            bbox = det["bbox"]
            bib_number = det["bib_number"]
            confidence = det["confidence"]

            # bbox is [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] - a quadrilateral
            pts = np.array(bbox, np.int32)
            pts = pts.reshape((-1, 1, 2))

            # Draw the polygon outline (green on grayscale stands out)
            cv2.polylines(image, [pts], isClosed=True, color=(0, 255, 0), thickness=3)

            # Get top-left point for label
            x_min = min(p[0] for p in bbox)
            y_min = min(p[1] for p in bbox)

            # Draw label background
            label = f"{bib_number} ({confidence:.0%})"
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.8
            thickness = 2
            (text_width, text_height), baseline = cv2.getTextSize(label, font, font_scale, thickness)

            # Position label above the box
            label_y = max(y_min - 10, text_height + 10)
            label_x = x_min

            # Draw background rectangle for text
            cv2.rectangle(
                image,
                (label_x, label_y - text_height - 5),
                (label_x + text_width + 10, label_y + 5),
                (0, 255, 0),
                -1
            )

            # Draw text
            cv2.putText(
                image, label,
                (label_x + 5, label_y),
                font, font_scale, (0, 0, 0), thickness
            )

        # Save the annotated image
        cv2.imwrite(str(output_path), image)
        return True

    except Exception as e:
        print(f"Error drawing bounding boxes on grayscale: {e}")
        return False

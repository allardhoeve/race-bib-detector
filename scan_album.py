#!/usr/bin/env python3
"""Scan images for bib numbers using OCR.

Supports two modes:
1. Google Photos album: Provide a URL to scan a shared album
2. Local directory: Provide a path to scan local image files
"""

import argparse
import hashlib
import io
import re
from pathlib import Path
from urllib.parse import urlparse

import cv2
import easyocr
import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright
from tqdm import tqdm

import db
from preprocessing import run_pipeline, PreprocessConfig
from utils import (
    CACHE_DIR, clean_photo_url, download_image,
    get_gray_bbox_path, draw_bounding_boxes_on_gray,
)


def is_avatar_url(url: str) -> bool:
    """Check if a URL is likely a user avatar rather than an album photo.

    Avatars typically have:
    - Small size parameters (=s32, =s48, =s64, =s96, etc.)
    - Or contain 'AAAAALX' pattern (Google profile photos)
    """
    # Avatar URLs often have small 's' size parameter (square/avatar sizing)
    # Album photos use 'w' parameter for width
    if re.search(r'=s\d{1,3}(-|$|[a-z])', url):
        # Small size like =s32, =s48, =s64, =s96 (avatars are typically < 200px)
        match = re.search(r'=s(\d+)', url)
        if match and int(match.group(1)) < 200:
            return True

    # Google profile photo URL pattern
    if 'AAAAALX' in url:
        return True

    return False


def extract_image_urls(page) -> list[dict]:
    """Extract image URLs from the Google Photos album page."""
    # Google Photos stores images in divs with data-latest-bg attribute
    # or in img tags. We look for lh3.googleusercontent.com URLs.
    urls = set()

    # Method 1: Look for background images in style attributes
    elements = page.query_selector_all("[style*='lh3.googleusercontent.com']")
    for el in elements:
        style = el.get_attribute("style") or ""
        matches = re.findall(r'url\(["\']?(https://lh3\.googleusercontent\.com/[^"\')\s]+)["\']?\)', style)
        urls.update(matches)

    # Method 2: Look for img tags with Google Photos URLs
    img_elements = page.query_selector_all("img[src*='lh3.googleusercontent.com']")
    for img in img_elements:
        src = img.get_attribute("src")
        if src:
            urls.add(src)

    # Method 3: Look for data-latest-bg attributes
    bg_elements = page.query_selector_all("[data-latest-bg*='lh3.googleusercontent.com']")
    for el in bg_elements:
        bg = el.get_attribute("data-latest-bg")
        if bg:
            urls.add(bg)

    # Filter out avatar URLs before cleaning
    photo_urls = [url for url in urls if not is_avatar_url(url)]

    # Clean up URLs - get base URL without size parameters
    cleaned = [clean_photo_url(url) for url in photo_urls]

    # Deduplicate by base_url
    seen = set()
    unique = []
    for item in cleaned:
        if item["base_url"] not in seen:
            seen.add(item["base_url"])
            unique.append(item)

    return unique


def scroll_to_load_all(page, max_scrolls: int = 100) -> None:
    """Scroll the page to load all images (handle infinite scroll)."""
    last_height = 0
    scroll_count = 0

    while scroll_count < max_scrolls:
        # Scroll down
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1500)  # Wait for content to load

        # Check if we've reached the bottom
        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            # Try one more scroll to be sure
            page.wait_for_timeout(2000)
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                break

        last_height = new_height
        scroll_count += 1


def find_white_regions(image_array: np.ndarray, min_area: int = 1000) -> list[tuple]:
    """Find white rectangular regions that could be bib numbers.

    Returns list of (x, y, w, h) tuples for candidate regions.
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


def is_valid_bib_number(text: str) -> bool:
    """Check if text is a valid bib number (1-9999, no leading zeros)."""
    # Remove whitespace
    cleaned = text.strip().replace(" ", "")

    # Must be 1-4 digits
    if not re.match(r"^\d{1,4}$", cleaned):
        return False

    # Must not start with 0 (except for "0" itself, which is invalid for bibs)
    if cleaned.startswith("0"):
        return False

    # Must be in valid range
    num = int(cleaned)
    return 1 <= num <= 9999


def bbox_area(bbox: list) -> float:
    """Calculate the area of a bounding box (quadrilateral)."""
    # bbox is [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
    # Use shoelace formula for polygon area
    n = len(bbox)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += bbox[i][0] * bbox[j][1]
        area -= bbox[j][0] * bbox[i][1]
    return abs(area) / 2.0


def filter_small_detections(detections: list[dict], white_region_area: float,
                            min_ratio: float = 0.10) -> list[dict]:
    """Filter out detections that are too small relative to the white region.

    A legitimate bib number (even single digit like "1") should occupy at least
    ~10-15% of the white bib region. Tiny detections are usually noise.
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


def bbox_to_rect(bbox: list) -> tuple:
    """Convert a quadrilateral bbox to a bounding rectangle (x_min, y_min, x_max, y_max)."""
    x_coords = [p[0] for p in bbox]
    y_coords = [p[1] for p in bbox]
    return (min(x_coords), min(y_coords), max(x_coords), max(y_coords))


def rect_intersection_area(rect1: tuple, rect2: tuple) -> float:
    """Calculate intersection area of two rectangles."""
    x1 = max(rect1[0], rect2[0])
    y1 = max(rect1[1], rect2[1])
    x2 = min(rect1[2], rect2[2])
    y2 = min(rect1[3], rect2[3])

    if x2 <= x1 or y2 <= y1:
        return 0.0
    return (x2 - x1) * (y2 - y1)


def rect_area(rect: tuple) -> float:
    """Calculate area of a rectangle."""
    return (rect[2] - rect[0]) * (rect[3] - rect[1])


def bbox_iou(bbox1: list, bbox2: list) -> float:
    """Calculate Intersection over Union (IoU) for two bounding boxes."""
    rect1 = bbox_to_rect(bbox1)
    rect2 = bbox_to_rect(bbox2)

    intersection = rect_intersection_area(rect1, rect2)
    if intersection == 0:
        return 0.0

    area1 = rect_area(rect1)
    area2 = rect_area(rect2)
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0


def bbox_overlap_ratio(bbox1: list, bbox2: list) -> float:
    """Calculate how much of the smaller box is covered by intersection.

    This catches cases where a small box is entirely inside a larger box,
    which would have low IoU but high overlap ratio.
    """
    rect1 = bbox_to_rect(bbox1)
    rect2 = bbox_to_rect(bbox2)

    intersection = rect_intersection_area(rect1, rect2)
    if intersection == 0:
        return 0.0

    # Use the smaller box's area as denominator
    smaller_area = min(rect_area(rect1), rect_area(rect2))
    return intersection / smaller_area if smaller_area > 0 else 0.0


def is_substring_bib(short_bib: str, long_bib: str) -> bool:
    """Check if short_bib is a substring of long_bib (as a bib number fragment)."""
    return short_bib in long_bib and short_bib != long_bib


def filter_overlapping_detections(detections: list[dict], iou_threshold: float = 0.3,
                                   overlap_threshold: float = 0.7) -> list[dict]:
    """Filter overlapping detections, keeping the longer/better one.

    When two detections overlap significantly:
    - If one bib is a substring of the other (e.g., "6" vs "620"), keep the longer one
    - Otherwise, keep the one with more digits
    - If same digit count, keep higher confidence

    Uses both IoU and overlap ratio to catch both partial overlaps and
    cases where a small box is entirely inside a larger one.
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


def detect_bib_numbers(
    reader: easyocr.Reader,
    image_data: bytes,
    preprocess_config: PreprocessConfig | None = None,
) -> tuple[list[dict], np.ndarray | None]:
    """Detect bib numbers in an image using EasyOCR.

    Focuses on white rectangular regions (typical bib appearance) and
    filters for valid bib number patterns.

    Args:
        reader: EasyOCR reader instance
        image_data: Raw image bytes
        preprocess_config: Optional preprocessing configuration

    Returns:
        Tuple of (list of detections, grayscale image used for OCR)
    """
    # Load image from bytes
    image = Image.open(io.BytesIO(image_data))

    # Convert to RGB if necessary
    if image.mode != "RGB":
        image = image.convert("RGB")

    # Convert to numpy array
    image_array = np.array(image)

    # Apply preprocessing pipeline
    preprocess_result = run_pipeline(image_array, preprocess_config)

    # Use resized image for OCR if available (more consistent kernel behavior)
    if preprocess_result.resized is not None:
        ocr_image = preprocess_result.resized
        ocr_grayscale = preprocess_result.resized_grayscale
        scale_factor = preprocess_result.scale_factor
    else:
        ocr_image = image_array
        ocr_grayscale = preprocess_result.grayscale
        scale_factor = 1.0

    # Find candidate white regions on the OCR image (resized if preprocessing enabled)
    white_regions = find_white_regions(ocr_image)

    all_detections = []

    if white_regions:
        # OCR only on candidate regions
        for (x, y, w, h) in white_regions:
            region_area = w * h
            region = ocr_image[y:y+h, x:x+w]
            results = reader.readtext(region)

            region_detections = []
            for bbox, text, confidence in results:
                cleaned = text.strip().replace(" ", "")

                if is_valid_bib_number(cleaned) and confidence > 0.4:
                    # Adjust bbox coordinates to full OCR image (before scaling back)
                    bbox_adjusted = [[int(p[0]) + x, int(p[1]) + y] for p in bbox]
                    region_detections.append({
                        "bib_number": cleaned,
                        "confidence": float(confidence),
                        "bbox": bbox_adjusted,
                    })

            # Filter out tiny detections relative to this white region
            filtered = filter_small_detections(region_detections, region_area)
            all_detections.extend(filtered)

    # Also run OCR on full image as fallback (in case region detection missed something)
    # For full image scan, we can't use white region filtering, so use higher confidence
    results = reader.readtext(ocr_image)
    for bbox, text, confidence in results:
        cleaned = text.strip().replace(" ", "")

        if is_valid_bib_number(cleaned) and confidence > 0.5:  # Higher threshold for full image
            bbox_native = [[int(coord) for coord in point] for point in bbox]
            all_detections.append({
                "bib_number": cleaned,
                "confidence": float(confidence),
                "bbox": bbox_native,
            })

    # Filter overlapping detections (e.g., "620" vs "6", "20")
    all_detections = filter_overlapping_detections(all_detections)

    # Deduplicate: keep highest confidence for each bib number
    best_detections = {}
    for det in all_detections:
        bib = det["bib_number"]
        if bib not in best_detections or det["confidence"] > best_detections[bib]["confidence"]:
            best_detections[bib] = det

    final_detections = list(best_detections.values())

    # Map bounding boxes back to original image coordinates if we resized
    if scale_factor != 1.0:
        for det in final_detections:
            det["bbox"] = [
                [int(p[0] * scale_factor), int(p[1] * scale_factor)]
                for p in det["bbox"]
            ]

    # Return detections and the grayscale image used (at OCR resolution for visualization)
    return final_detections, ocr_grayscale


def get_cache_path(photo_url: str) -> Path:
    """Generate a cache file path for a photo URL."""
    # Use hash of URL for unique filename
    url_hash = hashlib.md5(photo_url.encode()).hexdigest()[:12]
    return CACHE_DIR / f"{url_hash}.jpg"


def cache_image(image_data: bytes, cache_path: Path) -> None:
    """Save image data to cache."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_path.write_bytes(image_data)


def load_from_cache(cache_path: Path) -> bytes | None:
    """Load image from cache if it exists."""
    if cache_path.exists():
        return cache_path.read_bytes()
    return None


def scan_album(album_url: str, skip_existing: bool = True, limit: int | None = None) -> dict:
    """Scan a Google Photos album and detect bib numbers.

    Args:
        album_url: URL of the Google Photos album
        skip_existing: Skip photos that have already been scanned
        limit: Maximum number of photos to process (None for all)
    """
    # Validate URL
    parsed = urlparse(album_url)
    if "photos.google.com" not in parsed.netloc and "photos.app.goo.gl" not in parsed.netloc:
        print(f"Warning: URL doesn't appear to be a Google Photos URL: {album_url}")

    # Initialize EasyOCR (downloads model on first run)
    print("Initializing EasyOCR...")
    reader = easyocr.Reader(["en"], gpu=False)

    # Initialize database
    conn = db.get_connection()

    stats = {
        "photos_found": 0,
        "photos_scanned": 0,
        "photos_skipped": 0,
        "bibs_detected": 0,
    }

    print("Launching browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        print(f"Loading album: {album_url}")
        page.goto(album_url, wait_until="networkidle")
        page.wait_for_timeout(3000)  # Extra wait for dynamic content

        print("Scrolling to load all images...")
        scroll_to_load_all(page)

        print("Extracting image URLs...")
        images = extract_image_urls(page)
        stats["photos_found"] = len(images)
        print(f"Found {len(images)} images")

        browser.close()

    if not images:
        print("No images found. The album may be empty or require authentication.")
        return stats

    # Apply limit if specified
    if limit is not None:
        images = images[:limit]
        print(f"Processing limited to {limit} images")

    # Process each image
    print("\nScanning images for bib numbers...")
    for img_info in tqdm(images, desc="Processing"):
        photo_url = img_info["photo_url"]
        thumbnail_url = img_info["thumbnail_url"]

        # Skip if already scanned
        if skip_existing and db.photo_exists(conn, photo_url):
            stats["photos_skipped"] += 1
            continue

        try:
            # Check cache first, then download
            cache_path = get_cache_path(photo_url)
            image_data = load_from_cache(cache_path)

            if image_data is None:
                image_data = download_image(photo_url)
                cache_image(image_data, cache_path)

            # Use preprocessing for better detection
            preprocess_config = PreprocessConfig(target_width=1280)
            bibs, ocr_grayscale = detect_bib_numbers(reader, image_data, preprocess_config)

            # Generate grayscale bounding box image if detections found
            if bibs and ocr_grayscale is not None:
                gray_bbox_path = get_gray_bbox_path(cache_path)
                # Bboxes are already in original coordinates, need to scale down for grayscale
                gray_h, gray_w = ocr_grayscale.shape[:2]
                orig_h, orig_w = cv2.imdecode(
                    np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR
                ).shape[:2]
                gray_scale = gray_w / orig_w
                scaled_bibs = []
                for bib in bibs:
                    scaled_bib = bib.copy()
                    scaled_bib["bbox"] = [
                        [int(p[0] * gray_scale), int(p[1] * gray_scale)]
                        for p in bib["bbox"]
                    ]
                    scaled_bibs.append(scaled_bib)
                draw_bounding_boxes_on_gray(ocr_grayscale, scaled_bibs, gray_bbox_path)

            # Save to database with cache path
            photo_id = db.insert_photo(
                conn, album_url, photo_url, thumbnail_url,
                cache_path=str(cache_path)
            )

            for bib in bibs:
                db.insert_bib_detection(
                    conn,
                    photo_id,
                    bib["bib_number"],
                    bib["confidence"],
                    bib["bbox"],
                )
                stats["bibs_detected"] += 1

            stats["photos_scanned"] += 1

        except Exception as e:
            print(f"\nError processing image: {e}")
            continue

    conn.close()
    return stats


def scan_local_directory(directory: str, skip_existing: bool = True, limit: int | None = None) -> dict:
    """Scan a local directory of images and detect bib numbers.

    Args:
        directory: Path to directory containing images
        skip_existing: Skip photos that have already been scanned
        limit: Maximum number of photos to process (None for all)

    Returns:
        Stats dictionary with counts
    """
    dir_path = Path(directory).resolve()
    if not dir_path.is_dir():
        print(f"Error: {directory} is not a valid directory")
        return {"photos_found": 0, "photos_scanned": 0, "photos_skipped": 0, "bibs_detected": 0}

    # Find all image files
    image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
    image_files = []
    for ext in image_extensions:
        image_files.extend(dir_path.glob(f"*{ext}"))
        image_files.extend(dir_path.glob(f"*{ext.upper()}"))

    # Remove duplicates and sort
    image_files = sorted(set(image_files))

    # Initialize EasyOCR
    print("Initializing EasyOCR...")
    reader = easyocr.Reader(["en"], gpu=False)

    # Initialize database
    conn = db.get_connection()

    stats = {
        "photos_found": len(image_files),
        "photos_scanned": 0,
        "photos_skipped": 0,
        "bibs_detected": 0,
    }

    print(f"Found {len(image_files)} images in {dir_path}")

    if not image_files:
        print("No images found.")
        return stats

    # Apply limit if specified
    if limit is not None:
        image_files = image_files[:limit]
        print(f"Processing limited to {limit} images")

    # Use directory path as "album_url" for database grouping
    album_url = f"local:{dir_path}"

    # Process each image
    print("\nScanning images for bib numbers...")
    for image_path in tqdm(image_files, desc="Processing"):
        # Use the file path as the photo_url (unique identifier)
        photo_url = str(image_path)

        # Skip if already scanned
        if skip_existing and db.photo_exists(conn, photo_url):
            stats["photos_skipped"] += 1
            continue

        try:
            # Read image directly from file (no caching needed, files stay intact)
            image_data = image_path.read_bytes()

            # Use preprocessing for better detection
            preprocess_config = PreprocessConfig(target_width=1280)
            bibs, ocr_grayscale = detect_bib_numbers(reader, image_data, preprocess_config)

            # Generate grayscale bounding box image if detections found
            # Store in cache directory with a hash of the original path
            if bibs and ocr_grayscale is not None:
                # Create a cache path based on hash of original file path
                path_hash = hashlib.md5(str(image_path).encode()).hexdigest()[:12]
                cache_path = CACHE_DIR / f"{path_hash}.jpg"

                gray_bbox_path = get_gray_bbox_path(cache_path)
                # Bboxes are in original coordinates, scale down for grayscale
                gray_h, gray_w = ocr_grayscale.shape[:2]
                with Image.open(image_path) as img:
                    orig_w, orig_h = img.size
                gray_scale = gray_w / orig_w
                scaled_bibs = []
                for bib in bibs:
                    scaled_bib = bib.copy()
                    scaled_bib["bbox"] = [
                        [int(p[0] * gray_scale), int(p[1] * gray_scale)]
                        for p in bib["bbox"]
                    ]
                    scaled_bibs.append(scaled_bib)
                draw_bounding_boxes_on_gray(ocr_grayscale, scaled_bibs, gray_bbox_path)

                # Store the original file path as cache_path so web viewer can find it
                db_cache_path = str(cache_path)
            else:
                db_cache_path = None

            # Save to database
            # For local files, use file:// URL for thumbnail to allow viewing
            thumbnail_url = f"file://{image_path}"
            photo_id = db.insert_photo(
                conn, album_url, photo_url, thumbnail_url,
                cache_path=db_cache_path
            )

            for bib in bibs:
                db.insert_bib_detection(
                    conn,
                    photo_id,
                    bib["bib_number"],
                    bib["confidence"],
                    bib["bbox"],
                )
                stats["bibs_detected"] += 1

            stats["photos_scanned"] += 1

        except Exception as e:
            print(f"\nError processing {image_path.name}: {e}")
            continue

    conn.close()
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Scan images for bib numbers. Supports Google Photos albums or local directories."
    )
    parser.add_argument(
        "source",
        help="URL of Google Photos album OR path to local directory"
    )
    parser.add_argument(
        "--rescan",
        action="store_true",
        help="Rescan photos that have already been processed"
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=None,
        help="Maximum number of photos to process (default: all)"
    )

    args = parser.parse_args()

    # Determine if source is a URL or local path
    source = args.source
    is_url = source.startswith("http://") or source.startswith("https://") or "photos.google.com" in source or "photos.app.goo.gl" in source

    if is_url:
        stats = scan_album(source, skip_existing=not args.rescan, limit=args.limit)
    else:
        # Treat as local directory
        stats = scan_local_directory(source, skip_existing=not args.rescan, limit=args.limit)

    print("\n" + "=" * 50)
    print("Scan Complete!")
    print("=" * 50)
    print(f"Photos found:   {stats['photos_found']}")
    print(f"Photos scanned: {stats['photos_scanned']}")
    print(f"Photos skipped: {stats['photos_skipped']}")
    print(f"Bibs detected:  {stats['bibs_detected']}")
    print("\nResults saved to bibs.db")
    print("Query example: sqlite3 bibs.db \"SELECT * FROM bib_detections LIMIT 10\"")


if __name__ == "__main__":
    main()

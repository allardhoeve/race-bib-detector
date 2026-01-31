#!/usr/bin/env python3
"""Scan a Google Photos shared album and detect bib numbers using OCR."""

import argparse
import hashlib
import io
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import cv2
import easyocr
import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright
from tqdm import tqdm

import db
from utils import CACHE_DIR, clean_photo_url, download_image


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

    # Clean up URLs - get base URL without size parameters
    cleaned = [clean_photo_url(url) for url in urls]

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


def detect_bib_numbers(reader: easyocr.Reader, image_data: bytes) -> list[dict]:
    """Detect bib numbers in an image using EasyOCR.

    Focuses on white rectangular regions (typical bib appearance) and
    filters for valid bib number patterns.
    """
    # Load image from bytes
    image = Image.open(io.BytesIO(image_data))

    # Convert to RGB if necessary
    if image.mode != "RGB":
        image = image.convert("RGB")

    # Convert to numpy array
    image_array = np.array(image)

    # Find candidate white regions
    white_regions = find_white_regions(image_array)

    all_detections = []

    if white_regions:
        # OCR only on candidate regions
        for (x, y, w, h) in white_regions:
            region = image_array[y:y+h, x:x+w]
            results = reader.readtext(region)

            for bbox, text, confidence in results:
                cleaned = text.strip().replace(" ", "")

                if is_valid_bib_number(cleaned) and confidence > 0.4:
                    # Adjust bbox coordinates to full image
                    bbox_adjusted = [[int(p[0]) + x, int(p[1]) + y] for p in bbox]
                    all_detections.append({
                        "bib_number": cleaned,
                        "confidence": float(confidence),
                        "bbox": bbox_adjusted,
                    })

    # Also run OCR on full image as fallback (in case region detection missed something)
    results = reader.readtext(image_array)
    for bbox, text, confidence in results:
        cleaned = text.strip().replace(" ", "")

        if is_valid_bib_number(cleaned) and confidence > 0.5:  # Higher threshold for full image
            bbox_native = [[int(coord) for coord in point] for point in bbox]
            all_detections.append({
                "bib_number": cleaned,
                "confidence": float(confidence),
                "bbox": bbox_native,
            })

    # Deduplicate: keep highest confidence for each bib number
    best_detections = {}
    for det in all_detections:
        bib = det["bib_number"]
        if bib not in best_detections or det["confidence"] > best_detections[bib]["confidence"]:
            best_detections[bib] = det

    return list(best_detections.values())


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


def scan_album(album_url: str, skip_existing: bool = True) -> dict:
    """Scan a Google Photos album and detect bib numbers."""
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

            bibs = detect_bib_numbers(reader, image_data)

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


def main():
    parser = argparse.ArgumentParser(
        description="Scan a Google Photos shared album for bib numbers"
    )
    parser.add_argument(
        "album_url",
        help="URL of the Google Photos shared album"
    )
    parser.add_argument(
        "--rescan",
        action="store_true",
        help="Rescan photos that have already been processed"
    )

    args = parser.parse_args()

    stats = scan_album(args.album_url, skip_existing=not args.rescan)

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

"""
Google Photos album scraping.

Functions for extracting images from shared Google Photos albums.
"""

import logging
import re
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from logging_utils import configure_logging, LOG_LEVEL_CHOICES
from utils import clean_photo_url

logger = logging.getLogger(__name__)

def is_avatar_url(url: str) -> bool:
    """Check if a URL is likely a user avatar rather than an album photo.

    Avatars typically have:
    - Small size parameters (=s32, =s48, =s64, =s96, etc.)
    - Or contain 'AAAAALX' pattern (Google profile photos)

    Args:
        url: URL to check.

    Returns:
        True if URL appears to be an avatar.
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


def _extract_image_urls(page) -> list[dict]:
    """Extract image URLs from the Google Photos album page.

    Args:
        page: Playwright page object.

    Returns:
        List of dicts with photo_url, thumbnail_url, base_url.
    """
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


def _scroll_to_load_all(page, max_scrolls: int = 100) -> None:
    """Scroll the page to load all images (handle infinite scroll).

    Args:
        page: Playwright page object.
        max_scrolls: Maximum number of scroll attempts.
    """
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


def extract_images_from_album(album_url: str) -> list[dict]:
    """Extract all image URLs from a Google Photos album.

    Args:
        album_url: URL of the Google Photos shared album.

    Returns:
        List of dicts with photo_url, thumbnail_url, base_url.
    """
    # Validate URL
    parsed = urlparse(album_url)
    if "photos.google.com" not in parsed.netloc and "photos.app.goo.gl" not in parsed.netloc:
        logger.warning("URL doesn't appear to be a Google Photos URL: %s", album_url)

    logger.info("Launching browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        logger.info("Loading album: %s", album_url)
        page.goto(album_url, wait_until="networkidle")
        page.wait_for_timeout(3000)  # Extra wait for dynamic content

        logger.info("Scrolling to load all images...")
        _scroll_to_load_all(page)

        logger.info("Extracting image URLs...")
        images = _extract_image_urls(page)

        browser.close()

    return images


def main() -> int:
    """CLI helper to test album extraction."""
    import argparse

    parser = argparse.ArgumentParser(description="Extract Google Photos album images")
    parser.add_argument("album_url", help="Google Photos shared album URL")
    parser.add_argument(
        "--log-level",
        choices=LOG_LEVEL_CHOICES,
        help="Set log verbosity (debug, info, warning, error, critical)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase log verbosity (use -vv for more detail)",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="count",
        default=0,
        help="Reduce log verbosity (use -qq for errors only)",
    )

    args = parser.parse_args()
    configure_logging(args.log_level, args.verbose, args.quiet)
    images = extract_images_from_album(args.album_url)
    logger.info("Extracted %s images", len(images))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Bib number validation and parsing.

Functions for validating whether detected text represents a valid bib number.
"""

import re


def is_valid_bib_number(text: str) -> bool:
    """Check if text is a valid bib number (1-9999, no leading zeros).

    Args:
        text: Text to validate.

    Returns:
        True if text represents a valid bib number.
    """
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


def is_substring_bib(short_bib: str, long_bib: str) -> bool:
    """Check if short_bib is a substring of long_bib (as a bib number fragment).

    Used to detect when OCR has detected both "620" and "6" or "20" from the
    same bib - we want to keep only the full number.

    Args:
        short_bib: Potentially shorter bib number.
        long_bib: Potentially longer bib number.

    Returns:
        True if short_bib is a proper substring of long_bib.
    """
    return short_bib in long_bib and short_bib != long_bib

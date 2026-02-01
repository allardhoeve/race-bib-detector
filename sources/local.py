"""
Local directory image scanning.

Functions for finding and loading images from local directories.
"""

from pathlib import Path

# Supported image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}


def scan_local_images(directory: str) -> list[Path]:
    """Find all image files in a directory.

    Args:
        directory: Path to directory to scan.

    Returns:
        Sorted list of image file paths.

    Raises:
        ValueError: If directory doesn't exist or isn't a directory.
    """
    dir_path = Path(directory).resolve()
    if not dir_path.is_dir():
        raise ValueError(f"{directory} is not a valid directory")

    # Find all image files
    image_files = []
    for ext in IMAGE_EXTENSIONS:
        image_files.extend(dir_path.glob(f"*{ext}"))
        image_files.extend(dir_path.glob(f"*{ext.upper()}"))

    # Remove duplicates and sort
    return sorted(set(image_files))

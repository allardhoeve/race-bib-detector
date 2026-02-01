"""
Local directory image scanning.

Functions for finding and loading images from local directories.
"""

from pathlib import Path

# Supported image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}


def scan_local_images(path: str) -> list[Path]:
    """Find all image files in a directory or return a single image file.

    Args:
        path: Path to directory or single image file to scan.

    Returns:
        Sorted list of image file paths.

    Raises:
        ValueError: If path doesn't exist or isn't a valid image/directory.
    """
    file_path = Path(path).resolve()

    # Handle single file
    if file_path.is_file():
        if file_path.suffix.lower() in IMAGE_EXTENSIONS:
            return [file_path]
        raise ValueError(f"{path} is not a supported image file")

    # Handle directory
    if not file_path.is_dir():
        raise ValueError(f"{path} is not a valid file or directory")

    # Find all image files
    image_files = []
    for ext in IMAGE_EXTENSIONS:
        image_files.extend(file_path.glob(f"*{ext}"))
        image_files.extend(file_path.glob(f"*{ext.upper()}"))

    # Remove duplicates and sort
    return sorted(set(image_files))

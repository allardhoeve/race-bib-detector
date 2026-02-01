"""
Image normalization functions for preprocessing.

All functions are pure: they take an input and return a new output without
mutating the original array. This ensures predictable behavior and makes
testing straightforward.
"""

import numpy as np
import cv2


def to_grayscale(img: np.ndarray, dtype: np.dtype = np.uint8) -> np.ndarray:
    """Convert an image to grayscale.

    Pure function: returns a new array without modifying the input.

    Args:
        img: Input image. Can be:
             - RGB/BGR (3 channels): Will be converted to grayscale
             - RGBA/BGRA (4 channels): Alpha channel is dropped, then converted
             - Grayscale (1 channel or 2D): Returns a copy with normalized dtype
        dtype: Output dtype. Default is uint8 for CV2 compatibility.

    Returns:
        Grayscale image as 2D numpy array with the specified dtype.

    Raises:
        ValueError: If input is not a valid image array.
        TypeError: If img is not a numpy array.

    Examples:
        >>> rgb = np.zeros((100, 200, 3), dtype=np.uint8)
        >>> gray = to_grayscale(rgb)
        >>> gray.shape
        (100, 200)
        >>> gray.dtype
        dtype('uint8')
    """
    if not isinstance(img, np.ndarray):
        raise TypeError(f"Expected numpy.ndarray, got {type(img).__name__}")

    if img.ndim < 2 or img.ndim > 3:
        raise ValueError(
            f"Image must be 2D or 3D array, got {img.ndim}D array with shape {img.shape}"
        )

    if img.size == 0:
        raise ValueError("Image array is empty")

    # Handle different input formats
    if img.ndim == 2:
        # Already grayscale - return a copy with normalized dtype
        result = img.copy()
    elif img.ndim == 3:
        channels = img.shape[2]
        if channels == 1:
            # Single channel - squeeze and copy
            result = img[:, :, 0].copy()
        elif channels == 3:
            # RGB - convert to grayscale
            # Note: cv2.cvtColor expects BGR by default, but since we're
            # computing luminance, the slight difference in weights is acceptable
            # for our use case. For strict RGB, we use the ITU-R BT.601 formula.
            result = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        elif channels == 4:
            # RGBA - drop alpha and convert
            rgb = img[:, :, :3]
            result = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        else:
            raise ValueError(
                f"Unsupported number of channels: {channels}. "
                "Expected 1, 3 (RGB), or 4 (RGBA)."
            )
    else:
        # Should not reach here due to earlier check, but be defensive
        raise ValueError(f"Unexpected array dimensions: {img.ndim}")

    # Normalize dtype
    if result.dtype != dtype:
        # Handle type conversion carefully
        if np.issubdtype(dtype, np.integer):
            # For integer types, clip to valid range
            info = np.iinfo(dtype)
            result = np.clip(result, info.min, info.max).astype(dtype)
        else:
            result = result.astype(dtype)

    return result


def resize_to_width(
    img: np.ndarray,
    target_width: int,
    interpolation: int = cv2.INTER_AREA,
) -> tuple[np.ndarray, float]:
    """Resize image to a target width, preserving aspect ratio.

    Pure function: returns a new array without modifying the input.

    Args:
        img: Input image (2D grayscale or 3D color).
        target_width: Desired width in pixels.
        interpolation: OpenCV interpolation method. Default is INTER_AREA
                      which is best for downscaling. For upscaling, consider
                      INTER_LINEAR or INTER_CUBIC.

    Returns:
        Tuple of:
        - Resized image with same dtype as input
        - Scale factor (original_width / target_width) for coordinate mapping

    Raises:
        ValueError: If target_width is not positive or image is invalid.
        TypeError: If img is not a numpy array.

    Examples:
        >>> img = np.zeros((1000, 2000, 3), dtype=np.uint8)
        >>> resized, scale = resize_to_width(img, 1000)
        >>> resized.shape
        (500, 1000, 3)
        >>> scale
        2.0
    """
    if not isinstance(img, np.ndarray):
        raise TypeError(f"Expected numpy.ndarray, got {type(img).__name__}")

    if img.ndim < 2 or img.ndim > 3:
        raise ValueError(
            f"Image must be 2D or 3D array, got {img.ndim}D array with shape {img.shape}"
        )

    if img.size == 0:
        raise ValueError("Image array is empty")

    if not isinstance(target_width, int):
        raise TypeError(f"target_width must be int, got {type(target_width).__name__}")

    if target_width <= 0:
        raise ValueError(f"target_width must be positive, got {target_width}")

    # Get current dimensions
    original_height, original_width = img.shape[:2]

    # Skip resizing if already at target width
    if original_width == target_width:
        return img.copy(), 1.0

    # Calculate new dimensions preserving aspect ratio
    scale_factor = original_width / target_width
    new_height = int(round(original_height / scale_factor))

    # Ensure minimum height of 1
    new_height = max(1, new_height)

    # Choose interpolation based on whether we're upscaling or downscaling
    if target_width > original_width:
        # Upscaling - INTER_LINEAR is better than INTER_AREA
        actual_interpolation = cv2.INTER_LINEAR
    else:
        # Downscaling - use specified interpolation (default INTER_AREA)
        actual_interpolation = interpolation

    # Resize
    resized = cv2.resize(
        img,
        (target_width, new_height),
        interpolation=actual_interpolation,
    )

    return resized, scale_factor

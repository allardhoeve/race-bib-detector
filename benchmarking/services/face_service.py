"""Business logic for face photo labeling."""

import io
import logging
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from benchmarking.face_embeddings import build_embedding_index, find_top_k, EmbeddingIndex
from benchmarking.ghost import load_suggestion_store
from benchmarking.ground_truth import (
    FaceBox,
    FacePhotoLabel,
    load_face_ground_truth,
    save_face_ground_truth,
)
from benchmarking.label_utils import find_hash_by_prefix
from benchmarking.photo_index import load_photo_index, get_path_for_hash

logger = logging.getLogger(__name__)

PHOTOS_DIR = Path(__file__).parent.parent.parent / "photos"

# Module-level cache for the embedding index. Reset only on process restart.
# Tests that need a fresh index should call `_embedding_index_cache.clear()`.
_embedding_index_cache: dict[str, EmbeddingIndex] = {}


def get_embedding_index() -> EmbeddingIndex | None:
    """Build or return cached embedding index. Returns None on failure."""
    if 'index' not in _embedding_index_cache:
        try:
            from faces.embedder import get_face_embedder
            embedder = get_face_embedder()
            face_gt = load_face_ground_truth()
            index = load_photo_index()
            _embedding_index_cache['index'] = build_embedding_index(
                face_gt, PHOTOS_DIR, index, embedder
            )
            logger.info("Built embedding index: %d faces", _embedding_index_cache['index'].size)
        except Exception as e:
            logger.exception("Failed to build embedding index: %s", e)
            return None
    return _embedding_index_cache['index']


def load_image_rgb(photo_path: Path):
    """Load a photo file and return an RGB numpy array, or None on failure."""
    image_data = photo_path.read_bytes()
    arr = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        return None
    return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)


def get_face_label(content_hash: str) -> dict | None:
    """Return serialised face label data for a hash prefix, or None if not found.

    Returns a dict ready to be passed to jsonify():
        {full_hash, boxes, suggestions, tags}
    """
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return None

    face_gt = load_face_ground_truth()
    label = face_gt.get_photo(full_hash)

    store = load_suggestion_store()
    photo_sugg = store.get(full_hash)
    suggestions = [s.to_dict() for s in photo_sugg.faces] if photo_sugg else []

    if label:
        return {
            'full_hash': full_hash,
            'boxes': [b.to_dict() for b in label.boxes],
            'suggestions': suggestions,
            'tags': label.tags,
        }
    return {
        'full_hash': full_hash,
        'boxes': [],
        'suggestions': suggestions,
        'tags': [],
    }


def save_face_label(content_hash: str, boxes_data: list[dict] | None,
                    tags: list[str]) -> None:
    """Construct a FacePhotoLabel and persist it.

    Raises ValueError or TypeError on invalid data.
    """
    face_gt = load_face_ground_truth()
    boxes = [FaceBox.from_dict(b) for b in boxes_data] if boxes_data else []
    label = FacePhotoLabel(content_hash=content_hash, boxes=boxes, tags=tags)
    face_gt.add_photo(label)
    save_face_ground_truth(face_gt)


def get_face_crop_jpeg(content_hash: str, box_index: int) -> bytes | None:
    """Return JPEG bytes of a labeled face crop, or None if not found."""
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return None

    face_gt = load_face_ground_truth()
    label = face_gt.get_photo(full_hash)
    if not label or box_index < 0 or box_index >= len(label.boxes):
        return None

    box = label.boxes[box_index]
    if not box.has_coords:
        return None

    photo_path = get_path_for_hash(full_hash, PHOTOS_DIR, index)
    if not photo_path or not photo_path.exists():
        return None

    img = Image.open(photo_path)
    w, h = img.size
    left = int(box.x * w)
    upper = int(box.y * h)
    right = int((box.x + box.w) * w)
    lower = int((box.y + box.h) * h)
    crop = img.crop((left, upper, right, lower))

    buf = io.BytesIO()
    crop.save(buf, format='JPEG', quality=85)
    buf.seek(0)
    return buf.read()


def get_identity_suggestions(content_hash: str, box_x: float, box_y: float,
                              box_w: float, box_h: float, k: int = 5) -> list[dict] | None:
    """Return top-k identity suggestions for a face box region.

    Returns None if the photo is not found. Returns [] if no embedding index
    is available or the face crop yields no embeddings.
    """
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return None

    emb_index = get_embedding_index()
    if emb_index is None or emb_index.size == 0:
        return []

    photo_path = get_path_for_hash(full_hash, PHOTOS_DIR, index)
    if not photo_path or not photo_path.exists():
        return None

    image_rgb = load_image_rgb(photo_path)
    if image_rgb is None:
        return None

    h_px, w_px = image_rgb.shape[:2]
    from geometry import rect_to_bbox
    bbox = rect_to_bbox(int(box_x * w_px), int(box_y * h_px),
                        int(box_w * w_px), int(box_h * h_px))

    from faces.embedder import get_face_embedder
    embeddings = get_face_embedder().embed(image_rgb, [bbox])
    if not embeddings:
        return []

    matches = find_top_k(embeddings[0], emb_index, k=k)
    return [m.to_dict() for m in matches]

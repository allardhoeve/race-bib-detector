"""Face JSON API endpoints."""

import io
import logging
from pathlib import Path
from typing import TypedDict

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Query
from PIL import Image
from starlette.responses import StreamingResponse

from benchmarking.face_embeddings import (
    IdentityMatch,
    build_embedding_index,
    find_top_k,
    EmbeddingIndex,
)
from benchmarking.frozen_check import require_not_frozen
from benchmarking.ghost import FaceSuggestion, load_suggestion_store
from benchmarking.ground_truth import (
    FacePhotoLabel,
    load_face_ground_truth,
    save_face_ground_truth,
)
from benchmarking.label_utils import find_hash_by_prefix
from benchmarking.photo_index import load_photo_index, get_path_for_hash
from benchmarking.photo_metadata import (
    PhotoMetadata,
    load_photo_metadata,
    save_photo_metadata,
)
from benchmarking.schemas import (
    FaceBoxOut,
    FaceSuggestionOut,
    GetFaceBoxesResponse,
    IdentityMatchOut,
    IdentitySuggestionsResponse,
    SaveFaceBoxesRequest,
)
from pipeline_types import FaceBox

logger = logging.getLogger(__name__)

PHOTOS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "photos"

api_faces_router = APIRouter()


# ---- Face label helpers (inlined from services/face_service.py) -----------


class FaceLabelData(TypedDict):
    full_hash: str
    boxes: list[FaceBox]
    suggestions: list[FaceSuggestion]
    tags: list[str]


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


def _load_image_rgb(photo_path: Path):
    """Load a photo file and return an RGB numpy array, or None on failure."""
    image_data = photo_path.read_bytes()
    arr = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        return None
    return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)


def _get_face_label(content_hash: str) -> FaceLabelData | None:
    """Return typed face label data for a hash prefix, or None if not found."""
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return None

    face_gt = load_face_ground_truth()
    label = face_gt.get_photo(full_hash)

    store = load_suggestion_store()
    photo_sugg = store.get(full_hash)
    suggestions: list[FaceSuggestion] = photo_sugg.faces if photo_sugg else []

    meta_store = load_photo_metadata()
    meta = meta_store.get(full_hash)

    if label:
        return FaceLabelData(
            full_hash=full_hash,
            boxes=label.boxes,
            suggestions=suggestions,
            tags=meta.face_tags if meta else [],
        )
    return FaceLabelData(
        full_hash=full_hash,
        boxes=[],
        suggestions=suggestions,
        tags=meta.face_tags if meta else [],
    )


def _save_face_label(content_hash: str, boxes: list[FaceBox],
                     tags: list[str]) -> None:
    """Construct a FacePhotoLabel and persist it, plus save tags to PhotoMetadata."""
    face_gt = load_face_ground_truth()
    label = FacePhotoLabel(content_hash=content_hash, boxes=boxes, labeled=True)
    face_gt.add_photo(label)
    save_face_ground_truth(face_gt)

    meta_store = load_photo_metadata()
    meta = meta_store.get(content_hash) or PhotoMetadata(paths=[])
    meta.face_tags = tags
    meta_store.set(content_hash, meta)
    save_photo_metadata(meta_store)


def _get_face_crop_jpeg(content_hash: str, box_index: int) -> bytes | None:
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


def _get_identity_suggestions(content_hash: str, box_x: float, box_y: float,
                              box_w: float, box_h: float, k: int = 5) -> list[IdentityMatch] | None:
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

    image_rgb = _load_image_rgb(photo_path)
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

    return find_top_k(embeddings[0], emb_index, k=k)


# ---- Route handlers -------------------------------------------------------


@api_faces_router.get('/api/faces/{content_hash}', response_model=GetFaceBoxesResponse)
async def get_face_boxes(content_hash: str) -> GetFaceBoxesResponse:
    """Get face boxes, suggestions, and tags."""
    result = _get_face_label(content_hash)
    if result is None:
        raise HTTPException(status_code=404, detail='Photo not found')
    return GetFaceBoxesResponse(
        boxes=[FaceBoxOut.model_validate(b.model_dump()) for b in result['boxes']],
        suggestions=[FaceSuggestionOut.model_validate(s.to_dict()) for s in result['suggestions']],
        tags=result['tags'],
    )


@api_faces_router.put('/api/faces/{content_hash}')
async def save_face_label(content_hash: str, request: SaveFaceBoxesRequest):
    """Save face boxes/tags for a photo label. Replaces all existing data."""
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        raise HTTPException(status_code=404, detail='Photo not found')

    require_not_frozen(full_hash)

    try:
        boxes = [FaceBox.model_validate(b.model_dump()) for b in request.boxes]
        _save_face_label(
            content_hash=full_hash,
            boxes=boxes,
            tags=request.face_tags,
        )
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {'status': 'ok'}


@api_faces_router.get('/api/faces/{content_hash}/suggestions',
                      response_model=IdentitySuggestionsResponse)
async def face_identity_suggestions(
    content_hash: str,
    box_x: str | None = Query(default=None),
    box_y: str | None = Query(default=None),
    box_w: str | None = Query(default=None),
    box_h: str | None = Query(default=None),
    k: int = Query(default=5),
) -> IdentitySuggestionsResponse:
    """Suggest identities for a face box using embedding similarity."""
    try:
        box_x_f = float(box_x)
        box_y_f = float(box_y)
        box_w_f = float(box_w)
        box_h_f = float(box_h)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail='Missing or invalid box_x/box_y/box_w/box_h')

    result = _get_identity_suggestions(content_hash, box_x_f, box_y_f, box_w_f, box_h_f, k=k)
    if result is None:
        raise HTTPException(status_code=404, detail='Photo not found')
    return IdentitySuggestionsResponse(
        suggestions=[IdentityMatchOut.model_validate(m.to_dict()) for m in result]
    )


@api_faces_router.get('/api/faces/{content_hash}/crop/{box_index}')
async def face_crop(content_hash: str, box_index: int):
    """Return a JPEG crop of a labeled face box."""
    jpeg_bytes = _get_face_crop_jpeg(content_hash, box_index)
    if jpeg_bytes is None:
        raise HTTPException(status_code=404)
    return StreamingResponse(io.BytesIO(jpeg_bytes), media_type='image/jpeg')

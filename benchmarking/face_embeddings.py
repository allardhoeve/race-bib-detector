"""Embedding cache and top-k identity search for the labeling UI.

Maps (content_hash, box_index) -> embedding vector for identity-labeled faces.
Used to suggest likely identities when labeling new face boxes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from benchmarking.ground_truth import FaceGroundTruth, FaceBox
from benchmarking.photo_index import get_path_for_hash

logger = logging.getLogger(__name__)


@dataclass
class IdentityMatch:
    """A single identity suggestion from the embedding index."""

    identity: str
    similarity: float
    content_hash: str
    box_index: int

    def to_dict(self) -> dict:
        return {
            "identity": self.identity,
            "similarity": round(self.similarity, 4),
            "content_hash": self.content_hash,
            "box_index": self.box_index,
        }


@dataclass
class EmbeddingIndex:
    """In-memory index of face embeddings for identity-labeled boxes."""

    embeddings: np.ndarray  # (N, dim) float32
    identities: list[str] = field(default_factory=list)
    content_hashes: list[str] = field(default_factory=list)
    box_indices: list[int] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.identities)


def build_embedding_index(
    face_gt: FaceGroundTruth,
    photos_dir: Path,
    photo_index: dict[str, list[str]],
    embedder,
) -> EmbeddingIndex:
    """Compute embeddings for all identity-labeled face boxes.

    Only includes boxes with scope="keep" and a non-empty identity.
    """
    all_embeddings: list[np.ndarray] = []
    all_identities: list[str] = []
    all_hashes: list[str] = []
    all_box_indices: list[int] = []

    for content_hash, label in face_gt.photos.items():
        boxes_to_embed: list[tuple[int, FaceBox]] = []
        for i, box in enumerate(label.boxes):
            if box.scope == "keep" and box.identity and box.has_coords:
                boxes_to_embed.append((i, box))

        if not boxes_to_embed:
            continue

        # Load the photo
        photo_path = get_path_for_hash(content_hash, photos_dir, photo_index)
        if photo_path is None or not photo_path.exists():
            logger.debug("Photo not found for %s, skipping", content_hash[:8])
            continue

        image_data = photo_path.read_bytes()
        image_array = cv2.imdecode(
            np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR
        )
        if image_array is None:
            logger.warning("Failed to decode image: %s", content_hash[:8])
            continue
        image_rgb = cv2.cvtColor(image_array, cv2.COLOR_BGR2RGB)
        h, w = image_rgb.shape[:2]

        # Convert normalised coords to pixel bbox polygons
        from geometry import rect_to_bbox

        bboxes = []
        for _, box in boxes_to_embed:
            px = int(box.x * w)
            py = int(box.y * h)
            pw = int(box.w * w)
            ph = int(box.h * h)
            bboxes.append(rect_to_bbox(px, py, pw, ph))

        embeddings = embedder.embed(image_rgb, bboxes)

        for (box_idx, box), embedding in zip(boxes_to_embed, embeddings):
            all_embeddings.append(embedding)
            all_identities.append(box.identity)
            all_hashes.append(content_hash)
            all_box_indices.append(box_idx)

    if not all_embeddings:
        dim = embedder.model_info().embedding_dim
        return EmbeddingIndex(
            embeddings=np.empty((0, dim), dtype=np.float32),
        )

    return EmbeddingIndex(
        embeddings=np.stack(all_embeddings).astype(np.float32),
        identities=all_identities,
        content_hashes=all_hashes,
        box_indices=all_box_indices,
    )


def find_top_k(
    query_embedding: np.ndarray,
    index: EmbeddingIndex,
    k: int = 5,
) -> list[IdentityMatch]:
    """Return top-k identity matches by cosine similarity.

    Deduplicates by identity — returns the highest similarity per unique name.
    """
    if index.size == 0:
        return []

    # L2-normalise query
    query = query_embedding.astype(np.float32)
    norm = np.linalg.norm(query)
    if norm > 0:
        query = query / norm

    # L2-normalise index (should already be, but be safe)
    index_norms = np.linalg.norm(index.embeddings, axis=1, keepdims=True)
    index_norms[index_norms == 0] = 1.0
    normed_index = index.embeddings / index_norms

    similarities = normed_index @ query  # (N,)

    # Deduplicate by identity: keep best match per name
    best_by_identity: dict[str, tuple[float, int]] = {}
    for i, (identity, sim) in enumerate(zip(index.identities, similarities)):
        sim_f = float(sim)
        if identity not in best_by_identity or sim_f > best_by_identity[identity][0]:
            best_by_identity[identity] = (sim_f, i)

    # Sort by similarity descending, take top-k
    ranked = sorted(best_by_identity.items(), key=lambda x: x[1][0], reverse=True)
    results: list[IdentityMatch] = []
    for identity, (sim, idx) in ranked[:k]:
        results.append(
            IdentityMatch(
                identity=identity,
                similarity=sim,
                content_hash=index.content_hashes[idx],
                box_index=index.box_indices[idx],
            )
        )
    return results

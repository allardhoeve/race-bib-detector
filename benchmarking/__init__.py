"""Benchmarking module for bib detection evaluation."""

from .scanner import scan_photos, compute_content_hash, build_photo_index
from .ground_truth import (
    BibBox,
    FaceBox,
    BibPhotoLabel,
    FacePhotoLabel,
    BibGroundTruth,
    FaceGroundTruth,
    load_bib_ground_truth,
    save_bib_ground_truth,
    load_face_ground_truth,
    save_face_ground_truth,
    migrate_from_legacy,
    BIB_BOX_TAGS,
    FACE_SCOPE_TAGS,
    BIB_PHOTO_TAGS,
    FACE_PHOTO_TAGS,
    ALLOWED_TAGS,
    ALLOWED_FACE_TAGS,
    ALLOWED_SPLITS,
)
from .photo_index import (
    load_photo_index,
    save_photo_index,
    update_photo_index,
    get_path_for_hash,
)
from .scoring import (
    compute_iou,
    match_boxes,
    MatchResult,
    BibScorecard,
    FaceScorecard,
    score_bibs,
    score_faces,
    format_scorecard,
)
# Runner imports are lazy because runner.py depends on heavy ML packages
# (easyocr, cv2, torch) that may not be installed in all environments.
try:
    from .runner import (
        run_benchmark,
        compare_to_baseline,
        load_baseline,
        save_baseline,
        BenchmarkRun,
        BenchmarkMetrics,
        PhotoResult,
        RunMetadata,
    )
except ImportError:
    pass

__all__ = [
    # Scanner
    "scan_photos",
    "compute_content_hash",
    "build_photo_index",
    # Ground truth
    "BibBox",
    "FaceBox",
    "BibPhotoLabel",
    "FacePhotoLabel",
    "BibGroundTruth",
    "FaceGroundTruth",
    "load_bib_ground_truth",
    "save_bib_ground_truth",
    "load_face_ground_truth",
    "save_face_ground_truth",
    "migrate_from_legacy",
    "BIB_BOX_TAGS",
    "FACE_SCOPE_TAGS",
    "BIB_PHOTO_TAGS",
    "FACE_PHOTO_TAGS",
    "ALLOWED_TAGS",
    "ALLOWED_FACE_TAGS",
    "ALLOWED_SPLITS",
    # Photo index
    "load_photo_index",
    "save_photo_index",
    "update_photo_index",
    "get_path_for_hash",
    # Scoring
    "compute_iou",
    "match_boxes",
    "MatchResult",
    "BibScorecard",
    "FaceScorecard",
    "score_bibs",
    "score_faces",
    "format_scorecard",
    # Runner
    "run_benchmark",
    "compare_to_baseline",
    "load_baseline",
    "save_baseline",
    "BenchmarkRun",
    "BenchmarkMetrics",
    "PhotoResult",
    "RunMetadata",
]

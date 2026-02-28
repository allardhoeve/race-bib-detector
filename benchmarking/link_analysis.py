"""Empirical bib-face spatial analysis (task-042).

Measures actual spatial relationships between linked bib and face boxes
in the ground truth data and compares against the _torso_region() heuristic.

Usage:
    venv/bin/python -m benchmarking.link_analysis
"""

from __future__ import annotations

import math
import statistics

from benchmarking.ground_truth import (
    BibBox,
    FaceBox,
    load_bib_ground_truth,
    load_face_ground_truth,
    load_link_ground_truth,
)
from config import AUTOLINK_TORSO_BOTTOM, AUTOLINK_TORSO_HALF_WIDTH, AUTOLINK_TORSO_TOP
from faces.autolink import _torso_region


def _box_center(box: BibBox | FaceBox) -> tuple[float, float]:
    """Return (cx, cy) of a box."""
    return (box.x + box.w / 2, box.y + box.h / 2)


def _inside_torso(bib_cx: float, bib_cy: float, face: FaceBox) -> bool:
    """Check if a bib centroid falls inside the _torso_region() of a face."""
    tx, ty, tw, th = _torso_region(face)
    return tx <= bib_cx <= tx + tw and ty <= bib_cy <= ty + th


def _percentile(data: list[float], p: float) -> float:
    """Simple percentile (linear interpolation)."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    return sorted_data[f] * (c - k) + sorted_data[c] * (k - f)


def main() -> None:
    bib_gt = load_bib_ground_truth()
    face_gt = load_face_ground_truth()
    link_gt = load_link_ground_truth()

    vertical_offsets: list[float] = []
    horizontal_offsets: list[float] = []
    distances: list[float] = []
    angles_deg: list[float] = []
    inside_torso_count = 0
    total_pairs = 0
    skipped_no_coords = 0

    for content_hash, links in link_gt.photos.items():
        if not links:
            continue

        bib_photo = bib_gt.get_photo(content_hash)
        face_photo = face_gt.get_photo(content_hash)
        if not bib_photo or not face_photo:
            continue

        for link in links:
            if link.bib_index >= len(bib_photo.boxes):
                continue
            if link.face_index >= len(face_photo.boxes):
                continue

            bib = bib_photo.boxes[link.bib_index]
            face = face_photo.boxes[link.face_index]

            if not bib.has_coords or not face.has_coords:
                skipped_no_coords += 1
                continue

            total_pairs += 1

            bib_cx, bib_cy = _box_center(bib)
            face_cx, face_cy = _box_center(face)
            fh = face.h

            # Offsets normalised by face height
            dy = (bib_cy - face_cy) / fh
            dx = (bib_cx - face_cx) / fh

            vertical_offsets.append(dy)
            horizontal_offsets.append(dx)
            distances.append(math.sqrt(dx**2 + dy**2))
            # atan2(dx, dy): 0° = directly below, positive = right
            angles_deg.append(math.degrees(math.atan2(dx, dy)))

            if _inside_torso(bib_cx, bib_cy, face):
                inside_torso_count += 1

    # --- Print results ---
    print("=" * 60)
    print("Empirical bib-face spatial analysis")
    print("=" * 60)
    print()
    print(f"Linked pairs with coords: {total_pairs}")
    print(f"Skipped (no coords):      {skipped_no_coords}")
    print()

    if not total_pairs:
        print("No valid pairs to analyse.")
        return

    def _print_stats(label: str, data: list[float]) -> None:
        print(f"  {label}:")
        print(f"    median = {statistics.median(data):+.2f}")
        print(f"    mean   = {statistics.mean(data):+.2f}")
        print(f"    stdev  = {statistics.stdev(data):.2f}" if len(data) > 1 else "    stdev  = n/a")
        print(f"    p5     = {_percentile(data, 5):+.2f}")
        print(f"    p95    = {_percentile(data, 95):+.2f}")
        print(f"    min    = {min(data):+.2f}")
        print(f"    max    = {max(data):+.2f}")
        print()

    print("--- Offsets (in face-heights) ---")
    print()
    _print_stats("Vertical (bib below face)", vertical_offsets)
    _print_stats("Horizontal (bib right of face)", horizontal_offsets)
    _print_stats("Euclidean distance", distances)
    _print_stats("Angle (0°=below, +right)", angles_deg)

    # --- Coverage ---
    coverage = inside_torso_count / total_pairs * 100
    print("--- Current _torso_region() coverage ---")
    print()
    print(f"  {inside_torso_count}/{total_pairs} GT links inside heuristic = {coverage:.1f}%")
    print()

    # --- Suggested multipliers ---
    v_p5 = _percentile(vertical_offsets, 5)
    v_p95 = _percentile(vertical_offsets, 95)
    h_p5 = _percentile(horizontal_offsets, 5)
    h_p95 = _percentile(horizontal_offsets, 95)

    print("--- p5–p95 envelope (tightest 90% region) ---")
    print()
    print(f"  Vertical range:   {v_p5:+.2f} to {v_p95:+.2f} face-heights from face center")
    print(f"  Horizontal range: {h_p5:+.2f} to {h_p95:+.2f} face-heights from face center")
    print()

    print("--- Current config (config.py) ---")
    print()
    print(f"  AUTOLINK_TORSO_TOP        = {AUTOLINK_TORSO_TOP}")
    print(f"  AUTOLINK_TORSO_BOTTOM     = {AUTOLINK_TORSO_BOTTOM}")
    print(f"  AUTOLINK_TORSO_HALF_WIDTH = {AUTOLINK_TORSO_HALF_WIDTH}")
    print()
    print(f"  → vertical:   +{AUTOLINK_TORSO_TOP:.2f} to +{AUTOLINK_TORSO_BOTTOM:.2f} fh from face center")
    print(f"  → horizontal: ±{AUTOLINK_TORSO_HALF_WIDTH:.2f} fh from face center")


if __name__ == "__main__":
    main()

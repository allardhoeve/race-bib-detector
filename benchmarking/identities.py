"""Face identity management — persists known face identities for autocomplete."""

from __future__ import annotations

import json
from pathlib import Path


def get_identities_path() -> Path:
    return Path(__file__).parent / "face_identities.json"


def load_identities(path: Path | None = None) -> list[str]:
    if path is None:
        path = get_identities_path()
    if not path.exists():
        return []
    with open(path, "r") as f:
        return sorted(json.load(f))


def save_identities(identities: list[str], path: Path | None = None) -> None:
    if path is None:
        path = get_identities_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(sorted(set(identities)), f, indent=2)


def add_identity(name: str, path: Path | None = None) -> list[str]:
    ids = load_identities(path)
    if name not in ids:
        ids.append(name)
    ids = sorted(set(ids))
    save_identities(ids, path)
    return ids


def rename_identity(old: str, new: str, path: Path | None = None) -> list[str]:
    """Rename an identity in the list. Returns the updated sorted list."""
    ids = load_identities(path)
    ids = [new if name == old else name for name in ids]
    ids = sorted(set(ids))
    save_identities(ids, path)
    return ids


def rename_identity_across_gt(old_name: str, new_name: str) -> tuple[int, list[str]]:
    """Rename an identity in face GT boxes and the identities list.

    Returns (updated_count, new_identity_list).
    Raises ValueError if old_name == new_name.
    """
    from benchmarking.ground_truth import load_face_ground_truth, save_face_ground_truth

    if old_name == new_name:
        raise ValueError("old_name and new_name are the same")

    face_gt = load_face_ground_truth()
    updated_count = 0
    for label in face_gt.photos.values():
        for box in label.boxes:
            if box.identity == old_name:
                box.identity = new_name
                updated_count += 1
    save_face_ground_truth(face_gt)

    ids = rename_identity(old_name, new_name)
    return updated_count, ids

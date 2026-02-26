"""Business logic for identity CRUD and bulk-rename across face GT."""

from benchmarking.ground_truth import load_face_ground_truth, save_face_ground_truth
from benchmarking.identities import load_identities, add_identity, rename_identity


def list_identities() -> list[str]:
    return load_identities()


def create_identity(name: str) -> list[str]:
    """Add a new identity. Returns updated identity list."""
    return add_identity(name)


def rename_identity_across_gt(old_name: str, new_name: str) -> tuple[int, list[str]]:
    """Rename an identity in face GT boxes and the identities list.

    Returns (updated_count, new_identity_list).
    Raises ValueError if old_name == new_name.
    """
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

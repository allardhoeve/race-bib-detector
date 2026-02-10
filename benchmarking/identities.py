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

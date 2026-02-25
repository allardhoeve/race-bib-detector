# Task 006: Staging and frozen benchmark sets

Step 1 from `todo_benchmark.md`. Independent of all other pending tasks.

## Goal

Add the concepts of a **staging set** (the mutable working set of benchmark photos) and
**frozen sets** (named snapshots for reproducible evaluation). Implement `bnr benchmark freeze`.

## Background

Currently `photos/` holds all photos and there's no way to create a stable named snapshot.
Frozen sets allow comparing two pipeline versions against the exact same photo set.

## On-disk layout

```
benchmarking/
  staging/            ← symlinks or copies of photos being evaluated (optional, see note)
  frozen/
    <name>/
      index.json      ← {content_hash: relative_photo_path} subset of the main photo index
      metadata.json   ← {name, created_at, photo_count, description}
```

**Design choice**: frozen sets store an index file (list of content hashes + paths), not
copies of photos. Photos remain in `photos/`. This avoids disk duplication and keeps
freeze fast.

## New file: `benchmarking/sets.py`

```python
"""Staging and frozen benchmark set management."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


FROZEN_DIR = Path(__file__).parent / "frozen"


@dataclass
class BenchmarkSnapshotMetadata:
    name: str
    created_at: str          # ISO 8601
    photo_count: int
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "created_at": self.created_at,
            "photo_count": self.photo_count,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BenchmarkSnapshotMetadata:
        return cls(
            name=data["name"],
            created_at=data["created_at"],
            photo_count=data["photo_count"],
            description=data.get("description", ""),
        )


@dataclass
class BenchmarkSnapshot:
    metadata: BenchmarkSnapshotMetadata
    hashes: list[str]             # content hashes in this set
    index: dict[str, str]         # content_hash → relative photo path

    @property
    def path(self) -> Path:
        return FROZEN_DIR / self.metadata.name

    def save(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        with open(self.path / "index.json", "w") as f:
            json.dump({"hashes": self.hashes, "index": self.index}, f, indent=2)
        with open(self.path / "metadata.json", "w") as f:
            json.dump(self.metadata.to_dict(), f, indent=2)

    @classmethod
    def load(cls, name: str) -> BenchmarkSnapshot:
        path = FROZEN_DIR / name
        with open(path / "metadata.json") as f:
            metadata = BenchmarkSnapshotMetadata.from_dict(json.load(f))
        with open(path / "index.json") as f:
            data = json.load(f)
        return cls(metadata=metadata, hashes=data["hashes"], index=data["index"])


def list_snapshots() -> list[BenchmarkSnapshotMetadata]:
    """Return metadata for all frozen sets, sorted by created_at descending."""
    if not FROZEN_DIR.exists():
        return []
    result = []
    for d in FROZEN_DIR.iterdir():
        meta_path = d / "metadata.json"
        if meta_path.exists():
            with open(meta_path) as f:
                result.append(BenchmarkSnapshotMetadata.from_dict(json.load(f)))
    result.sort(key=lambda m: m.created_at, reverse=True)
    return result


def freeze(
    name: str,
    hashes: list[str],
    index: dict[str, str],
    description: str = "",
) -> BenchmarkSnapshot:
    """Create a new frozen snapshot. Raises ValueError if name already exists."""
    target = FROZEN_DIR / name
    if target.exists():
        raise ValueError(f"Snapshot already exists: {name!r}")
    metadata = BenchmarkSnapshotMetadata(
        name=name,
        created_at=datetime.now(timezone.utc).isoformat(),
        photo_count=len(hashes),
        description=description,
    )
    snapshot = BenchmarkSnapshot(metadata=metadata, hashes=hashes, index=index)
    snapshot.save()
    return snapshot
```

## CLI changes: `benchmarking/cli.py`

### New command: `benchmark freeze`

Add a subparser and handler for `bnr benchmark freeze --name <name>`.

```python
def cmd_freeze(args: argparse.Namespace) -> int:
    """Create a frozen snapshot of the current benchmark photo set."""
    from benchmarking.sets import freeze, BenchmarkSnapshot

    name = args.name
    description = args.description or ""

    # Validate name (alphanumeric, hyphens, underscores only)
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        print(f"Error: name must be alphanumeric with hyphens/underscores: {name!r}")
        return 1

    index = load_photo_index()
    if not index:
        print("Error: no photos in index. Run 'bnr benchmark scan' first.")
        return 1

    # Only freeze labeled photos (or all, with --all flag)
    if args.all:
        hashes = sorted(index.keys())
    else:
        gt = load_bib_ground_truth()
        hashes = sorted(h for h in index if gt.get_photo(h) and gt.get_photo(h).labeled)
        if not hashes:
            print("No labeled photos to freeze. Use --all to freeze unlabeled photos too.")
            return 1

    try:
        snapshot = freeze(
            name=name,
            hashes=hashes,
            index={h: index[h] for h in hashes},
            description=description,
        )
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    print(f"Snapshot '{name}' created:")
    print(f"  Photos: {snapshot.metadata.photo_count}")
    print(f"  Path:   {snapshot.path}")
    return 0
```

### New command: `benchmark frozen-list`

```python
def cmd_frozen_list(args: argparse.Namespace) -> int:
    """List all frozen benchmark snapshots."""
    from benchmarking.sets import list_snapshots
    snapshots = list_snapshots()
    if not snapshots:
        print("No snapshots yet. Use 'bnr benchmark freeze --name <name>'.")
        return 0
    print(f"{'Name':<30} {'Photos':>8} {'Created':<12} Description")
    print("-" * 70)
    for m in snapshots:
        print(f"{m.name:<30} {m.photo_count:>8} {m.created_at[:10]:<12} {m.description}")
    return 0
```

### Subparser additions in `build_parser()`

```python
# In the subparsers block:
freeze_parser = subparsers.add_parser("freeze", help="Freeze current photo set as a named snapshot")
freeze_parser.add_argument("--name", required=True, help="Name for the snapshot")
freeze_parser.add_argument("--description", default="", help="Optional description")
freeze_parser.add_argument("--all", action="store_true", help="Include unlabeled photos")

subparsers.add_parser("frozen-list", help="List all frozen snapshots")
```

Add `"freeze": cmd_freeze` and `"frozen-list": cmd_frozen_list` to the commands dict in `main()`.

## Tests

Add `tests/test_sets.py`:

- `test_freeze_creates_files()` — freeze a set, verify `metadata.json` + `index.json` exist.
- `test_freeze_name_conflict()` — freezing same name twice raises `ValueError`.
- `test_list_snapshots()` — verify sorted order and metadata fields.
- `test_snapshot_load_roundtrip()` — `freeze()` then `BenchmarkSnapshot.load()` gives same data.

### Isolating `FROZEN_DIR` in tests

`FROZEN_DIR` is a module-level constant in `benchmarking/sets.py`. All functions and
`BenchmarkSnapshot.path` read it at call time, so monkeypatching the constant redirects
all disk I/O to `tmp_path`:

```python
import benchmarking.sets as sets_module

def test_freeze_creates_files(tmp_path, monkeypatch):
    monkeypatch.setattr(sets_module, "FROZEN_DIR", tmp_path / "frozen")
    snapshot = sets_module.freeze(
        name="v1",
        hashes=["abc123"],
        index={"abc123": "photo_a.jpg"},
    )
    assert (tmp_path / "frozen" / "v1" / "metadata.json").exists()
    assert (tmp_path / "frozen" / "v1" / "index.json").exists()
```

Apply the same `monkeypatch.setattr(sets_module, "FROZEN_DIR", ...)` in every test that
touches the filesystem.

## Scope boundaries

- **In scope**: `sets.py` data layer, `freeze`/`frozen-list` CLI commands.
- **Out of scope**: using frozen sets in `run_benchmark()` (that's a later step), web UI for frozen sets, runner integration.

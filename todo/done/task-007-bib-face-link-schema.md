# Task 007: Bib-face link ground truth schema

Step 5 (part 1/4) from `todo_benchmark.md`. Data layer only — no UI or scoring.

## Goal

Design and implement the storage schema for bib-face associations. A link records that
a specific bib box and a specific face box in the same photo depict the same person.

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Where to store? | Separate `benchmarking/bib_face_links.json` — keeps bib and face GT files clean |
| Schema format | `{"version": 3, "photos": {"<hash>": [[bib_idx, face_idx], ...]}}` |
| What do indices reference? | Positions in `bib_ground_truth.json`.photos[hash].boxes and `face_ground_truth.json`.photos[hash].boxes |
| Staleness on box edit | Known limitation — documented, not guarded against at this stage |
| Many-to-many? | Yes — one face can link to multiple bibs (relay team) and vice versa |

## Changes: `benchmarking/ground_truth.py`

Add the following after the `FaceGroundTruth` class and before the file-paths section.

### New dataclass: `BibFaceLink`

```python
@dataclass
class BibFaceLink:
    """A directed association between a bib box and a face box in the same photo.

    Indices reference positions in ``BibPhotoLabel.boxes`` and
    ``FacePhotoLabel.boxes`` for the same content hash.

    Note: links become stale if boxes are reordered or deleted after linking.
    No automatic repair is done — re-label if the link list looks wrong.
    """
    bib_index: int    # index into BibPhotoLabel.boxes
    face_index: int   # index into FacePhotoLabel.boxes

    def to_pair(self) -> list[int]:
        return [self.bib_index, self.face_index]

    @classmethod
    def from_pair(cls, pair: list[int]) -> BibFaceLink:
        return cls(bib_index=pair[0], face_index=pair[1])
```

### New container: `LinkGroundTruth`

```python
@dataclass
class LinkGroundTruth:
    """Container for all bib-face link ground truth associations."""

    version: int = SCHEMA_VERSION
    photos: dict[str, list[BibFaceLink]] = field(default_factory=dict)

    def get_links(self, content_hash: str) -> list[BibFaceLink]:
        return self.photos.get(content_hash, [])

    def set_links(self, content_hash: str, links: list[BibFaceLink]) -> None:
        self.photos[content_hash] = links

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "photos": {
                h: [lnk.to_pair() for lnk in links]
                for h, links in self.photos.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> LinkGroundTruth:
        gt = cls(version=data.get("version", SCHEMA_VERSION))
        for content_hash, pairs in data.get("photos", {}).items():
            gt.photos[content_hash] = [BibFaceLink.from_pair(p) for p in pairs]
        return gt
```

### New file-path functions and load/save

Add these alongside the existing `get_bib_ground_truth_path` / `get_face_ground_truth_path`:

```python
def get_link_ground_truth_path() -> Path:
    return Path(__file__).parent / "bib_face_links.json"


def load_link_ground_truth(path: Path | None = None) -> LinkGroundTruth:
    if path is None:
        path = get_link_ground_truth_path()
    if not path.exists():
        return LinkGroundTruth()
    with open(path, "r") as f:
        return LinkGroundTruth.from_dict(json.load(f))


def save_link_ground_truth(gt: LinkGroundTruth, path: Path | None = None) -> None:
    if path is None:
        path = get_link_ground_truth_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(gt.to_dict(), f, indent=2)
```

## Tests

Add `tests/test_link_ground_truth.py`:

- `test_roundtrip_empty()` — `LinkGroundTruth()` → `to_dict()` → `from_dict()` is identity.
- `test_roundtrip_with_links()` — save and reload preserves links.
- `test_get_links_missing_hash()` — returns `[]` for unknown hash.
- `test_set_and_get_links()` — set then get gives same list.
- `test_load_missing_file(tmp_path)` — `load_link_ground_truth(tmp_path / "x.json")` returns empty `LinkGroundTruth`.
- `test_save_load_roundtrip(tmp_path)` — save then load gives identical data.

## Scope boundaries

- **In scope**: `BibFaceLink`, `LinkGroundTruth`, `load_link_ground_truth`, `save_link_ground_truth`, tests.
- **Out of scope**: API routes (task-008), UI (task-009), scoring (task-010).
- **Do not** modify existing bib or face GT classes.

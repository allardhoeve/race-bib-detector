# Task 018: Misc small cleanups (review leftovers)

Batch of independent one- or two-line fixes. Each item is self-contained.

## Items

### A. Fix Image.open() resource leak (`routes_face.py:328`)

`face_crop()` opens a PIL image without a context manager. If `img.crop()` raises,
the file handle leaks.

**Current (lines 328–334):**
```python
img = Image.open(photo_path)
w, h = img.size
left = int(box.x * w)
upper = int(box.y * h)
right = int((box.x + box.w) * w)
lower = int((box.y + box.h) * h)
crop = img.crop((left, upper, right, lower))
```

**Fix:**
```python
with Image.open(photo_path) as img:
    w, h = img.size
    left = int(box.x * w)
    upper = int(box.y * h)
    right = int((box.x + box.w) * w)
    lower = int((box.y + box.h) * h)
    crop = img.crop((left, upper, right, lower))
```

---

### B. Remove redundant `import cv2 as _cv2` inside function (`routes_face.py:277`)

`cv2` is imported at module level (line 8). Line 277 re-imports it under a private
alias inside `face_identity_suggestions()`. Delete line 277 and replace `_cv2` with
`cv2` on lines 279–284.

Note: this is also covered in task-013 if that task is done first — skip here if so.

---

### C. Remove duplicate `get_face_embedder` import (`routes_face.py:254, 295`)

`face_identity_suggestions()` imports `get_face_embedder` twice (lines 254 and 295).
Remove the second import at line 295 and use the name already bound at line 254.

Note: also covered by task-013 — skip here if done there.

---

### D. Deduplicate `get_filtered_hashes` / `get_filtered_face_hashes` (`label_utils.py:14–62`)

The two functions are ~75 % identical. Introduce a shared inner function:

```python
def _filtered_hashes(filter_type: str, all_hashes: set[str], labeled_hashes: set[str]) -> list[str]:
    if filter_type == 'unlabeled':
        return sorted(all_hashes - labeled_hashes)
    elif filter_type == 'labeled':
        return sorted(all_hashes & labeled_hashes)
    return sorted(all_hashes)
```

Then both public functions reduce to:
```python
def get_filtered_hashes(filter_type: str) -> list[str]:
    index = load_photo_index()
    all_hashes = set(index.keys())
    if filter_type == 'all':
        return sorted(all_hashes)
    gt = load_bib_ground_truth()
    labeled = {h for h, lbl in gt.photos.items() if lbl.labeled}
    return _filtered_hashes(filter_type, all_hashes, labeled)

def get_filtered_face_hashes(filter_type: str) -> list[str]:
    index = load_photo_index()
    all_hashes = set(index.keys())
    if filter_type == 'all':
        return sorted(all_hashes)
    gt = load_face_ground_truth()
    labeled = {h for h, lbl in gt.photos.items() if is_face_labeled(lbl)}
    return _filtered_hashes(filter_type, all_hashes, labeled)
```

---

### E. Remove `rect_iou()` alias in `geometry.py:57–59`

Covered fully by task-016. Skip here if that task is done first.

## Test strategy

Follow [docs/REFACTORING.md](../../docs/REFACTORING.md).

- Run `pytest tests/` after the batch.
- Items A–C are in `routes_face.py` — test by running the face labeling route tests.
- Item D is in `label_utils.py` — test by running bib + face label route tests.

## Scope boundaries

- **In scope**: the specific lines listed above. No logic changes.
- **Out of scope**: any architectural changes, new features, API changes.

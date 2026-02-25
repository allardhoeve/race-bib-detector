# Task 016: Consolidate duplicate IoU implementations

Small cleanup. Independent of all other pending tasks.

## Goal

Two IoU functions exist with different coordinate conventions:

| Location | Function | Format |
|---|---|---|
| `geometry.py:32–54` | `compute_intersection_over_union(rect_a, rect_b)` | `(x1, y1, x2, y2)` |
| `geometry.py:57–59` | `rect_iou(rect_a, rect_b)` | same — alias only |
| `benchmarking/scoring.py:27–60` | `compute_iou(box_a, box_b)` | `(x, y, w, h)` |

The two coordinate formats reflect real domain differences (pixel rects vs normalised
boxes) so both implementations should stay. The problem is:
1. `rect_iou()` is a no-op alias for `compute_intersection_over_union()` — one of them
   should be removed.
2. Callers must know which module and which format to use; the names don't signal the
   difference clearly.

## Changes

### 1. Remove `rect_iou()` alias from `geometry.py`

Delete lines 57–59:
```python
def rect_iou(rect_a: tuple[int, int, int, int], rect_b: tuple[int, int, int, int]) -> float:
    """Compute IoU between two rectangles (x1, y1, x2, y2)."""
    return compute_intersection_over_union(rect_a, rect_b)
```

Check callers with:
```
grep -rn "rect_iou" .
```
If any callers use `rect_iou`, update them to call `compute_intersection_over_union`
directly (or rename `compute_intersection_over_union` to `rect_iou` and remove the
alias — either direction is fine, just pick one name).

### 2. Rename `compute_intersection_over_union` to `rect_iou` (optional alternative)

If the shorter name is preferred: rename the main function to `rect_iou` and remove the
alias. Update all callers (currently only `geometry.py` internal usage + any external
caller found by grep).

### 3. Add a docstring note to `compute_iou` in scoring.py

To help future readers understand why there are two functions:
```python
def compute_iou(box_a: Box, box_b: Box) -> float:
    """Compute IoU between two (x, y, w, h) normalised boxes.

    Uses (x, y, w, h) format as used throughout the benchmarking schema.
    See also ``geometry.compute_intersection_over_union`` for pixel-rect
    (x1, y1, x2, y2) format.
    """
```

## Test strategy

Follow [docs/REFACTORING.md](../../docs/REFACTORING.md).

- Run `grep -rn "rect_iou\|compute_intersection_over_union" .` before and after to
  confirm no dangling references.
- Run `pytest tests/` — geometry and scoring tests should pass unchanged.

## Scope boundaries

- **In scope**: removing the alias, optionally renaming, adding a cross-reference
  docstring comment.
- **Out of scope**: changing either IoU formula, merging the two implementations into
  one, or changing coordinate formats.

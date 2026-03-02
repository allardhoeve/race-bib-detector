# Task 097: Modern Python idioms — Optional syntax, emptiness checks, dead parameters

From code review (REVIEW.md, 2026-03-02). Independent of other tasks.

## Goal

Modernize typing syntax (`Optional[X]` → `X | None`), replace non-idiomatic emptiness checks, and remove an unused function parameter.

## Background

The project targets Python >=3.14 where `X | None` is the standard union syntax. A few files still use the older `Optional[X]` import. Two places use `len(x) == 0` instead of the idiomatic `not x`. One function accepts a `tags` parameter that no call site provides.

## Context

- `db.py:7` — `from typing import Optional, TYPE_CHECKING`
- `db.py:235-236, 293-295, 456-457, 639, 654, 662` — `Optional[str]`, `Optional[int]`, `Optional[dict]`
- `preprocessing/config.py:9` — `from typing import Optional, Any`
- `preprocessing/config.py:48` — `target_width: Optional[int] = TARGET_WIDTH`
- `benchmarking/cli/commands/benchmark.py:205` — `if len(matches) == 0:`
- `benchmarking/runner.py:329` — `if len(expected_set) == 0:`
- `benchmarking/runner.py:298-342` — `compute_photo_result()` accepts unused `tags` parameter

## Changes

### Modified: `db.py`

Replace all `Optional[X]` with `X | None`. Remove `Optional` from the typing import (keep `TYPE_CHECKING`).

### Modified: `preprocessing/config.py`

Replace `Optional[int]` with `int | None`. Remove `Optional` from the typing import (keep `Any`).

### Modified: `benchmarking/cli/commands/benchmark.py`

```python
# Before (line 205)
if len(matches) == 0:

# After
if not matches:
```

### Modified: `benchmarking/runner.py`

```python
# Before (line 329)
if len(expected_set) == 0:

# After
if not expected_set:
```

**Remove unused `tags` parameter** from `compute_photo_result()` (line 302): verify no call site passes `tags`, then remove the parameter and always pass `[]` to `PhotoResult`.

## Tests

No new tests needed — these are syntactic/signature changes. Existing tests cover behavior.

## Verification

```bash
venv/bin/python -m pytest -v
```

Grep to confirm no `Optional` imports remain outside venv:

```bash
grep -r "from typing import.*Optional" --include="*.py" --exclude-dir=venv --exclude-dir=.venv .
```

## Acceptance criteria

- [ ] All existing tests still pass (`venv/bin/python -m pytest`)
- [ ] No `Optional[X]` usage in project source (outside venv)
- [ ] No `len(x) == 0` patterns remain
- [ ] `compute_photo_result()` no longer accepts `tags` parameter
- [ ] All call sites of `compute_photo_result()` verified and updated

## Scope boundaries

- **In scope**: `Optional` → `X | None`, `len() == 0` → `not`, dead parameter removal
- **Out of scope**: adding type annotations where none exist, other typing modernizations
- **Do not** change runtime behavior of any function

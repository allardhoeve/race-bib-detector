# Task 107: Extract and test label parsing from cmd_label

Depends on nothing. Deferred priority — tackle after tasks 100-105.

**TDD approach: `tdd: strangler rewrite`** (for the extracted functions)

## Goal

The `cmd_label` function in `benchmarking/cli/commands/photos.py` (6% coverage) contains bib-number parsing, tag validation, and ground-truth mutation logic buried inside a CLI handler. Extract the pure parsing logic into testable functions, then cover them.

## Background

Coverage analysis (2026-03-02) found `cmd_label` (lines 201-282) entirely untested. The CLI handler mixes argument parsing with business logic. The fix is to extract the validation/parsing into pure functions that can be tested without argparse, then leave the CLI handler as a thin shell (acceptable gap).

## Context

- `benchmarking/cli/commands/photos.py` — `cmd_label()` lines 201-282
- `benchmarking/ground_truth.py` — `BibBox`, `BibPhotoLabel`, `BIB_PHOTO_TAGS`
- The function does three things: (1) parse bib numbers from comma string, (2) validate tags against allowed set, (3) update ground truth. Items 1 and 2 are extractable pure functions.

## Changes

### Modified: `benchmarking/cli/commands/photos.py`

Extract two functions:

```python
def parse_bib_boxes(bibs_str: str) -> list[BibBox]:
    """Parse comma-separated bib numbers into BibBox objects.

    Raises ValueError if any entry is not a valid integer.
    """

def validate_tags(tags_str: str, allowed: set[str]) -> list[str]:
    """Parse comma-separated tags and validate against allowed set.

    Raises ValueError if any tag is not in the allowed set.
    """
```

`cmd_label` calls these instead of inline parsing.

## Tests

### New: `tests/benchmarking/test_label_parsing.py`

**`parse_bib_boxes`**:
- `test_single_bib()` — `"42"` → one BibBox with number="42"
- `test_multiple_bibs()` — `"42, 123"` → two BibBoxes
- `test_empty_string()` — `""` → empty list
- `test_invalid_bib_raises()` — `"abc"` → ValueError
- `test_whitespace_handling()` — `" 42 , 123 "` → correct parse

**`validate_tags`**:
- `test_valid_tags()` — known tags accepted
- `test_invalid_tag_raises()` — unknown tag raises ValueError with message
- `test_empty_string()` — `""` → empty list

## Acceptance criteria

- [ ] All existing tests still pass (`venv/bin/python -m pytest`)
- [ ] `parse_bib_boxes` and `validate_tags` fully covered
- [ ] `cmd_label` uses extracted functions (no inline parsing)
- [ ] `cmd_label` itself remains untested (acceptable — thin CLI shell)

## Scope boundaries

- **In scope**: extract + test parsing logic from `cmd_label`
- **Out of scope**: other `cmd_*` functions in `photos.py`, ground truth persistence logic
- **Do not** change the external behavior of `cmd_label`

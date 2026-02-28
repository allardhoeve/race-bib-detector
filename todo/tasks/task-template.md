# Task NNN: <short title>

Depends on task-NNN. Independent of task-NNN.

## Goal

<!-- What this task accomplishes in 1–3 sentences. -->

## Background

<!-- Why this is needed. Reference relevant design docs, decisions, or constraints. -->

## Context

<!-- Bullet list of relevant files with one-line descriptions of what each provides.
     Also note conclusions from previous research to avoid redoing work. -->

- `path/to/file.py` — what it provides or why it's relevant
- `tests/test_foo.py` — existing test patterns to follow

## Constraints

<!-- Remove this section if not necessary. -->

## Design decisions (resolved)

<!-- Remove this section if not applicable. -->

| Question | Decision |
|----------|----------|
| … | … |

## Changes

<!-- Use one H3 per file. Prefix with New: or Modified: -->

### New: `path/to/new_file.py`

```python
# paste representative skeleton or full implementation here
```

### Modified: `path/to/existing_file.py`

<!-- Describe what changes and why; include before/after snippet if helpful. -->

## Tests

<!-- Separate new test files from extensions to existing files. -->

Add `tests/test_<module>.py`:

- `test_basic_case()` — …
- `test_edge_case()` — …

Extend `tests/test_<existing>.py`:

- `test_regression_case()` — …

## Verification

<!-- How to confirm the change works beyond automated tests.
     Include test commands to run during development and any manual checks.
     Remove this section for pure logic changes where tests suffice. -->

```bash
venv/bin/python -m pytest tests/test_<module>.py tests/test_<related>.py -v
```

## Pitfalls

<!-- Known gotchas, ordering constraints, import quirks, or traps discovered during
     planning. Remove this section if there are none. -->

## Acceptance criteria

<!-- Concrete checklist for "done". Every item should be objectively verifiable. -->

- [ ] All existing tests still pass (`venv/bin/python -m pytest`)
- [ ] New tests pass
- [ ] …

## Scope boundaries

- **In scope**: …
- **Out of scope**: …
- **Do not** modify …

# Claude Code Guidelines

## Running commands

This project uses a local virtualenv. **Always use `venv/bin/python`** — never `python`, `python3`, or `uv run`.

```bash
# Run tests
venv/bin/python -m pytest

# Run CLI
venv/bin/python bnr.py <command>
```

## Recording TODOs

TODOs are always written with `[ ]` syntax so it is clear what is done.

## Standards

Project-wide conventions live in `STANDARDS.md`. Do not duplicate those rules elsewhere; link to them instead.

## Test-driven development

Use red/green TDD. Write failing tests first, then make them pass. Do not write implementation code before its test exists. When a task specifies test cases, create the test file and verify the tests fail before touching production code.

## One pipeline principle

Benchmark and production must use the same detection/embedding/clustering code. Do not create parallel implementations for the same operation. If the benchmark needs richer output (traces, diagnostics), extend the shared code with optional outputs — do not fork it into a separate function.

## Rescanning Single Photos

To rescan a single photo after making code changes, use:

```bash
# By photo hash (8 hex characters):
venv/bin/python bnr.py scan --rescan 6dde41fd

# By 1-based index (photo number in database order):
venv/bin/python bnr.py scan --rescan 47
```

This is useful for testing detection changes on specific photos without rescanning the entire album.

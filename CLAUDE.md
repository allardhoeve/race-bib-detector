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

## Rescanning Single Photos

To rescan a single photo after making code changes, use:

```bash
# By photo hash (8 hex characters):
venv/bin/python bnr.py scan --rescan 6dde41fd

# By 1-based index (photo number in database order):
venv/bin/python bnr.py scan --rescan 47
```

This is useful for testing detection changes on specific photos without rescanning the entire album.

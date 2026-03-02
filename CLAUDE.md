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

## Task names

Related tasks are always recorded in todo/tasks/ with name syntax: task-xxx-theme-name-xxxxx.

## Committing

If you commit at the user's request, or if you deem this necessary, always record if the commit is part of a task. This should be in the title ("task-051: something something summary").

If the commit is unrelated to a single task, try to commit changes grouped by task.

```
Succinct summary of changes

Task 051:
- This changed
- That changed

Task 052:
- Something changed
- Something else changes

Other things:
- More things
- Things happen
```


## Standards

Project-wide conventions live in `STANDARDS.md`. Do not duplicate those rules elsewhere; link to them instead.

## Test-driven development

Use strict red/green TDD — one test at a time. Write one test, run it and confirm it fails (red), then write the minimal code to make it pass (green). Repeat. Do not batch-write multiple tests before implementing. If a new test passes immediately, it is redundant — delete it or question the code. This cycle ensures every line of production code is justified by a specific failure and prevents over-engineering.

## One pipeline principle

Benchmark and production must use the same detection/embedding/clustering code. Do not create parallel implementations for the same operation. If the benchmark needs richer output (traces, diagnostics), extend the shared code with optional outputs — do not fork it into a separate function.

## Album pipeline

```bash
# Full pipeline: scan all photos in a directory + cluster faces
venv/bin/python bnr.py album ingest /path/to/photos

# Rescan a single photo + re-cluster its album
venv/bin/python bnr.py album rescan 6dde41fd   # by photo hash (8 hex chars)
venv/bin/python bnr.py album rescan 47          # by 1-based index
```

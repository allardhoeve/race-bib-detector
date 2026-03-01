# Task 058: Remove duplicate CLI parser and shim functions

Independent of other open tasks. No prerequisites.

## Goal

Eliminate the duplicate `argparse` parser in `benchmarking/cli/__init__.py`, remove the shim functions in `bnr.py`, and add the two missing subcommands (`tune`, `inspect`) to `bnr.py`. After this task, `bnr.py` is the single source of truth for CLI argument parsing.

## Problem

There are two independent argparse trees that define the same benchmark subcommands:

| Entrypoint | Invocation | Parser location |
|---|---|---|
| `bnr.py` | `bnr benchmark run --full` | `bnr.py:114` `build_parser()` |
| `benchmarking/cli/__init__.py` | `python -m benchmarking.cli benchmark` | `benchmarking/cli/__init__.py:36` `build_parser()` |

### Specific duplication

`bnr.py` has 11 shim functions (:33–111) that do nothing but forward to the real command functions:

```python
def cmd_benchmark_run(args):
    from benchmarking.cli import cmd_benchmark
    bench_args = argparse.Namespace(split="full" if args.full else "iteration", ...)
    return cmd_benchmark(bench_args)

def cmd_benchmark_list(args):
    from benchmarking.cli import cmd_benchmark_list
    return cmd_benchmark_list(args)  # literally just re-imports and calls
```

The `cmd_benchmark_run` shim is the worst — it manually constructs an `argparse.Namespace` to bridge `--full` (bnr.py) to `--split iteration|full` (cli module), which is fragile.

### Missing from bnr.py

Two subcommands exist in `benchmarking/cli/__init__.py` but not in `bnr.py`:

1. **`tune`** — `benchmarking/cli/commands/tune.py:9` `cmd_tune(args)` — sweep face detection parameters
   - Args: `--config YAML`, `--params KEY=v1,v2 ...`, `-s/--split`, `--metric`, `-q/--quiet`

2. **`inspect`** — `benchmarking/cli/commands/benchmark.py:134` `cmd_benchmark_inspect(args)` — print URL to inspect a run
   - Args: `run_id` (positional, optional, defaults to latest)

### Commands that should NOT be added to bnr.py

Three commands in the old CLI are low-value standalone commands that exist only there:
- `unlabeled` — `cmd_unlabeled(args)` — list unlabeled photos (use the UI instead)
- `show` — `cmd_show(args)` — show photo details by hash
- `label` — `cmd_label(args)` — add/update a label from CLI

These are development helpers, not user-facing commands. Drop them from the re-export module.

## Context — command function signatures

All command functions live in `benchmarking/cli/commands/` and take `argparse.Namespace`:

### `benchmarking/cli/commands/benchmark.py`

```python
cmd_benchmark(args)          # args.split, args.quiet, args.note, args.frozen_set, args.update_baseline
cmd_benchmark_inspect(args)  # args.run_id (optional, defaults to latest)
cmd_benchmark_list(args)     # no specific args
cmd_benchmark_delete(args)   # args.run_ids, args.force
cmd_benchmark_clean(args)    # args.keep_latest, args.keep_baseline, args.older_than, args.force
cmd_set_baseline(args)       # args.run_id, args.force
cmd_freeze(args)             # args.name, args.description, args.all, args.include_incomplete
cmd_frozen_list(args)        # no specific args
cmd_update_baseline = cmd_set_baseline  # alias at :470
```

### `benchmarking/cli/commands/photos.py`

```python
cmd_scan(args)     # no specific args
cmd_stats(args)    # no specific args
cmd_prepare(args)  # args.source, args.refresh, args.reset_labels
cmd_ui(args)       # no specific args
```

### `benchmarking/cli/commands/tune.py`

```python
cmd_tune(args)     # args.config, args.params, args.split, args.metric, args.quiet
```

## Changes

### 1. Modified: `bnr.py`

#### Remove all shim functions

Delete lines 33–111 (11 functions: `cmd_serve`, `cmd_benchmark_run`, `cmd_benchmark_ui`, `cmd_benchmark_list`, `cmd_benchmark_delete`, `cmd_benchmark_clean`, `cmd_benchmark_baseline`, `cmd_benchmark_prepare`, `cmd_benchmark_scan`, `cmd_benchmark_stats`, `cmd_benchmark_freeze`, `cmd_benchmark_frozen_list`).

Replace with direct imports at the top of `build_parser()` or use `set_defaults(_cmd=...)` pointing to lazy-imported command functions.

#### Fix `benchmark run` parser

Change `--full` flag to `-s/--split` with choices to match what `cmd_benchmark` expects:

```python
bench_run.add_argument(
    "-s", "--split", choices=["iteration", "full"],
    default="iteration",
    help="Which split to run (default: iteration)",
)
bench_run.add_argument(
    "--update-baseline", action="store_true", default=False,
    help="Update baseline if metrics improved",
)
bench_run.set_defaults(_cmd=cmd_benchmark)  # direct, no shim
```

#### Add `benchmark tune` subcommand

```python
bench_tune = benchmark_subparsers.add_parser("tune", help="Sweep face detection parameters")
bench_tune.add_argument("--config", metavar="YAML", help="Path to tune config YAML")
bench_tune.add_argument("--params", nargs="+", metavar="KEY=v1,v2", help="Inline param grid")
bench_tune.add_argument("-s", "--split", choices=["iteration", "full"], default=None)
bench_tune.add_argument("--metric", choices=["face_f1", "face_recall", "face_precision"], default=None)
bench_tune.add_argument("-q", "--quiet", action="store_true")
bench_tune.set_defaults(_cmd=cmd_tune)
```

#### Add `benchmark inspect` subcommand

```python
bench_inspect = benchmark_subparsers.add_parser("inspect", help="Show URL to inspect a benchmark run")
bench_inspect.add_argument("run_id", nargs="?", default=None, help="Run ID (defaults to latest)")
bench_inspect.set_defaults(_cmd=cmd_benchmark_inspect)
```

#### Keep `cmd_serve` as a local function

`cmd_serve` imports from `web` which is not in `benchmarking/cli/commands/`. Keep it as a small local function (it's only 3 lines).

### 2. Modified: `benchmarking/cli/__init__.py`

Strip to re-exports only:

```python
"""Benchmark CLI command functions (re-exported for convenience)."""
from benchmarking.cli.commands.benchmark import (
    cmd_benchmark,
    cmd_benchmark_inspect,
    cmd_benchmark_list,
    cmd_benchmark_clean,
    cmd_benchmark_delete,
    cmd_set_baseline,
    cmd_update_baseline,
    cmd_freeze,
    cmd_frozen_list,
)
from benchmarking.cli.commands.photos import cmd_scan, cmd_stats, cmd_prepare, cmd_ui
from benchmarking.cli.commands.tune import cmd_tune
```

Remove: `build_parser()`, `main()`, `import argparse`, `import sys`, `from pathlib import Path`, sys.path manipulation, `add_logging_args`, and the five low-value commands (`cmd_unlabeled`, `cmd_show`, `cmd_label`).

### 3. Delete: `benchmarking/cli/__main__.py`

No longer needed — `python -m benchmarking.cli` is not a supported entrypoint.

### 4. Tests

Add to an existing or new test file:

- `test_bnr_benchmark_run_help` — `bnr benchmark run --help` exits 0, output contains `--split`
- `test_bnr_benchmark_tune_help` — `bnr benchmark tune --help` exits 0
- `test_bnr_benchmark_inspect_help` — `bnr benchmark inspect --help` exits 0
- `test_bnr_cli_reexports` — `from benchmarking.cli import cmd_benchmark, cmd_tune, cmd_benchmark_inspect` works

Verification:

```bash
venv/bin/python bnr.py benchmark --help
venv/bin/python bnr.py benchmark run --help
venv/bin/python bnr.py benchmark tune --help
venv/bin/python bnr.py benchmark inspect --help
venv/bin/python -m pytest -v
```

## Scope boundaries

- **In scope**: parser consolidation, shim removal, add tune + inspect, delete `__main__.py`
- **Out of scope**: changing command function internals, web UI, template changes
- **Do not** change any runtime behaviour — same output, same exit codes
- **Do not** remove `cmd_serve` — it's the only function that's genuinely local to `bnr.py`

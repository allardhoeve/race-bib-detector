# Task 048: Consolidate CLI entrypoints — single parser, no duplication

Independent of other open tasks. No prerequisites.

## Goal

Make `bnr.py` the single source of truth for all CLI argument parsing. Eliminate the duplicated parser in `benchmarking/cli/__init__.py` so that adding a flag like `--set` only requires touching one file.

## Problem

There are two independent argparse trees that define the same benchmark subcommands:

| Entrypoint | Invocation | Structure |
|---|---|---|
| `bnr.py` | `bnr benchmark run --full` | Nested: `benchmark` → `run`, `list`, `clean`, … |
| `benchmarking/cli/__init__.py` | `python -m benchmarking.cli benchmark -s full` | Flat: `benchmark`, `benchmark-list`, `benchmark-clean`, … |

Every new flag must be added in both places. `bnr.py` uses shim functions (e.g. `cmd_benchmark_run`) that manually construct `argparse.Namespace` objects to bridge the two parser shapes, which is fragile and easy to forget.

### Specific inconsistencies today

- `bnr.py` uses `--full` flag; `benchmarking/cli` uses `-s/--split choices=[iteration,full]`
- `bnr.py` calls it `baseline`; `benchmarking/cli` calls it `set-baseline`
- `benchmarking/cli` has `tune`, `unlabeled`, `show`, `label`, `benchmark-inspect` — none exist in `bnr.py`
- `benchmarking/cli` has `benchmark` (flat, runs detection); `bnr.py` has `benchmark` as a group with subcommands

## Design decisions (resolved)

| Question | Decision |
|---|---|
| Which entrypoint survives? | `bnr.py` — it's what users run |
| What happens to `benchmarking/cli/__init__.py`? | Becomes a thin re-export of command functions only (no `build_parser`, no `main`). `benchmarking/cli/__main__.py` removed. |
| Where do command functions live? | Stay in `benchmarking/cli/commands/*.py` — unchanged. They take `argparse.Namespace` and return `int`. |
| Missing commands in bnr.py? | Add: `tune`, `inspect`. Drop from old CLI: `unlabeled`, `show`, `label` (low-value standalone commands, keep if trivial). |
| Namespace shim pattern? | Eliminated. `bnr.py` defines parsers that produce `Namespace` objects matching what command functions expect. No adapter layer. |

## Changes

### 1. `bnr.py` — single parser, direct dispatch

Add missing subcommands under `benchmark`:
- `tune` — sweep face detection parameters (copy parser args from old `benchmarking/cli`)
- `inspect` — show URL to inspect a run

Remove all shim functions (`cmd_benchmark_run`, `cmd_benchmark_ui`, etc.). Instead, use `set_defaults(_cmd=...)` pointing directly at the command functions from `benchmarking/cli/commands/*.py`.

Align argument names so the `Namespace` matches what command functions expect:
- `benchmark run`: use `-s/--split` with `choices=[iteration, full]` and `default=iteration` (drop `--full` flag)
- `benchmark baseline`: rename from `baseline` to match `cmd_set_baseline` expectation, or rename the function — pick one, be consistent

### 2. `benchmarking/cli/__init__.py` — strip parser, keep re-exports

Remove `build_parser()` and `main()`. Keep the imports so existing code that does `from benchmarking.cli import cmd_benchmark` still works:

```python
"""Benchmark CLI command functions (re-exported for convenience)."""
from benchmarking.cli.commands.benchmark import (
    cmd_benchmark,
    cmd_benchmark_inspect,
    cmd_benchmark_list,
    cmd_benchmark_clean,
    cmd_set_baseline,
    cmd_freeze,
    cmd_frozen_list,
)
from benchmarking.cli.commands.photos import cmd_scan, cmd_stats, cmd_prepare, cmd_ui
from benchmarking.cli.commands.tune import cmd_tune
```

### 3. `benchmarking/cli/__main__.py` — delete

No longer needed since `python -m benchmarking.cli` is not a supported entrypoint.

### 4. `benchmarking/cli/commands/benchmark.py` — minor cleanup

`cmd_benchmark()` currently reads `args.split` directly. Confirm it works with the new parser's Namespace (it should — just ensure `args.split` is set, not `args.full`).

### 5. Tests

- Verify `bnr benchmark run --help` shows all flags
- Verify `bnr benchmark tune --help` works
- Verify `bnr benchmark inspect --help` works
- Verify existing tests that import from `benchmarking.cli` still pass (re-exports intact)

## Scope boundaries

- **In scope**: parser consolidation, shim removal, adding missing subcommands to `bnr.py`
- **Out of scope**: changing command function internals, web UI, template changes
- **Do not** change any runtime behaviour — same flags, same output, same exit codes

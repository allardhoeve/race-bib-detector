# Task 017: Split cli.py into command-group modules

Larger refactor. Independent of all other pending tasks.

## Goal

`benchmarking/cli.py` is 779 lines containing 12 command functions, `build_parser()`,
and `main()`. Split into a package so individual command groups can be read and edited
without scrolling through the whole file.

## Current commands (by line)

| Function | Line | Group |
|---|---|---|
| `cmd_scan` | 37 | photos |
| `cmd_stats` | 66 | photos |
| `cmd_unlabeled` | 126 | photos |
| `cmd_show` | 156 | photos |
| `cmd_label` | 198 | photos |
| `cmd_prepare` | 277 | photos |
| `cmd_ui` | 320 | photos |
| `cmd_benchmark` | 326 | benchmark |
| `cmd_benchmark_inspect` | 434 | benchmark |
| `cmd_benchmark_list` | 458 | benchmark |
| `cmd_benchmark_clean` | 489 | benchmark |
| `cmd_set_baseline` | 557 | benchmark |
| `build_parser` | 623 | — |
| `main` | 751 | — |

## Proposed structure

```
benchmarking/
  cli.py            ← keep as entry point (thin shim that delegates to cli/)
  cli/
    __init__.py     ← build_parser(), main() — ~50 lines
    commands/
      photos.py     ← cmd_scan, cmd_stats, cmd_unlabeled, cmd_show, cmd_label,
                        cmd_prepare, cmd_ui  (~290 lines)
      benchmark.py  ← cmd_benchmark, cmd_benchmark_inspect, cmd_benchmark_list,
                        cmd_benchmark_clean, cmd_set_baseline  (~430 lines)
```

`benchmarking/cli.py` becomes:
```python
"""CLI entry point — delegates to benchmarking.cli package."""
from benchmarking.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
```

## Migration steps

1. Create `benchmarking/cli/` directory.
2. Move `cmd_scan` through `cmd_ui` (lines 37–325) to `commands/photos.py`.
   Copy needed imports; these commands use: `ground_truth`, `photo_index`,
   `label_utils`, `runner`, `config`, `logging_utils`, `web_app`.
3. Move `cmd_benchmark` through `cmd_set_baseline` (lines 326–622) to
   `commands/benchmark.py`.
   These commands use: `runner`, `ground_truth`, `photo_index`, `scoring`.
4. Move `build_parser()` and `main()` (lines 623–779) to `cli/__init__.py`.
   Update subparser `set_defaults(func=...)` to reference the moved functions,
   importing from `commands.photos` and `commands.benchmark`.
5. Replace `benchmarking/cli.py` with the thin shim above.

## Shared utilities

`get_photos_dir()` (line 33) is used by both groups. Options:
- Duplicate it (it's one line) — simplest.
- Move to a `commands/_common.py` file shared by both.

## Test strategy

Follow [docs/REFACTORING.md](../../docs/REFACTORING.md). Note: test imports that
reference `benchmarking.cli` directly will need their import paths updated after the
module is split into a package — see the [Patch paths](../../docs/REFACTORING.md#patch-paths)
section.

- Run `pytest tests/` after each step.
- Verify `python -m benchmarking.cli --help` still works.
- Spot-check: `python -m benchmarking.cli scan`, `python -m benchmarking.cli stats`.

## Scope boundaries

- **In scope**: moving functions into the package structure; updating imports.
  No logic changes.
- **Out of scope**: changing CLI argument names, command behaviour, or output format.
- **Note**: `benchmarking/cli.py` currently used as `__main__` entry — confirm
  `pyproject.toml` / `setup.cfg` entry point references before changing the path.

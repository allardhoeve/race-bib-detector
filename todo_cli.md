# CLI Refactor Plan

## Goals
- [ ] Keep `bnr.py` as a router only (no heavy work or scan logic).
- [ ] Move scan parsing/control flow into `cli/scan.py`.
- [ ] Move scan execution into reusable modules under `scan/` so web/workers can call it.
- [ ] Align benchmarking CLI with the same pattern (router -> cli/* -> reusable service).

## Notes
- CLI modules should only parse args and dispatch to reusable services.
- Reusable services should avoid `print()` and return structured data.

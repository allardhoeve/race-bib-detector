# Testing Guidelines

These guidelines capture how we approach tests in this repo. Project-wide conventions live in
`STANDARDS.md`; this document should not duplicate those rules.

## Goals

- Prefer tests that protect behavior, invariants, and integration boundaries.
- Keep tests resilient to refactors of internal structure.
- Avoid tests that only restate Python/dataclass mechanics.

## Keep

- Validation rules and error handling.
- Computed properties and non-trivial transformations.
- Boundary contracts: file formats, schema migrations, and API defaults.
- Cross-module behavior (e.g., pipeline flows, DB effects, CLI behavior).

## Trim Or Remove

- Dataclass/accessor tests that only check constructor args or default values.
- Repeated round-trip tests for every class when one module-level snapshot is enough.
- Pure “shape” tests that confirm a field exists without behavior attached.

## Serialization Strategy

- One focused round-trip test per module is usually sufficient.
- Prefer a single golden dict to lock down format stability.
- Keep defaults/compat tests only where backward compatibility is required.

## Review Checklist

- Does this test fail if real behavior regresses?
- Could we remove this test and still catch the same bug elsewhere?
- Is this test asserting a language feature instead of our code?

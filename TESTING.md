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

## Refactoring Discipline

Guidelines for pure refactors — changes that reorganise code without altering behaviour.

**Core principle:** Tests are the behavioral contract. If `pytest` passes before and after with no test changes, the refactor is verified correct by definition. A refactor that requires changing what a test *asserts* has changed behaviour — stop, investigate, and decide whether that was intended.

**Before you start:**
1. Establish a green baseline — run `pytest` and confirm everything passes. Fix broken tests first.
2. Understand the call graph — find all callers before renaming or moving anything.

**What to change vs. leave alone:**

| Situation | Action |
|---|---|
| Extracting a private helper called only by the split function | Leave tests unchanged |
| Renaming an internal variable | Leave tests unchanged |
| Moving a function to a different module | Update import paths in tests (patch paths) |
| Changing a function's signature or return type | Update all callers — but reconsider scope |
| Spotted a bug while refactoring | Do not fix it here — file a new task |

**Patch paths:** `unittest.mock.patch` targets the name *as imported at the call site*. When splitting modules, update the patch string — that is mechanical, not a behaviour change.

**Commit discipline:** One logical change per commit. Run `pytest` after each commit. Keep the diff minimal.

**Scope discipline:** Do not add docstrings, type annotations, comments, reformatting, or error handling to code outside your change. The "while I'm here" instinct is the primary source of refactoring regressions.

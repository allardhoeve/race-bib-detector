# Refactoring Guidelines

Guidelines for pure refactors — changes that reorganise code without altering behaviour.

---

## Core principle

> Tests are the behavioral contract. If `pytest` passes before and after with no test
> changes, the refactor is verified correct by definition.

A refactor that requires changing what a test *asserts* has changed behaviour.
Stop, investigate, and decide whether the behaviour change was intended.

---

## Before you start

1. **Establish a green baseline.** Run `pytest` and confirm everything passes.
   If tests are already broken, fix them first — otherwise you can't tell whether
   your refactor caused a regression.
2. **Understand the call graph.** Use `grep -rn 'function_name'` to find all callers
   before renaming or moving anything. Missing a caller means a silent break.

---

## What to change vs. what to leave alone

| Situation | Action |
|---|---|
| Extracting a private helper called only by the function you split | Leave tests unchanged |
| Renaming an internal variable or intermediate result | Leave tests unchanged |
| Moving a function to a different module | Update import paths in tests — see [Patch paths](#patch-paths) |
| Changing a function's signature or return type | Update all callers including tests — but reconsider: this may be out of scope for a pure refactor |
| Spotted a bug or improvement while refactoring | **Do not fix it here.** File a new task. |

---

## Patch paths

`unittest.mock.patch` targets the name *as imported at the call site*, not where it is
defined. This matters when splitting modules.

**Example:** a test patches `routes_face._embedding_index_cache`. If that cache is
moved to a new helper module `face_service`, the patch path becomes
`face_service._embedding_index_cache`. Updating the path is a mechanical necessity —
it is not a behaviour change.

**Rule:** updating a `patch(...)` string because the target moved = acceptable.
Updating what a test *asserts* because the refactor changed a result = not acceptable.

---

## Commit discipline

- Make **one logical change per commit** — e.g. "extract `_run_detection_loop`", not
  "refactor runner + fix imports + rename variable".
- Run `pytest` after each commit, not just at the end.
- Keep the diff minimal. Reviewers (and future-you) should be able to read the diff
  and immediately see that no logic changed.

---

## Scope discipline

A refactor task has a defined scope. If you notice something adjacent that should be
improved, **do not touch it**. File a new task instead. Mixing concerns in a refactor
makes diffs harder to review and increases the chance of unintended side-effects.

The "while I'm here" instinct is the primary source of refactoring regressions.

---

## Things to leave alone entirely

Even if they look wrong or inconsistent:

- **Do not** add docstrings, type annotations, or comments to code you did not
  restructure.
- **Do not** reformat code outside the lines you changed.
- **Do not** rename things not in scope — even obvious misspellings.
- **Do not** add error handling or input validation.

If any of these genuinely need doing, they deserve their own commit with a clear message.

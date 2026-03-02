# Task 093: Cross-photo refinement loop — `pipeline/refine.py`

Part of the tuning series (085-094). Framework for iterative pipeline improvement.

**Depends on:** task-091 (pipeline/cluster.py), task-095 (trace-based autolink)

**BLOCKED:** The bib consistency check needs to know which face traces are linked to which bib traces. Currently autolink operates on boxes (`BibBox`, `FaceBox`), and there is no explicit bridge between the box world and the trace world. Task-095 must resolve this first — either by moving autolink to traces, or by adding an explicit trace↔box mapping.

## Goal

Create `pipeline/refine.py` with a `refine()` function that iterates: cluster → check → correct → re-cluster. Both production and benchmarking call the same function. This task builds the framework and one proof-of-concept check.

## Background

The pipeline has two natural phases after single-photo detection:
- **Phase 2**: Clustering (task-091)
- **Phase 3**: Refinement — cross-photo checks that feed back into traces

A face rejected at confidence 0.28 might clearly match 5 other faces in a cluster. A bib reading "423" might be an OCR error when the cluster reads "428" everywhere else. These corrections are only visible in aggregate.

```
Phase 2: cluster()
    │
    ▼
Phase 3: refine()
    ├── check: cluster quality
    ├── check: orphan face rescue
    ├── check: bib consistency
    └── corrections → re-cluster if changed
    │
    ▼ loop until stable or max iterations
```

## Design

### Loop structure

```python
def refine(
    face_traces: list[FaceCandidateTrace],
    bib_traces: list[BibCandidateTrace] | None = None,
    checks: list[RefinementCheck] | None = None,
    max_iterations: int = 3,
) -> RefinementResult:
    applied_keys: set[str] = set()
    iterations: list[IterationLog] = []

    for iteration in range(max_iterations):
        cluster(face_traces)
        corrections = []
        for check in checks:
            corrections.extend(check.run(face_traces, bib_traces))

        # Deduplicate: skip already-applied corrections
        novel = [c for c in corrections if c.key not in applied_keys]
        if not novel:
            break

        for c in novel:
            c.apply()
            applied_keys.add(c.key)

        iterations.append(IterationLog(...))

    return RefinementResult(iterations=iterations)
```

### Check interface

```python
class RefinementCheck(Protocol):
    def run(
        self,
        face_traces: list[FaceCandidateTrace],
        bib_traces: list[BibCandidateTrace] | None,
    ) -> list[Correction]: ...

@dataclass
class Correction:
    key: str                 # unique ID, e.g. "bib_consistency:hash:idx"
    correction_type: str     # "rescue_face", "revise_bib", "split_cluster"
    evidence: str            # human-readable explanation
    confidence: float        # 0-1
    apply: Callable          # function that mutates traces
```

### Convergence guarantees

1. **No corrections** → stop
2. **Max iterations** → stop unconditionally
3. **Monotonic progress** → corrections only add information (rescue, revise), never undo. Deduplication by key prevents oscillation.

### Proof-of-concept check: bib consistency

For each cluster, collect bib numbers from linked traces. If majority agrees and outliers exist, flag the outlier:

```python
class BibConsistencyCheck:
    def run(self, face_traces, bib_traces):
        # Group bib numbers by cluster_id
        # Find clusters with a clear majority and outliers
        # Return Correction for each outlier
```

This is pure set logic — no re-running detection. The correction can:
- Check if the majority number exists as a sub-threshold OCR result on the outlier trace
- Flag for human review
- Adopt majority reading with low confidence

### Future checks (not in this task)

- **Orphan face rescue**: rejected face close to a cluster centroid → re-embed and add
- **Cluster quality**: high intra-cluster distance → split candidate
- **Low-confidence bib rescan**: cluster consensus disagrees with low-confidence reading → rescan snippet with tighter crop

### Diagnostics

Each iteration records: which checks ran, corrections proposed/applied, before/after metrics delta.

## Context

- `pipeline/cluster.py` — `cluster()` function (task-091)
- `pipeline/types.py` — `BibCandidateTrace`, `FaceCandidateTrace`
- `pipeline/single_photo.py` — `run_single_photo()`

## Changes

### New: `pipeline/refine.py`

Loop structure, `RefinementCheck` protocol, `Correction` model, `RefinementResult`, `IterationLog`.

### New: `pipeline/checks/bib_consistency.py` (or inline in refine.py)

Proof-of-concept bib consistency check.

### Modified: `benchmarking/runner.py`

After clustering, optionally run refinement:
```python
from pipeline.refine import refine
all_traces = collect_traces(photo_results)
refine(all_traces.face, all_traces.bib)
```

### Modified: `pipeline/__init__.py`

Add `refine` to re-exports.

## Tests

`tests/test_pipeline_refine.py`:
- `test_empty_corrections_stops_immediately` — no checks → one iteration, done
- `test_max_iterations_caps_loop` — corrections every iteration → stops at max
- `test_duplicate_correction_skipped` — same key not applied twice
- `test_bib_consistency_finds_outlier` — cluster [428, 428, 423, 428] → correction for 423
- `test_bib_consistency_no_outlier` — uniform cluster → no correction
- `test_refinement_result_logs_iterations` — iteration count and corrections recorded

## Acceptance criteria

- [ ] `pipeline/refine.py` exists with `refine()` function
- [ ] `RefinementCheck` protocol defined
- [ ] `Correction` model with key-based deduplication
- [ ] Loop terminates on stability or max iterations
- [ ] Bib consistency check implemented as proof of concept
- [ ] Per-iteration diagnostics recorded
- [ ] TDD tests pass
- [ ] All existing tests pass

## Scope boundaries

- **In scope**: framework, convergence, bib consistency check, diagnostics
- **Out of scope**: orphan rescue, cluster splitting, low-confidence rescan (future checks)
- **This is framework + one check** — additional checks are separate tasks

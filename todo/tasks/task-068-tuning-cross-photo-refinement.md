# Task 068: Cross-photo refinement loop framework

Part of the tuning series. Architectural framework for iterative pipeline improvement.

**Depends on:** task-065 (bib trace), task-067 (face trace), and prerequisites not yet tasked: embedding stored on face trace, clustering with diagnostics.

## Goal

Establish a loop structure where cross-photo analysis (clustering, consistency checks) feeds back into single-photo results, rescuing borderline rejections and correcting errors that are only visible in aggregate.

## Background

The benchmark pipeline has two natural phases:

**Single-photo pipeline** (per photo, independent, parallelizable):
- Bib detection: candidates → validation → OCR → accept/reject
- Face detection: candidates → confidence/NMS → accept/reject
- Face embedding: crop accepted faces → compute embedding
- Autolink: spatial bib ↔ face matching

**Cross-photo analysis** (needs all photos):
- Face clustering: all embeddings → distance matrix → identity groups
- Bib-identity consistency: check bib numbers within each cluster

Today the pipeline is one-shot: single-photo → cross-photo → done. But cross-photo analysis produces signal that could improve single-photo results. A face rejected at confidence 0.28 might be clearly the same person as 5 other faces in a cluster. A bib reading "423" might be an OCR error when the cluster's other photos all read "428".

The refinement loop uses cross-photo context to challenge borderline single-photo decisions:

```
1. Single-photo pass
       │
       ▼
2. Cross-photo analysis (clustering)
       │
       ▼
3. Refinement checks
   ├── 3a. Cluster quality — do the clusters look right?
   ├── 3b. Orphan rescue — can unmatched faces join existing clusters?
   ├── 3c. Bib consistency — are numbers consistent within clusters?
   └── 3d. Feed corrections back → re-cluster if anything changed
       │
       ▼
   If changes: go to step 2
   If stable: done
```

## Design

### Loop structure

```python
def run_pipeline(photos, config) -> PipelineResult:
    # Phase 1: single-photo pass (parallelizable)
    photo_results = [run_single_photo(photo, config) for photo in photos]

    # Phase 2+3: cross-photo analysis with refinement loop
    max_iterations = config.max_refinement_iterations  # default: 3
    for iteration in range(max_iterations):
        # Phase 2: cluster
        cluster_result = cluster_faces(photo_results)

        # Phase 3: run all refinement checks
        corrections = []
        for check in refinement_checks:
            corrections.extend(check.run(photo_results, cluster_result))

        if not corrections:
            break  # stable — no more improvements

        # Apply corrections and loop
        apply_corrections(photo_results, corrections)

    return PipelineResult(photo_results, cluster_result)
```

### Refinement check interface

```python
class RefinementCheck(Protocol):
    """A cross-photo check that may propose corrections to single-photo results."""

    def run(
        self,
        photo_results: list[PhotoResult],
        cluster_result: ClusterResult,
    ) -> list[Correction]:
        ...

@dataclass
class Correction:
    """A proposed change to a single-photo result, motivated by cross-photo evidence."""
    photo_hash: str
    correction_type: str          # "rescue_face", "revise_bib", "split_cluster", etc.
    evidence: str                 # human-readable explanation
    confidence: float             # how sure we are (0-1)
    apply: Callable               # function that applies the correction
```

### Planned refinement checks

#### 3a. Cluster quality check

Quick pass along clusters. Flag clusters with low cohesion (high intra-cluster distance) or suspiciously mixed visual features. These are candidates for splitting.

- **Input**: cluster assignments + pairwise distances
- **Output**: `split_cluster` corrections for low-quality clusters

#### 3b. Orphan face rescue

For each face not assigned to a cluster (or rejected during detection), check if it's close to an existing cluster centroid. If within a relaxed threshold, rescue it.

- **Input**: rejected face traces (from `face_trace` where `accepted=False`), cluster centroids
- **Output**: `rescue_face` corrections that re-embed the rejected region and add to cluster

This is the most impactful check — it directly improves recall by using cluster context to lower the effective detection threshold for faces that "look like" known people.

#### 3c. Bib consistency check

For each cluster, collect all bib numbers from linked photos. If there's a majority number and outliers, flag the outliers for OCR re-examination.

- **Input**: cluster assignments + pred_bib_boxes + pred_links
- **Output**: `revise_bib` corrections for inconsistent readings

This is pure set logic — no re-running detection. If cluster 7 has bibs [428, 428, 423, 428, 428], the "423" is likely an OCR error. The correction can either:
- Re-score the bib trace for that photo (was there a "428" candidate below threshold?)
- Flag it for human review
- Automatically adopt the majority reading (with low confidence flag)

### Convergence

The loop terminates when:
- No refinement check produces corrections (stable), or
- Maximum iterations reached (safety bound, default 3)

In practice, most corrections happen in iteration 1. Iteration 2 catches second-order effects (e.g., a rescued face changes a cluster composition, which changes a bib consistency verdict). Iteration 3 should almost always be a no-op.

### Diagnostics

Each iteration records:
- Which checks ran
- What corrections were proposed
- What was applied
- Before/after metrics delta

This feeds into the benchmark report so you can see exactly what the refinement loop contributed.

## Prerequisites (not yet tasked)

This framework depends on infrastructure that needs its own tasks:

1. **Embedding on face trace** — move face embedding from `_assign_face_clusters()` into the single-photo pipeline. Store embedding vector (or a hash/summary) on `FaceCandidateTrace`. This makes embeddings available without re-processing images.

2. **Clustering with diagnostics** — refactor `_assign_face_clusters()` into a pure function that takes embeddings and returns cluster assignments + per-face distances + cluster cohesion metrics. No image access needed.

3. **Image decode once** — share decoded image between bib and face detection in the single-photo pipeline, eliminating the current 3x decode.

## Scope boundaries

- **In scope**: loop structure, refinement check interface, correction model, iteration tracking
- **Out of scope**: implementing individual refinement strategies (those are separate tasks), modifying single-photo detection logic, production (non-benchmark) pipeline changes
- **This task is framework only** — it builds the scaffold that refinement checks plug into

## Acceptance criteria

- [ ] Loop structure runs cross-photo analysis and refinement checks iteratively
- [ ] `RefinementCheck` protocol defined with clear contract
- [ ] `Correction` model captures what/why/confidence for each proposed change
- [ ] Loop terminates on stability or max iterations
- [ ] Per-iteration diagnostics recorded
- [ ] At least one trivial check implemented as proof of concept (e.g., bib consistency)
- [ ] TDD tests for loop mechanics (convergence, max iterations, empty corrections)
- [ ] All existing tests pass

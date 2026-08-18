# PlanGraph

An ontology and entity-resolution layer for construction document sets, built on
**HydraDB**. Submission to Hack Hydra 2026, **Track 01 — Enterprise Context + Ontology**.

Dataset: **AEC-Bench** (Apache-2.0, nomic-ai) — documents are fetched from the
upstream `manifest.jsonl` and are **not** redistributed in this repository.

---

## Pre-registered hypothesis

**Written 2026-08-17, before any arm was run.** Recorded here so that a null
result is reportable rather than quietly dropped.

### Where we predict the graph wins

| Family | Tasks | Why |
|---|---|---|
| cross-reference-resolution | 51 | A callout pointing at a sheet that does not exist is a traversal terminating in absence. Native graph operation. |
| cross-reference-tracing | 24 | "Where is detail 5/A902 referenced from" is reverse-dependency closure. HydraDB ships reverse adjacency indexes for exactly this. |
| sheet-index-consistency | 14 | Set difference between what the index claims and what the set contains. |

### Where we predict the graph does NOT help

| Family | Tasks | Why |
|---|---|---|
| spec-drawing-sync | 16 | The bottleneck is *perception* — reading a dimension off a drawing — not traversal. A graph cannot fix blindness. We expect little or no gain here, and we will report that. |

### Falsification conditions

- If cross-reference-resolution does **not** improve over the published baseline,
  the core claim fails and we say so.
- If spec-drawing-sync **does** improve substantially, our model of *why* the
  graph helps is wrong, and the explanation in this README is wrong.

### Known measurement limits, stated up front

- **Abstention is graded on only 2 of 196 tasks.** It is reported as an
  ablation, never as a headline number.
- **cross-reference-tracing is capped at 0.416** by unsatisfiable grader checks
  (72 of 103 ref-checks require 2 matches from a 1-element keyword list). We
  report against that ceiling, and we do not modify graders.
- Scanned pages are out of scope; ingestion is text-layer only.

## Arms

1. **Control** — the benchmark's own published agent configuration, unmodified.
2. **PlanGraph** — same tasks, same documents, same model; retrieval via the
   HydraDB graph.
3. *(if time)* A vector-retrieval arm, as an additional comparison — not a
   substitute for arm 1.

## Attribution

- HydraDB — github.com/hydra-db/hydradb (AGPL-3.0)
- AEC-Bench — github.com/nomic-ai/aec-bench (Apache-2.0), arXiv:2603.29199
- PyMuPDF — text and geometry extraction

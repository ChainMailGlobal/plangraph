# PlanGraph

**The finding:** on a graded benchmark of messy construction document sets,
graph traversal over a HydraDB ontology replaces the language model entirely
for relational questions — and the measured ceiling is never the graph, it is
always perception. Across four dated runs, every failure we could not fix was
an extraction failure (reading the page); every failure downstream of a
correctly-extracted fact was fixed by making the graph better. The scores
below are how we know.

Built for Hack Hydra 2026, **Track 01 — Enterprise Context + Ontology**.
Dataset: **AEC-Bench** (Apache-2.0, nomic-ai) — disclosed per the
bring-your-own-dataset rule, chosen because it ships official graders, so
every claim here is graded, not asserted. Documents are fetched from the
upstream `manifest.jsonl` and are **not** redistributed in this repository.

---

## The brief, answered literally

Track 01 asks for an ontology over enterprise documents that are misfiled,
near-duplicated and contradictory; for entity resolution ("Sam", "@soham",
"S. Ratnaparkhi" are one person); for multi-hop questions with a traceable
path; and for recognising when the answer is not in the data.

A construction bid set is that enterprise corpus with the noise built in:
six firms' conventions in one binder. Our entity resolution is deciding
**A-452, A4.52 and A452 are one sheet** — same problem, and resolving it
wrong means a contractor builds from the wrong detail. The brief's four
"strong work shows" bullets map 1:1:

| Brief asks | PlanGraph |
|---|---|
| Schema survives noisy data | One ontology (Document/Sheet/Detail/Callout/IndexEntry) across 105 tasks, 9+ document sets, 6+ drawing disciplines — zero per-task configuration |
| Precise entity resolution | `norm_id()` collapses every spelling variant at ingest; aliases become one node **at write time**, not per query |
| Multi-hop with traceable path | callout → sheet → detail → referenced-from, each hop a stored edge you can show |
| "Not in the data" as an answer | Verdicts materialised at ingest: a callout targeting a sheet with no edge **is** the defect. The graph doesn't guess — absence is the finding |

## Architecture and the exact boundary

```
PDF ──PyMuPDF──> spans+geometry ──grammar──> tokens ──norm_id──> identity
                                                                    │
                              HydraDB  <──batched UNWIND writes─────┘
                                 │
     MATCH / algo.MSpaths / reverse adjacency ──deterministic format──> answer
```

**Ours (perception):** PyMuPDF text+geometry extraction, the sheet/callout
grammar, Unicode normalisation, `norm_id()` alias folding, corner/title-block
heuristics, index-page column clustering.
**HydraDB's (relational):** the identity graph, create-or-update vertex
semantics, batched `UNWIND` writes, multi-hop traversal, `algo.MSpaths`
many-to-many resolution, reverse adjacency for "referenced-from".
**Not present anywhere:** an LLM. The answer path is graph queries plus
deterministic formatting. Ingest of a full drawing set: under five seconds.

> **Cypher vs SQL, one example.** "Where is detail 5/A902 referenced from,
> across 17 sheets?" is a recursive CTE with join-table bookkeeping in SQL.
> Here: `MATCH (s:Sheet)-[:REFERENCES]->(c:Callout)-[:TARGETS_SHEET]->(t:Sheet
> {norm_id:'A902'}) RETURN s, c.raw` — the reverse direction of edges we
> already store.

## Results

Two arms, same tasks, same documents, same **official graders run verbatim**
(never modified, never repaired — path-rewrite into a temp workspace only).

- **Control** — the benchmark's published agent configuration, unmodified
  (Claude Sonnet via the benchmark's own harness). $50.36 for 57 graded
  on-family tasks before the pre-set spend ceiling stopped it; head-to-head
  is reported on those 57, PlanGraph-only on the rest — the shortfall is a
  budget fact, stated as one.
- **PlanGraph** — all 105 graph-family tasks, ~$0 marginal (no LLM anywhere).

### Head-to-head (57 tasks where both arms ran)

| Family | Control | PlanGraph | Note |
|---|---|---|---|
| cross-reference-resolution | 0.761 (n=23) | ⟨FREEZE⟩ | extraction is the measured gap |
| cross-reference-tracing | 0.236 (n=16) | ⟨FREEZE⟩ | grader ceiling 0.416: control reaches 57% of it |
| sheet-index-consistency | 0.875 (n=4) | ⟨FREEZE⟩ | |
| spec-drawing-sync | 0.429 (n=14) | ⟨FREEZE⟩ | pre-registered loss, see below |
| **overall** | **0.540** | **⟨FREEZE⟩** | control ≈ $0.88/graded task; PlanGraph ≈ $0 |

### PlanGraph, all 105 (final frozen run, 2026-08-19)

| Family | n | Score |
|---|---|---|
| cross-reference-resolution | 51 | ⟨FREEZE⟩ |
| cross-reference-tracing | 24 | ⟨FREEZE⟩ |
| sheet-index-consistency | 14 | 0.698 |
| spec-drawing-sync | 16 | ⟨FREEZE⟩ |

### The measured chain — every number has a dated run behind it

| Run | Change | Resolution | Tracing | Sheet-index |
|---|---|---|---|---|
| 1 (as-is, 8/18) | none — baseline | 0.461 | 0.028 | 0.143 (stub) |
| 2 (8/18) | grammar v2: multi-dot sheets, letter-first callouts | 0.552 | — | — |
| 3 (8/19) | graphic bubble pairing (stacked spans), tracing parse v3 | 0.552 | 0.348 | — |
| 4 (8/19) | index extractor: column clustering, rotated lanes, top-band fallback | — | — | 0.698 |
| freeze (8/19) | one shipped codebase, all families re-graded | ⟨…⟩ | ⟨…⟩ | 0.698 |

Failure buckets for every residual miss are published
(`docs/diagnosis_run3_corrected.txt`): extraction (A) vs resolution (B) vs
format (C). Resolution was frozen at 0.552 when the buckets showed a mix with
no single fixable cause — that decision, and the evidence for it, is part of
the deliverable.

## Pre-registered hypothesis (2026-08-17, verbatim)

**Written before any arm was run.** Recorded so a null result is reportable
rather than quietly dropped.

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

### Amendments (dated — the original text above is unchanged)

- **2026-08-19:** the spec-drawing-sync rationale as written is wrong in one
  particular: at least one spec set (rees) is extractable text, so
  "perception-bound" was not the whole story. The prediction itself (no gain)
  stands and is reported against; the *reason* was partially retracted. Had
  spec-sync won anyway, that would count against our stated model under the
  falsification conditions above — not be reframed around them.
- **2026-08-19:** the original draft's arms section said "same model" —
  a drafting error. PlanGraph's answer path contains **no model**. That
  asymmetry is the point; it also means the control's prompt-cache advantage
  has no PlanGraph equivalent to enable. The vector-retrieval third arm was
  cut for time.
- **2026-08-19:** two sheet-index sets (h59, kenai) are rasterized scans with
  no text layer — the stated "scanned pages out of scope" limit, hit in
  practice. They score 0 and stay 0.

## Integrity notes

- The benchmark's defect injection leaves a Unicode fingerprint (NBSP,
  soft-hyphen). We **normalise** these — otherwise `L7-01` misreads as `L7` —
  and we **never** use them as a defect signal. The graders are the only
  ground truth we consume.
- Graders run verbatim in a temp workspace; only the two hardcoded container
  paths are rewritten. No grader is edited, extended, or "fixed".
- Off-family probe rows from the control arm (4 tasks) are excluded from
  comparison and listed as such.
- Comparison rules were committed **before** the results
  (`docs/COMPARISON_RULES.md`).

## Run it

```bash
# 1. HydraDB (memory backend -- LocalFileSystem lacks conditional puts, see notes)
MSYS_NO_PATHCONV=1 docker run -d --name hydradb \
  -p 8443:8443 -e CLOUD_PROVIDER=memory -e RUST_MIN_STACK=33554432 \
  ghcr.io/hydra-db/hydradb:latest

# 2. ingest a drawing set (any multi-sheet construction PDF)
pip install pymupdf
python src/ingest.py path/to/set.pdf

# 3. live demo
python demo/serve.py        # -> http://127.0.0.1:8000

# 4. MSpaths exhibit (many-to-many resolution in one call)
python src/mspaths_demo.py path/to/set.pdf

# 5. full benchmark run (needs AEC-Bench checked out; see docs/)
python src/run_tasks.py
```

**Field notes:** five HydraDB limitations we hit in real work, each with a
reproduction and the shipped workaround — [docs/HYDRADB_NOTES.md](docs/HYDRADB_NOTES.md).
That file is our answer to *why this hackathon exists*.

## Attribution

- HydraDB — github.com/hydra-db/hydradb (AGPL-3.0)
- AEC-Bench — github.com/nomic-ai/aec-bench (Apache-2.0), arXiv:2603.29199
- PyMuPDF — text and geometry extraction

License: MIT (this repository's code).

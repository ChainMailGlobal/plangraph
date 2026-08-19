# Hack Hydra submission — form answers (draft)

Deadline: **Thu Aug 20, 11:59 PM PT**. Submit Wednesday night HST; Thursday is
buffer only. Fill the video link after upload; everything else is final once
COMPARISON.md numbers land.

---

**Project name:** PlanGraph

**Track:** 01 — Enterprise Context + Ontology

**Repository:** https://github.com/ChainMailGlobal/plangraph

**Video:** ⟨YouTube/Loom link — unlisted is fine, test in incognito⟩

**Team:** Daniel Kaneshiro (INViSU AI) — sole founder; built with Claude Code

**One-liner:**
The drawing set as a graph: entity resolution and multi-hop defect finding
for construction documents on HydraDB — no LLM in the answer path.

**Description (~150 words):**

Track 01's hard problem is entity resolution over messy enterprise documents
— deciding "Sam", "@soham" and "S. Ratnaparkhi" are one person. In a
construction bid set that decision is deciding A-452, A4.52 and A452 are one
sheet, and getting it wrong means a contractor builds from the wrong detail.

PlanGraph extracts each drawing set once (PyMuPDF), resolves identities at
ingest, and materialises the reference ontology in HydraDB:
Document→Sheet→Detail, callouts as first-class nodes with TARGETS_SHEET
edges, and — because the brief asks for "not in the data" as an answer —
resolution verdicts stored at write time. The graph doesn't guess: absence is
the defect.

Evaluated on AEC-Bench (Apache-2.0, disclosed) against the benchmark's own
published agent baseline, same official graders run verbatim. The answer path
contains no LLM: ingest once, and every answer is a HydraDB query at ~$0.
Full pre-registered methodology, dated run chain, failure buckets, and five
HydraDB field-note limitations with reproductions are in the repo.

**Where HydraDB is used / what breaks without it:**
HydraDB holds the identity graph and does all relational work: batched UNWIND
ingest over the HTTP API, multi-hop traversal, algo.MSpaths many-to-many
resolution, reverse adjacency for "referenced-from". Remove it and every
"does this exist" question becomes hand-built joins we'd have to keep
consistent ourselves. Field notes: docs/HYDRADB_NOTES.md.

---

## Pre-submit checklist

- [ ] README ⟨FREEZE⟩ cells filled from docs/COMPARISON.md
- [ ] Repo public — open in incognito
- [ ] LICENSE (MIT) visible on repo front page
- [ ] Video uploaded, link opens in incognito
- [ ] Video numbers == COMPARISON.md numbers
- [ ] Fresh-clone quickstart tested (docker run → ingest → demo)
- [ ] Form submitted; screenshot the confirmation

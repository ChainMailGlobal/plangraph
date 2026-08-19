# PlanGraph — 3-minute video script

Target: 2:55. Screen recording + voiceover. Read every number off
`docs/COMPARISON.md` on screen, never from memory.

---

## Beat 1 — The problem IS the brief (0:00–0:30)

**Screen:** Track 01 brief on screen, highlight the line about entity
resolution ("Sam / @soham / S. Ratnaparkhi"). Then cut to a real drawing
sheet, zoom on a callout bubble "5 / A902".

**VO:**
> Track 01 asks for an ontology over messy enterprise documents — misfiled,
> near-duplicated, contradictory — and for knowing when the answer just isn't
> in there. Our enterprise is a construction project. A bid set is enterprise
> data from six firms in one binder: architect, structural, mechanical,
> electrical, civil, landscape — each with its own naming conventions.
> The brief's hard problem is deciding "Sam", "@soham" and "S. Ratnaparkhi"
> are one person. In our corpus that's deciding **A-452, A4.52 and A452 are
> one sheet**. Same problem — but here, resolving it wrong means a contractor
> builds from the wrong detail.

## Beat 2 — The graph idea (0:30–1:00)

**Screen:** `docs/SCHEMA.md` diagram, then a terminal running
`python src/ingest.py <pdf>` — show the ingest stats line appear in seconds.

**VO:**
> So we extract once, resolve identity at ingest, and materialise the
> reference graph in HydraDB: documents contain sheets, sheets carry details,
> callouts target sheets. Every spelling variant collapses to one node at
> write time — entity resolution happens once, not on every query. And every
> callout stores a verdict: resolved, missing sheet, missing detail — because
> the brief's last requirement, knowing when the answer is NOT in the data,
> is the thing a graph answers natively. **The graph doesn't guess — absence
> is the defect.**

## Beat 3 — Live demo (1:00–2:20)

**Screen:** `python demo/serve.py` → browser at 127.0.0.1:8000.

**Record this beat in TWO takes** (cut them together):

*Take 1 — fresh container, ingest the **Lear** set only.* Click cards
1 → 2 → 4. Every click visibly hits HydraDB.

1. **Resolve a callout** — "callout → sheet → detail, one traversal,
   milliseconds."
2. **Dead end** — "7 slash L7-01 — a real planted defect. This reference
   points at nothing, and the missing edge IS the finding." (Lear-only graph
   keeps this card clean: exactly one dead end.)
4. **Reverse trace** — "where is this sheet referenced from? In SQL that's a
   recursive CTE. Here it's the same edges, read backwards."

*Between takes (off camera):* ingest the wcu set into the same graph —
`python src/ingest.py <wcu pdf>`. This takes ~4 minutes (79 pages of
CPU-bound extraction) — do NOT film it or call it fast.

*Take 2 — both sets loaded.*

3. **Alias cluster** — "we've also loaded a second firm's 79-page electrical
   set into the same graph. Their callouts write **E01**; the sheet is
   **E001**. One node. Different firm, different convention, same entity —
   this is the Sam/@soham problem, solved structurally, at write time."
   (Verified in the wcu PDF: callouts D35/E01, E03/E01 on sheets D102/D104,
   title-block sheet E001 — they share one graph node.)

**Then cut to the comparison table** (`docs/COMPARISON.md` on screen):

**VO — three claims, the table carries the rest:**
> Same tasks, same documents, same official graders — never modified. Three
> results. One: the graph **wins sheet-index consistency outright — 0.917 to
> 0.875**. Two: where the agent wins — resolution — the gap is extraction,
> reading the page, never the traversal. We proved that on the final run:
> six resolution tasks went from zero to perfect purely by improving
> extraction, zero regressions, and the graph never changed. Three: cost.
> The agent baseline is about 83 cents a task. PlanGraph has **no LLM
> anywhere** — after ingest, every answer is a graph query for effectively
> zero dollars, which is how it graded all 105 tasks, including the 48 the
> agent's budget never reached. Every number on this table has a dated run
> and published failure buckets behind it.

## Beat 4 — The boundary, in one breath (2:20–2:35)

**Screen:** README boundary section, then `docs/HYDRADB_NOTES.md` scrolled
slowly.

**VO:**
> The boundary is one sentence: our code does perception — PyMuPDF and a
> grammar — and HydraDB does everything relational: identity, traversal,
> reverse adjacency, batched writes. And we shipped field notes — five real
> limitations we hit building this, each with a reproduction and the
> workaround that shipped.

## Beat 5 — The close (2:35–2:55)

**Screen:** the demo page with the alias card visible, then fade to the
repo README title.

**VO:**
> Last thing, and it's why this matters beyond one bid set. Every reviewer
> correction lands in the graph as a stored, traceable fact. When a
> thirty-year plan reviewer retires, their judgment doesn't walk out the
> door — it's in the graph, with the traversal that justified every call.
> Enterprise knowledge that outlives the people who created it — that's the
> brief's real ask. And everything we measured points one direction: the
> ceiling is perception, not the graph. Better eyes, same memory.
> PlanGraph: the drawing set as a graph — on HydraDB.

---

## Recording checklist

- [ ] HydraDB container up (`memory` backend), Lear set ingested:
      `tasks/intradrawing/cross-reference-resolution/lear-theater-landscape-03-01/environment/Bid_set_-_Lear_Theater_240610.pdf`
- [ ] wcu set path ready in the terminal for the live-ingest beat:
      `tasks/intradrawing/cross-reference-tracing/wcu-a1-a523-medium/environment/16-15506-04E-WCU-FD3-DWG.pdf`
- [ ] All four demo cards clicked once BEFORE recording (warm, no surprises)
- [ ] `docs/COMPARISON.md` numbers final (freeze run) and matching the VO
- [ ] Track 01 brief open in a tab; SCHEMA.md open; HYDRADB_NOTES.md open
- [ ] Mic check; 1080p; hide bookmarks bar
- [ ] Watch once before upload; link opens in incognito

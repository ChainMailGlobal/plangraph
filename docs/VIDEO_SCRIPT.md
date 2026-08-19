# PlanGraph — 3-minute video script

Target: 2:50. Screen recording + voiceover. Numbers marked ⟨…⟩ get filled
from the frozen results table before recording — read them off
`docs/COMPARISON.md`, never from memory.

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

**Screen:** `python demo/serve.py` → browser at 127.0.0.1:8000. Click the
four cards IN ORDER, pausing ~15s each. Every click visibly hits HydraDB.

1. **Resolve a callout** — "callout → sheet → detail, one traversal,
   milliseconds."
2. **Dead end** — "this reference points at nothing. Nobody hallucinates an
   answer; the missing edge IS the finding."
3. **Alias cluster** — "three spellings, one node. This is the Sam/@soham
   problem, solved structurally."
4. **Reverse trace** — "where is this sheet referenced from? In SQL that's a
   recursive CTE. Here it's the same edges, read backwards."

**Then cut to the comparison table** (`docs/COMPARISON.md` on screen):

**VO:**
> Same tasks, same documents, same official graders — never modified. The
> published agent baseline costs about 88 cents a task. PlanGraph's answer
> path has **no LLM at all**: ingest once, every answer is a graph query for
> effectively zero dollars. Head-to-head, the graph **wins sheet-index
> consistency outright — 0.917 to 0.875** — and ties tracing at zero cost.
> Across all 24 tracing tasks it reaches **84% of the grader-capped ceiling**
> against the agent's 57%. Where the agent still wins — resolution, 0.76 to
> 0.57 — the gap is extraction, reading the page, never the traversal: our
> final run lifted six resolution tasks from zero to perfect with zero
> regressions, purely by improving extraction, and the graph never changed.
> Every number has a dated run and published failure buckets behind it.

## Beat 4 — Where HydraDB is, and what breaks without it (2:20–2:50)

**Screen:** README boundary section, then `docs/HYDRADB_NOTES.md` scrolled
slowly.

**VO:**
> The boundary is clean: PyMuPDF and our grammar do perception; HydraDB does
> everything relational — the identity graph, multi-hop traversal, reverse
> adjacency, batched UNWIND writes over the HTTP API. Take HydraDB out and
> every "does this exist" question becomes joins we'd have to hand-build and
> keep consistent. We also shipped field notes — five real limitations we hit,
> each with a reproduction and the workaround we used, from conditional-put
> gaps on the local backend to a silent pair-dropping mode in MSpaths.
> That's the report of someone who actually built on it. PlanGraph:
> the drawing set as a graph — on HydraDB.

---

## Recording checklist

- [ ] HydraDB container up (`memory` backend), Lear set ingested
- [ ] All four demo cards clicked once BEFORE recording (warm, no surprises)
- [ ] `docs/COMPARISON.md` numbers final (freeze run) and matching the VO
- [ ] Track 01 brief open in a tab; SCHEMA.md open; HYDRADB_NOTES.md open
- [ ] Mic check; 1080p; hide bookmarks bar
- [ ] Watch once before upload; link opens in incognito

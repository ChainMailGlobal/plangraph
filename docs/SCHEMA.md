# PlanGraph — graph schema (draft 1, 2026-08-18)

Ontology + entity resolution over construction document sets, in HydraDB.
Dataset: AEC-Bench (Apache-2.0, nomic-ai) — documents fetched from upstream
`manifest.jsonl`, never redistributed here.

## Constraints discovered by probing a live node (these SHAPE the schema)

| Cypher feature | Status | Consequence |
|---|---|---|
| `WHERE ... IS NULL` | **REJECTED** | Absence cannot be filtered server-side |
| `OPTIONAL MATCH` | works (returns `{"type":"null"}`) | Absence is *retrievable*, filter client-side |
| `WHERE` property comparison | works | **Materialise verdicts at ingest** |
| Reverse traversal | works | Cross-reference tracing is a plain MATCH |
| `WITH` | pass-through only | No multi-stage pipelines |
| Pattern | one rel type, directed | No `[:A\|B]`, no undirected |

**Design consequence:** resolution is computed at INGEST and written into the
graph as properties. This is not only a workaround — it is where entity
resolution belongs, and it is Track 01's stated hard part.

## Vertices

```
Document      {id, name, kind: drawings|spec|submittal}
Sheet         {id, sheet_no, norm_id, title, page, discipline, canonical: bool}
Detail        {id, detail_no, sheet_no, title}
Callout       {id, raw, det_token, sheet_token, src_sheet,
               resolved: bool, resolution: ok|missing_sheet|missing_detail|ambiguous}
IndexEntry    {id, listed_sheet_no, present: bool}
SpecSection   {id, number, title}
Requirement   {id, section, subject, value, conflict: bool}
DrawnValue    {id, sheet_no, subject, value}
```

`norm_id` is the entity-resolution key: uppercase, separators stripped, leading
zeros dropped — so `A452`, `A-452`, `A4.52`, `a452` collapse to one identity.

## Edges (all directed, one type per pattern)

```
(Document)-[:CONTAINS]->(Sheet)
(Sheet)-[:HAS_DETAIL]->(Detail)
(Sheet)-[:REFERENCES]->(Callout)
(Callout)-[:RESOLVES_TO]->(Detail)        // written only when resolution succeeds
(Callout)-[:TARGETS_SHEET]->(Sheet)
(Sheet)-[:ALIAS_OF]->(Sheet)              // non-canonical -> canonical
(Sheet)-[:SUPERSEDES]->(Sheet)            // revision chronology
(IndexEntry)-[:INDEXED_AS]->(Sheet)       // written only when the listed sheet exists
(SpecSection)-[:REQUIRES]->(Requirement)
(Requirement)-[:CONTRADICTS]->(DrawnValue)
```

Absence is represented by an edge that was **not written**, plus a materialised
boolean on the source vertex. Both halves matter: the boolean makes it
queryable, the missing edge makes it traversable.

## The four demo queries (all valid under the subset — verified)

```cypher
-- 1. Broken cross-references ("not in the data" as a positive finding)
MATCH (s)-[:REFERENCES]->(c) WHERE c.resolved = false
RETURN c.src_sheet AS on_sheet, c.raw AS callout, c.resolution AS why

-- 2. Reverse trace: everywhere a detail is called out from
MATCH (c)-[:RESOLVES_TO]->(d {id: $detail_id})
RETURN c.src_sheet AS referenced_from, c.raw AS callout

-- 3. Sheet-index inconsistency
MATCH (e) WHERE e.present = false RETURN e.listed_sheet_no AS listed_but_absent

-- 4. Spec/drawing contradiction
MATCH (r)-[:CONTRADICTS]->(v)
RETURN r.subject AS subject, r.value AS spec_says, v.value AS drawing_says
```

## Open questions for pressure-testing against AEC-Bench ground truth

1. **Alias reality.** Does `norm_id` collapse too much? `A5.01` vs `A501` may be
   distinct sheets in some sets. Needs checking against real sheet indexes.
2. **Supersession source.** AEC-Bench tasks are single-version; revisions may
   have to come from title-block dates rather than explicit rev markers.
3. **Ambiguous resolution.** A callout `3/A5` where both `A5` and `A5.1` exist —
   `ambiguous` verdict, or pick nearest?
4. **Detail-level vs sheet-level.** `missing_detail` (sheet exists, detail
   doesn't) is a different finding from `missing_sheet`; graders may only
   reward one.

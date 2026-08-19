# HydraDB field notes — what we hit building PlanGraph

Everything below was found while building a working system against HydraDB
v0.1.0 (`ghcr.io/hydra-db/hydradb:latest`, pulled 2026-08-18) on Windows 11 +
Docker Desktop, driving the HTTP query API (`POST /v1/graphs/default/query`).
Each item has the exact symptom, a minimal reproduction, and the workaround we
actually shipped. None of these blocked us — but every one cost us an hour we'd
like the next builder to keep.

## 1. Lone-vertex `CREATE` / `MERGE` are rejected — `MATCH ... SET` is the vertex primitive

**Symptom:** `CREATE (n {id: 1})` and `MERGE (n {id: 1})` both fail with
*"only one-hop edge patterns"* — even with clean literals. CREATE accepts
relationship paths only.

**Workaround (shipped in `src/hydra.py`):**
- Single vertex: `MATCH (n {id: 1}) SET n.k = 'v'` — this **creates-or-updates**
  the vertex, which is surprising coming from Neo4j (MATCH on a missing node
  is a no-op there) but is the reliable upsert primitive here.
- Bulk: the batched `UNWIND $rows AS row MERGE (n {id: row.vertex}) SET ...`
  form **is** legal — the bare-MERGE restriction applies only to the
  single-statement form. Parameters go as a real JSON array in the HTTP
  `parameters` field; the server caps a batch at 1024 rows
  (`client_query_batch_items`), so we chunk at 1000.

**Suggestion:** either accept lone-vertex CREATE/MERGE or say in the error
message that `MATCH ... SET` upserts. The current message sends you to the
wrong mental model (we assumed our escaping was broken for an hour).

## 2. `WHERE ... IS NULL` unsupported — absence must be materialised at ingest

**Symptom:** any `IS NULL` / `IS NOT NULL` predicate is rejected. You cannot
ask "which callouts have no resolution edge" at query time.

**Workaround (shipped in `src/ingest.py`):** we compute the verdict during
ingest and write it as a property — every `Callout` carries
`resolved: true/false` and `resolution: 'ok' | 'missing_sheet' |
'missing_detail'`. Queries then filter on a concrete value.

**Note:** for our workload this turned out to be a *feature in disguise* —
"absence is the defect" became a stored, indexable fact instead of a query-time
negation. But it's a real expressiveness gap for exploratory queries, and it
should be documented next to the OpenCypher-subset table.

## 3. `algo.MSpaths` — `pairwise:true` silently drops pairs on disjoint sets; args must be inline literals

**Symptom A:** with `pairwise:true`, pairs where `source.id > target.id` are
silently filtered (symmetric dedupe). On disjoint source/target sets
(Callouts → Sheets) roughly half the expected paths vanish with **no error and
no warning**. `pairwise:false` is mandatory for many-to-many over disjoint
sets.

**Symptom B:** `sourceValues` / `targetValues` / `relTypes` must be inline
string literals — passing them via `$parameters` fails. Large value lists must
be chunked into multiple CALLs.

**Suggestion:** a doc example of the disjoint-set case, and a warning (or an
option) when the id-ordering filter removes results. Silent partial results
are the worst failure mode a path engine can have.

## 4. Local filesystem backend: batched writes fail — `PutMode::Update` unimplemented

**Symptom:** with `CLOUD_PROVIDER=local`, every batched UNWIND write fails
(and the GC log spams the same error): LocalFileSystem does not implement
`put_opts` / `PutMode::Update`, i.e. no conditional puts.

**Workaround (shipped):** `CLOUD_PROVIDER=memory` for eval and demo — ingest
is seconds, so we rebuild per run, and a restart wiping the store doubles as
task isolation between benchmark tasks. S3/MinIO is the durable path.

**Suggestion:** fail fast at startup — "local backend does not support
conditional puts; batched writes will fail" — rather than per-write. The
per-write error reads like a client bug, not a backend capability gap.

## 5. Windows + Git Bash: MSYS path mangling breaks container env vars

**Symptom:** launching the container from Git Bash, `LOCAL_PATH=/data/store`
arrives inside the container as `C:/Program Files/Git/data/store` (MSYS
rewrites anything that looks like a POSIX path) → bare `PermissionDenied` at
startup with no hint of the real cause.

**Workaround (shipped in our run scripts):** `MSYS_NO_PATHCONV=1` on every
`docker run` invocation from Git Bash.

**Suggestion:** one line in the Windows section of the README. This is a
generic MSYS behaviour, but it manifests as a HydraDB startup crash and will
hit every Windows contributor first.

---

### Smaller observations

- **Node-only MATCH needs a predicate** — `MATCH (s) WHERE s.page = 7` is
  rejected; `MATCH (s:Sheet) WHERE s.page = 7` works. Label or id/property
  anchor required.
- **String escaping is backslash-style** — doubled single-quote (`''`), the
  other common Cypher convention, is a parse error. Worth one line in
  `cypher-compat.md`.
- **`WITH` is pass-through only** in the subset we exercised — fine for our
  workload, worth flagging for people porting Neo4j queries.
- **`RUST_MIN_STACK=33554432`** was needed for deep recursive queries on our
  larger sheets; the default stack overflows quietly inside the container.

### What we'd keep

The HTTP-first design (no driver to install), the deterministic id model, and
`MERGE`-with-`SET` batch semantics made a reproducible benchmark harness easy:
our entire client is ~160 lines of stdlib Python (`src/hydra.py`), and the
graph writes for a full drawing set (batched UNWIND on the memory backend)
land in under a second — extraction, not the database, dominates ingest time.

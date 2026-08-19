"""Minimal HydraDB client over the HTTP query API.

Only what PlanGraph needs, shaped by what the engine's OpenCypher subset
actually accepts. Verified against a live node on 2026-08-18:

  * `CREATE (n {...})` with no edge is REJECTED ("only one-hop edge patterns")
    — CREATE takes relationship paths, not lone vertices.
  * A bare `MERGE (n {id: N})` is likewise rejected.
  * `MATCH (n {id: N}) SET n.p = v` CREATES-OR-UPDATES the vertex. That is the
    vertex primitive here.
  * String literals are single-quoted with BACKSLASH escaping. Doubled-quote
    escaping ('') is a parse error.
  * `WHERE ... IS NULL` is rejected, so absence must be materialised as a
    property at ingest time (see docs/SCHEMA.md).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

BACKSLASH = chr(92)
QUOTE = chr(39)


class Hydra:
    def __init__(
        self,
        base: str = "http://127.0.0.1:8443",
        graph: str = "default",
        token: str = "local-development-token-32-bytes",
        cell: str = "cell-0",
    ):
        self.url = f"{base}/v1/graphs/{graph}/query"
        self.token = token
        self.cell = cell

    def q(self, cypher: str, parameters: dict | None = None) -> dict:
        payload = {"cell_id": self.cell, "query": cypher}
        if parameters:
            payload["parameters"] = parameters
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            self.url,
            data=body,
            headers={
                "Authorization": "Bearer " + self.token,
                "X-Graph-Namespace": "default",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                return {"error": json.loads(e.read().decode() or "{}")}
            except Exception:
                return {"error": {"message": "HTTP " + str(e.code)}}

    def rows(self, cypher: str) -> list:
        """Execute and flatten to a list of {column: value} dicts."""
        res = self.q(cypher)
        if "error" in res:
            err = res["error"]
            msg = err.get("message", err) if isinstance(err, dict) else err
            raise RuntimeError(str(msg) + " :: " + cypher[:160])
        cols = res.get("columns") or []
        out = []
        for row in res.get("rows") or []:
            out.append(
                {c: (v.get("value") if isinstance(v, dict) else v)
                 for c, v in zip(cols, row)}
            )
        return out

    # -- write primitives -------------------------------------------------

    def put(self, vid: int, props: dict) -> None:
        """Create-or-update a vertex. MATCH...SET is the only shape that works."""
        if not props:
            return
        sets = ", ".join(k + " = " + esc(v) for k, v in
                         (("n." + kk, vv) for kk, vv in props.items()))
        res = self.q("MATCH (n {id: " + str(int(vid)) + "}) SET " + sets)
        if "error" in res:
            raise RuntimeError("put(" + str(vid) + ") failed: " + str(res["error"]))

    def edge(self, src: int, rel: str, dst: int) -> None:
        """Create a directed edge. Endpoints are created implicitly if absent."""
        res = self.q(
            "CREATE (a {id: " + str(int(src)) + "})-[:" + rel + "]->(b {id: "
            + str(int(dst)) + "})"
        )
        if "error" in res:
            raise RuntimeError("edge failed: " + str(res["error"]))

    # -- batched writes ---------------------------------------------------
    #
    # The UNWIND batch form is the ONLY way to write at speed, and it is also
    # the only place a bare `MERGE (n {id: ...})` is legal -- the single-
    # statement form is rejected ("only one-hop edge patterns"). Parameters are
    # passed as a real JSON array over HTTP; do NOT inline them.
    # Hard cap is DEFAULT_MAX_PARAMETERS = 1024 rows per call, enforced as
    # `client_query_batch_items`, so we chunk below that.

    BATCH = 1000

    def put_many(self, label: str, props: list, rows: list) -> int:
        """Upsert many vertices. Each row needs 'vertex' plus every key in props."""
        if not rows:
            return 0
        sets = ["n:" + label] + ["n." + p + " = row." + p for p in props]
        cy = ("UNWIND $rows AS row MERGE (n {id: row.vertex}) SET " + ", ".join(sets))
        n = 0
        for i in range(0, len(rows), self.BATCH):
            chunk = rows[i:i + self.BATCH]
            res = self.q(cy, {"rows": chunk})
            if "error" in res:
                raise RuntimeError("put_many(" + label + ") failed: " + str(res["error"]))
            n += len(chunk)
        return n

    def edge_many(self, src_label: str, rel: str, dst_label: str,
                  rows: list, props: list | None = None) -> int:
        """Create many edges. Each row needs 'src', 'dst', 'rel' (edge id)."""
        if not rows:
            return 0
        props = props or []
        cy = ("UNWIND $rows AS row "
              "MATCH (s:" + src_label + " {id: row.src}), (d:" + dst_label + " {id: row.dst}) "
              "MERGE (s)-[r:" + rel + " {id: row.rel}]->(d)")
        if props:
            cy += " SET " + ", ".join("r." + p + " = row." + p for p in props)
        else:
            cy += " SET r.k = row.rel"      # SET is required by the batch template
        n = 0
        for i in range(0, len(rows), self.BATCH):
            chunk = rows[i:i + self.BATCH]
            res = self.q(cy, {"rows": chunk})
            if "error" in res:
                raise RuntimeError("edge_many(" + rel + ") failed: " + str(res["error"]))
            n += len(chunk)
        return n


def esc(s) -> str:
    """Escape a Python value into a Cypher literal.

    Integer, float, boolean and string literals only. Backslash escaping is
    what this parser accepts; doubled quotes are a parse error.
    """
    if isinstance(s, bool):
        return "true" if s else "false"
    if isinstance(s, (int, float)):
        return str(s)
    if s is None:
        return QUOTE + QUOTE
    t = str(s)
    t = t.replace(BACKSLASH, BACKSLASH + BACKSLASH)
    t = t.replace(QUOTE, BACKSLASH + QUOTE)
    t = t.replace("\n", " ").replace("\r", " ")
    return QUOTE + t + QUOTE

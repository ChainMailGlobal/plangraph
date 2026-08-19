"""MSpaths exhibit: many-to-many callout resolution in ONE algorithm call.

Ingests a PDF, then asks HydraDB's algo.MSpaths for paths from every callout
to every sheet in a single invocation — the batched form of "does this
reference land anywhere?". Two behaviours verified the hard way:

  * `pairwise:false` is MANDATORY on disjoint source/target sets --
    `pairwise:true` applies a source-id < target-id dedupe that silently
    drops roughly half the pairs. See docs/HYDRADB_NOTES.md #3.
  * sourceValues/targetValues/relTypes must be INLINE LITERALS, so the call
    is chunked when the value list is large.

Usage: python src/mspaths_demo.py <pdf>
"""
from __future__ import annotations

import sys

from hydra import Hydra
from ingest import build


def lit(vals):
    return "[" + ", ".join("'" + v.replace("'", "") + "'" for v in vals) + "]"


def main():
    pdf = sys.argv[1]
    h = Hydra()
    stats = build(pdf, h)
    print("ingested:", stats)

    det_keys = [r["k"] for r in h.rows(
        "MATCH (c:Callout) WHERE c.resolved = true "
        "RETURN DISTINCT c.raw AS k LIMIT 40") if r.get("k")]
    sheet_ids = [r["n"] for r in h.rows(
        "MATCH (s:Sheet) WHERE s.canonical = true "
        "RETURN s.norm_id AS n LIMIT 40") if r.get("n")]
    if not det_keys or not sheet_ids:
        print("graph has no resolvable callouts; ingest a richer set")
        return

    cy = ("CALL algo.MSpaths({"
          "sourceLabel:'Callout', sourceProperty:'raw', sourceValues:" + lit(det_keys) + ", "
          "targetLabel:'Sheet', targetProperty:'norm_id', targetValues:" + lit(sheet_ids) + ", "
          "pairwise:false, relTypes:['TARGETS_SHEET'], relDirection:'outgoing', "
          "maxLen:2, pathCount:1, resultLimit:200}) "
          "YIELD path, pathWeight RETURN path, pathWeight")
    res = h.q(cy)
    if "error" in res:
        print("MSpaths error:", res["error"])
        return
    rows = res.get("rows") or []
    print("MSpaths: %d source callouts x %d target sheets -> %d paths in ONE call"
          % (len(det_keys), len(sheet_ids), len(rows)))
    for r in rows[:8]:
        try:
            nodes = r[0]["value"]["nodes"]
            raw = nodes[0]["properties"]["raw"]["String"]
            tgt = nodes[-1]["properties"]["sheet_no"]["String"]
            print("  %-14s -> %s" % (raw, tgt))
        except Exception:
            print("  path:", str(r)[:120])
    print("  (every path above is a resolved reference; the planted defect has NO path)")


if __name__ == "__main__":
    main()

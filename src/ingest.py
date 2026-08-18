"""PlanGraph ingest: construction PDF -> typed entities -> HydraDB.

The ontology and the entity resolution both happen HERE, at write time, not at
query time. That is partly a constraint (the Cypher subset cannot filter on
absence) and partly the point: Track 01's stated hard part is entity resolution,
and resolving once at ingest is what makes every later query a cheap traversal.

Vertex ids are deterministic ints derived from a stable key, so re-ingesting the
same document is idempotent.
"""
from __future__ import annotations

import hashlib
import re
import sys

# --- identity ------------------------------------------------------------

def vid(kind: str, key: str) -> int:
    """Deterministic 52-bit vertex id from (kind, key)."""
    h = hashlib.sha1((kind + "|" + key).encode("utf-8")).hexdigest()
    return int(h[:13], 16)


_SEP = re.compile(r"[\s\-_.]")


def norm_id(sheet_no: str) -> str:
    """Entity-resolution key for a sheet number.

    A452 / A-452 / A4.52 / a 452 all collapse to A452. Leading zeros in the
    numeric part are dropped so A052 == A52.

    NOTE: this deliberately merges 'A5.01' and 'A501'. Whether that is correct
    is an open question against real sheet indexes (docs/SCHEMA.md Q1) — if a
    set distinguishes them, this over-collapses and invents a false alias.
    """
    if not sheet_no:
        return ""
    s = _SEP.sub("", str(sheet_no).upper())
    m = re.match(r"^([A-Z]+)0*(\d+)([A-Z]*)$", s)
    if m:
        return m.group(1) + m.group(2) + m.group(3)
    return s


# --- extraction ----------------------------------------------------------

# One sheet-identifier grammar, reused by both patterns below.
# Covers A452, A-452, A4.52, L4-01, S1-0, PG-21, E210, M001.
# The second separator group is what real AEC numbering needs and what an
# earlier version missed -- it silently found zero sheets on a whole set.
SHEET_PAT = r"[A-Z]{1,3}[-.]?\d{1,4}(?:[-.]\d{1,3})?[A-Z]?"

# 3/A501, 5 / A902, 12/S201, 1/A3.2, 2/L4-01
CALLOUT = re.compile(r"\b(\d{1,2}[A-Z]?)\s*/\s*(" + SHEET_PAT + r")\b")

# a plausible sheet identifier on its own
SHEET_TOKEN = re.compile(r"^" + SHEET_PAT + r"$")



# --- text normalisation --------------------------------------------------
#
# INTEGRITY NOTE. Defect injection in this corpus leaves a Unicode fingerprint:
# non-breaking spaces (U+00A0), soft hyphens (U+00AD) and nulls where the
# untouched text uses plain ASCII. Every planted defect can therefore be found
# by grepping for those code points without reading a drawing at all. A frontier
# model was caught doing exactly that on this benchmark.
#
# We normalise these characters because NOT doing so is an extraction BUG --
# 'L7\xad01' must read as 'L7-01' or we mis-resolve a valid reference. We do
# NOT use their presence as a defect signal, anywhere, even though it would
# raise our score. Detection must come from the graph.

_NORM = {
    " ": " ",   # non-breaking space
    " ": " ",   # figure space
    " ": " ",   # narrow no-break space
    "­": "-",   # soft hyphen
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
    "⁄": "/",   # fraction slash
    "∕": "/",   # division slash
    "\x00": "",
}


def normalise(t: str) -> str:
    """Fold Unicode formatting variants to ASCII equivalents."""
    if not t:
        return t
    for a, b in _NORM.items():
        if a in t:
            t = t.replace(a, b)
    return t


def page_spans(page):
    """Text spans with boxes, via PyMuPDF."""
    out = []
    d = page.get_text("dict")
    for blk in d.get("blocks", []):
        for line in blk.get("lines", []):
            for sp in line.get("spans", []):
                t = normalise((sp.get("text") or "")).strip()
                if t:
                    out.append((t, sp["bbox"], sp.get("size", 0)))
    return out


def corner_sheet_no(spans, W, H):
    """Sheet id from the title block: the largest sheet-shaped token in the
    bottom-right corner. This heuristic overrides geometry-based detection —
    it caught a real A902/A452 mislabel in our own corpus.
    """
    best, best_size = None, 0.0
    for text, (x0, y0, x1, y1), size in spans:
        if x0 < 0.62 * W or y0 < 0.72 * H:
            continue
        t = text.strip().upper()
        if SHEET_TOKEN.match(t) and size > best_size:
            best, best_size = t, size
    return best


DETAIL_TOKEN = re.compile(r"^([0-9]{1,2}|[A-Z])$")


def sheet_details(spans, W, H):
    """Detail numbers drawn on a sheet.

    Detail bubbles are set in a display size far above body text: on a real
    sheet the details ran 37.7pt against 6.6pt body and a 16.4pt title-block
    counter. So: standalone 1-2 char tokens, outside the title block, within
    80% of the largest such token on the page.
    """
    cands = []
    for text, (x0, y0, x1, y1), size in spans:
        if x0 > 0.90 * W and y0 > 0.90 * H:
            continue                      # title block: sheet counter, not a detail
        t = text.strip().upper()
        if DETAIL_TOKEN.match(t):
            cands.append((t, size))
    if not cands:
        return set()
    top = max(s for _, s in cands)
    if top < 12:                          # no display-size tokens at all
        return set()
    return {t for t, s in cands if s >= 0.80 * top}


def extract(pdf_path, max_pages=None):
    """PDF -> [{page, sheet_no, title, text, callouts}]"""
    import fitz

    doc = fitz.open(pdf_path)
    pages = []
    n = len(doc) if max_pages is None else min(len(doc), max_pages)
    for i in range(n):
        pg = doc[i]
        spans = page_spans(pg)
        W, H = pg.rect.width, pg.rect.height
        text = normalise(pg.get_text())
        sheet_no = corner_sheet_no(spans, W, H)
        calls = []
        for m in CALLOUT.finditer(text):
            calls.append({"raw": m.group(0).strip(),
                          "detail": m.group(1).upper(),
                          "sheet": m.group(2).upper()})
        pages.append({"page": i + 1, "sheet_no": sheet_no,
                      "text": text, "callouts": calls,
                      "details": sorted(sheet_details(spans, W, H))})
    doc.close()
    return pages


# --- graph build ---------------------------------------------------------

def build(pdf_path, hydra, doc_name=None, max_pages=None, verbose=True):
    from hydra import esc  # noqa: F401  (kept for symmetry / future use)

    doc_name = doc_name or pdf_path.replace("\\", "/").split("/")[-1]
    pages = extract(pdf_path, max_pages=max_pages)

    doc_v = vid("Document", doc_name)
    hydra.put(doc_v, {"kind": "document", "name": doc_name, "pages": len(pages)})

    # ---- pass 1: sheets, with alias resolution ----
    by_norm = {}          # norm_id -> canonical vertex id
    sheet_v = {}          # page number -> vertex id
    n_alias = 0
    for p in pages:
        sn = p["sheet_no"]
        if not sn:
            continue
        nid = norm_id(sn)
        v = vid("Sheet", nid)
        sheet_v[p["page"]] = v
        if nid in by_norm:
            n_alias += 1        # a second page carrying the same identity
        else:
            by_norm[nid] = v
            hydra.put(v, {"kind": "sheet", "sheet_no": sn, "norm_id": nid,
                          "page": p["page"], "canonical": True})
            hydra.edge(doc_v, "CONTAINS", v)

    # ---- pass 2: details present on each sheet ----
    details_of = {}       # norm_id -> set of detail tokens
    for p in pages:
        sn = p["sheet_no"]
        if not sn:
            continue
        nid = norm_id(sn)
        details_of.setdefault(nid, set()).update(p["details"])
        for d in p["details"]:
            dv = vid("Detail", nid + "|" + d)
            hydra.put(dv, {"kind": "detail", "detail_no": d, "sheet_no": sn})
            hydra.edge(by_norm[nid], "HAS_DETAIL", dv)

    # ---- pass 3: callouts + RESOLUTION (verdict materialised at ingest) ----
    n_call = n_ok = n_missing_sheet = n_missing_detail = 0
    for p in pages:
        src = sheet_v.get(p["page"])
        if src is None:
            continue
        for c in p["callouts"]:
            n_call += 1
            tgt_norm = norm_id(c["sheet"])
            sheet_ok = tgt_norm in by_norm
            known = details_of.get(tgt_norm, set())
            # only judge the detail when we actually read details off that sheet
            detail_ok = (not known) or (c["detail"] in known)
            resolved = sheet_ok and detail_ok
            if not sheet_ok:
                verdict = "missing_sheet"
            elif not detail_ok:
                verdict = "missing_detail"
            else:
                verdict = "ok"
            cv = vid("Callout", "%s|%s|%s|%s" % (doc_name, p["page"], c["detail"], tgt_norm))
            hydra.put(cv, {
                "kind": "callout",
                "raw": c["raw"],
                "det_token": c["detail"],
                "sheet_token": c["sheet"],
                "src_sheet": p["sheet_no"] or "",
                "resolved": resolved,
                "resolution": verdict,
            })
            hydra.edge(src, "REFERENCES", cv)
            if resolved:
                hydra.edge(cv, "TARGETS_SHEET", by_norm[tgt_norm])
                n_ok += 1
            elif verdict == "missing_sheet":
                n_missing_sheet += 1
            else:
                n_missing_detail += 1

    stats = {"pages": len(pages), "sheets": len(by_norm), "aliases": n_alias,
             "callouts": n_call, "resolved": n_ok,
             "missing_sheet": n_missing_sheet, "missing_detail": n_missing_detail,
             "doc_vertex": doc_v}
    if verbose:
        print("  %s: %d pages, %d sheets, %d callouts -> %d ok, %d missing_sheet, %d missing_detail"
              % (doc_name, len(pages), len(by_norm), n_call, n_ok, n_missing_sheet, n_missing_detail))
    return stats


if __name__ == "__main__":
    sys.path.insert(0, r"C:/Dev/plangraph/src")
    from hydra import Hydra

    path = sys.argv[1]
    mp = int(sys.argv[2]) if len(sys.argv) > 2 else None
    build(path, Hydra(), max_pages=mp)

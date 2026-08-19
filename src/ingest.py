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
import os
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
# v2 grammar — the measured fix from the as-is run's bucket-A list: sheet ids
# with MULTIPLE dot/dash groups (T7.1.1, A9.2.5, D101.3) were invisible to v1,
# which allowed at most one trailing group.
SHEET_PAT = r"[A-Z]{1,3}[-.]?\d{1,4}(?:[-.]\d{1,3}){0,3}[A-Z]?"

# v2 detail token — digit-first (3, 12A), letter-first (A5, B12), or a short
# range (2-3); all three shapes appear verbatim in the bucket-A defect list.
# 3/A501, 5 / A902, 46 / A9.2.5, A5/G106, 2-3/LH501
CALLOUT = re.compile(
    r"\b(\d{1,2}[A-Z]?|[A-Z]\d{1,2}|\d{1,2}\s*-\s*\d{1,2})\s*/\s*(" + SHEET_PAT + r")\b")

# a plausible sheet identifier on its own
SHEET_TOKEN = re.compile(r"^" + SHEET_PAT + r"$")
# an index ROW as a single span: sheet token, separator, inline title
ROW_TOKEN = re.compile(r"^(" + SHEET_PAT + r")[ .\-:–—]")



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
        if x0 > W or y0 > H:
            continue                      # bbox outside the page: rotation artifact
        if x0 < 0.62 * W or y0 < 0.72 * H:
            continue
        t = text.strip().upper()
        if SHEET_TOKEN.match(t) and size > best_size:
            best, best_size = t, size
    if best is None:
        # some title blocks run along the TOP band instead (measured:
        # saluda set, number at y=0.05H in 50pt against 9pt body). Additive
        # fallback -- fires only when the corner has nothing: the largest
        # sheet-shaped token on the page, display-size only.
        for text, (x0, y0, x1, y1), size in spans:
            if x0 > W or y0 > H:
                continue
            t = text.strip().upper()
            if size >= 18 and SHEET_TOKEN.match(t) and size > best_size:
                best, best_size = t, size
    return best


INDEX_HEAD = re.compile(r"(SHEET|DRAWING)\s+(INDEX|LIST)|INDEX\s+OF\s+(DRAWINGS|SHEETS)", re.I)


def corner_title(spans, W, H, sheet_no):
    """Sheet title from the title block: the display-size alpha text in the
    corner region. Titles WRAP across spans ('LEVEL 4 - FLOOR' / 'PLAN -
    HVAC'), so every span within 85% of the largest size is joined in reading
    order -- a single-span pick truncates and then reads as a title mismatch."""
    cands = []
    for text, (x0, y0, x1, y1), size in spans:
        if x0 < 0.62 * W or y0 < 0.62 * H:
            continue
        t = text.strip()
        if len(t) < 4 or t.upper() == (sheet_no or "").upper():
            continue
        if not re.search(r"[A-Za-z]{3}", t) or SHEET_TOKEN.match(t.upper()):
            continue
        cands.append((t.upper(), (x0, y0), size))
    if not cands:
        return ""
    top = max(s for _, _, s in cands)
    parts = [(pos[1], pos[0], t) for t, pos, s in cands if s >= 0.85 * top]
    return " ".join(t for _, _, t in sorted(parts))[:80]


def index_entries(doc, max_scan=8):
    """(sheet_no, title) pairs from the drawing-index page.

    The trap (measured): energy-code citations (C403.2.7.1) are sheet-shaped,
    so a line parser ingests the IECC as an index. Real entries live in an
    X-ALIGNED LABEL COLUMN with title text beside them; code citations sit
    inside prose. So: heading page first, then column clustering on spans.
    """
    for i in range(min(max_scan, len(doc))):
        text = normalise(doc[i].get_text())
        if not INDEX_HEAD.search(text):
            continue
        spans = page_spans(doc[i])
        # two row layouts, both real: (A) sheet token in its OWN span, title
        # in neighbouring spans; (B) one span per row -- "M1.0 - FLOOR PLAN".
        toks = []
        for t, b, s in spans:
            u = t.strip().upper()
            if len(u) < 2:
                continue
            if SHEET_TOKEN.match(u):
                toks.append((u, b, None))            # layout A
                continue
            m = ROW_TOKEN.match(u)
            if m and re.search(r"[A-Za-z]{3}", u[m.end():]):
                inline = u[m.end():].lstrip(" .-:–—")[:80]
                toks.append((m.group(1), b, inline))  # layout B
        # cluster sheet tokens by x0 (the label column)
        cols = {}
        for t, b, inline in toks:
            cols.setdefault(round(b[0] / 12), []).append((t, b, inline))
        entries = []
        for _, members in cols.items():
            if len(members) < 4:          # a real index column has many rows
                continue
            for t, (x0, y0, x1, y1), inline in members:
                if inline is not None:
                    entries.append((t, inline))
                    continue
                title_bits = [(b2[0], t2.strip()) for t2, b2, s2 in spans
                              if b2[0] > x1 and b2[0] < x1 + 0.45 * doc[i].rect.width
                              and abs((b2[1] + b2[3]) / 2 - (y0 + y1) / 2) < (y1 - y0)
                              and re.search(r"[A-Za-z]{3}", t2)]
                title = " ".join(t2 for _, t2 in sorted(title_bits))[:80].upper()
                entries.append((t, title))
        # rotated index (drawn at 90 deg): tokens align on y0 instead, each
        # LINE is a thin vertical lane -- title spans share the token's x lane
        if not entries:
            yrows = {}
            for t, b, inline in toks:
                yrows.setdefault(round(b[1] / 12), []).append((t, b, inline))
            for _, members in yrows.items():
                if len(members) < 4:
                    continue
                for t, (x0, y0, x1, y1), inline in members:
                    if inline is not None:
                        entries.append((t, inline))
                        continue
                    lane = max(8.0, x1 - x0)
                    title_bits = [(b2[1], t2.strip()) for t2, b2, s2 in spans
                                  if abs(b2[0] - x0) < 1.5 * lane
                                  and abs(b2[1] - y0) > 1
                                  and re.search(r"[A-Za-z]{3}", t2)]
                    title_bits.sort(key=lambda z: abs(z[0] - y0))
                    title = " ".join(t2 for _, t2 in title_bits[:4])[:80].upper()
                    entries.append((t, title))
        if entries:
            return entries, i + 1
    return [], None


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


DET_SPAN = re.compile(r"^([A-Z]?\d{1,2}[A-Z]?)$")


def bubble_callouts(spans):
    """Graphic callout bubbles: a detail token stacked ABOVE a sheet token
    (the circle-with-divider convention). Two separate spans, no slash — the
    inline CALLOUT regex cannot see these. Measured fix #4: every scoreable
    tracing task failed because its references are drawn this way.

    Pairing rule: detail-shaped span whose box x-overlaps a sheet-shaped span
    below it, with a vertical gap under 60% of the detail span's height, and
    both in similar (display) sizes.
    """
    dets, sheets = [], []
    grid = {}                       # x-bucket -> sheet spans (kills the O(n^2))
    for text, (x0, y0, x1, y1), size in spans:
        t = text.strip().upper()
        if SHEET_TOKEN.match(t) and any(ch.isdigit() for ch in t):
            rec = (t, x0, y0, x1, y1, size)
            sheets.append(rec)
            grid.setdefault(int(x0 // 150), []).append(rec)
        if DET_SPAN.match(t):
            dets.append((t, x0, y0, x1, y1, size))
    out = []
    for dt, dx0, dy0, dx1, dy1, dsz in dets:
        h = max(dy1 - dy0, 1.0)
        bucket = int(dx0 // 150)
        for st, sx0, sy0, sx1, sy1, ssz in (
                grid.get(bucket, []) + grid.get(bucket - 1, []) + grid.get(bucket + 1, [])):
            if st == dt:
                continue
            x_overlap = min(dx1, sx1) - max(dx0, sx0)
            gap = sy0 - dy1
            # measured on a real bubble (B1 over A511, wcu p51): gap was 0.7h,
            # the old 0.6h ceiling missed it by one point. 1.3h with slight
            # overlap allowed covers the drawn divider line between the tokens.
            if x_overlap > 0.3 * (dx1 - dx0) and -0.3 * h <= gap <= 1.3 * h \
                    and 0.5 <= (ssz / dsz if dsz else 1) <= 2.0:
                out.append({"raw": dt + "/" + st, "detail": dt, "sheet": st})
                break
    return out


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
        title = corner_title(spans, W, H, sheet_no)
        calls = []
        for m in CALLOUT.finditer(text):
            calls.append({"raw": m.group(0).strip(),
                          "detail": m.group(1).upper(),
                          "sheet": m.group(2).upper()})
        # graphic bubbles (stacked spans) — dedupe against inline finds
        seen_pairs = {(c["detail"], c["sheet"]) for c in calls}
        for b in bubble_callouts(spans):
            if (b["detail"], b["sheet"]) not in seen_pairs:
                calls.append(b)
        pages.append({"page": i + 1, "sheet_no": sheet_no, "title": title,
                      "text": text, "callouts": calls,
                      "details": sorted(sheet_details(spans, W, H))})
    entries, idx_page = index_entries(doc)
    doc.close()
    return pages, entries, idx_page


# --- graph build ---------------------------------------------------------

def build(pdf_path, hydra, doc_name=None, max_pages=None, verbose=True):
    """Batched build.

    All writes go through the UNWIND batch form. That is not a micro-
    optimisation: it is the only shape that scales, and it is also the only
    place a bare `MERGE (n {id: ...})` is legal -- the single-statement form is
    rejected outright. Requires an object store with conditional puts;
    LocalFileSystem does NOT implement `put_opts`/`PutMode::Update`, so use the
    memory or S3/MinIO backend.
    """
    doc_name = doc_name or pdf_path.replace("\\", "/").split("/")[-1]
    pages, idx_entries, idx_page = extract(pdf_path, max_pages=max_pages)

    doc_v = vid("Document", doc_name)
    V_doc = [{"vertex": doc_v, "kind": "document", "name": doc_name,
              "pages": len(pages)}]
    V_sheet, V_detail, V_callout, V_index = [], [], [], []
    E_contains, E_hasdetail, E_references, E_targets, E_indexed = [], [], [], [], []

    def eid(src, rel, dst):
        return vid("E", str(src) + "|" + rel + "|" + str(dst))

    # ---- pass 1: sheets, with alias resolution (collect only) ----
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
            V_sheet.append({"vertex": v, "kind": "sheet", "sheet_no": sn,
                            "norm_id": nid, "page": p["page"], "canonical": True,
                            "title": p.get("title", ""),
                            "hosts_index": p["page"] == idx_page})
            E_contains.append({"src": doc_v, "dst": v,
                               "rel": eid(doc_v, "CONTAINS", v)})

    # ---- pass 2: details present on each sheet (collect only) ----
    details_of = {}       # norm_id -> set of detail tokens
    seen_detail = set()
    for p in pages:
        sn = p["sheet_no"]
        if not sn:
            continue
        nid = norm_id(sn)
        details_of.setdefault(nid, set()).update(p["details"])
        for d in p["details"]:
            key = nid + "|" + d
            if key in seen_detail:
                continue
            seen_detail.add(key)
            dv = vid("Detail", key)
            V_detail.append({"vertex": dv, "kind": "detail",
                             "detail_no": d, "sheet_no": sn})
            E_hasdetail.append({"src": by_norm[nid], "dst": dv,
                                "rel": eid(by_norm[nid], "HAS_DETAIL", dv)})

    # ---- pass 3: callouts + RESOLUTION (verdict materialised; collect only) ----
    n_call = n_ok = n_missing_sheet = n_missing_detail = 0
    seen_callout = set()
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
            ckey = "%s|%s|%s|%s" % (doc_name, p["page"], c["detail"], tgt_norm)
            cv = vid("Callout", ckey)
            if cv not in seen_callout:
                seen_callout.add(cv)
                V_callout.append({
                    "vertex": cv, "kind": "callout", "raw": c["raw"],
                    "det_token": c["detail"], "sheet_token": c["sheet"],
                    "src_sheet": p["sheet_no"] or "",
                    "resolved": resolved, "resolution": verdict,
                })
                E_references.append({"src": src, "dst": cv,
                                     "rel": eid(src, "REFERENCES", cv)})
                if resolved:
                    E_targets.append({"src": cv, "dst": by_norm[tgt_norm],
                                      "rel": eid(cv, "TARGETS_SHEET", by_norm[tgt_norm])})
            if resolved:
                n_ok += 1
            elif verdict == "missing_sheet":
                n_missing_sheet += 1
            else:
                n_missing_detail += 1

    # ---- index entries: the listed-vs-present verdict, materialised ----
    listed_norms = set()
    for sn_listed, title_listed in idx_entries:
        nid = norm_id(sn_listed)
        if nid in listed_norms:
            continue
        listed_norms.add(nid)
        iv = vid("IndexEntry", doc_name + "|" + nid)
        present = nid in by_norm
        V_index.append({"vertex": iv, "kind": "index_entry",
                        "listed_sheet_no": sn_listed, "listed_title": title_listed,
                        "present": present})
        if present:
            E_indexed.append({"src": iv, "dst": by_norm[nid],
                              "rel": eid(iv, "INDEXED_AS", by_norm[nid])})

    # ---- single write section: batched UNWIND (1000-row chunks) ----
    hydra.put_many("Document", ["kind", "name", "pages"], V_doc)
    hydra.put_many("Sheet", ["kind", "sheet_no", "norm_id", "page", "canonical",
                             "title", "hosts_index"], V_sheet)
    hydra.put_many("IndexEntry", ["kind", "listed_sheet_no", "listed_title",
                                  "present"], V_index)
    hydra.edge_many("IndexEntry", "INDEXED_AS", "Sheet", E_indexed)
    hydra.put_many("Detail", ["kind", "detail_no", "sheet_no"], V_detail)
    hydra.put_many("Callout", ["kind", "raw", "det_token", "sheet_token",
                               "src_sheet", "resolved", "resolution"], V_callout)
    hydra.edge_many("Document", "CONTAINS", "Sheet", E_contains)
    hydra.edge_many("Sheet", "HAS_DETAIL", "Detail", E_hasdetail)
    hydra.edge_many("Sheet", "REFERENCES", "Callout", E_references)
    hydra.edge_many("Callout", "TARGETS_SHEET", "Sheet", E_targets)

    stats = {"pages": len(pages), "sheets": len(by_norm), "aliases": n_alias,
             "callouts": n_call, "resolved": n_ok,
             "missing_sheet": n_missing_sheet, "missing_detail": n_missing_detail,
             "doc_vertex": doc_v}
    if verbose:
        print("  %s: %d pages, %d sheets, %d callouts -> %d ok, %d missing_sheet, %d missing_detail"
              % (doc_name, len(pages), len(by_norm), n_call, n_ok, n_missing_sheet, n_missing_detail))
    return stats


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from hydra import Hydra

    path = sys.argv[1]
    mp = int(sys.argv[2]) if len(sys.argv) > 2 else None
    print(build(path, Hydra(), max_pages=mp))

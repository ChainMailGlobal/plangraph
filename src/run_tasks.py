"""PlanGraph task runner: fresh graph -> ingest -> query -> output.jsonl -> official grader.

Per task:
  1. `docker restart hydradb` — memory backend, so restart = empty graph.
     Crude and bulletproof task isolation: deterministic sheet vertex-ids would
     otherwise collide across tasks that share source documents, letting one
     task's sheets resolve another task's deliberately-broken callouts.
  2. Ingest the task's PDFs (batched UNWIND, src/ingest.py — AS-IS, no
     extraction changes before the first measured run).
  3. Answer from the graph, deterministically. NO LLM anywhere in this file.
  4. Grade with the task's own tests/test.sh VERBATIM in a temp workspace
     (only the two hardcoded paths are rewritten). Graders are never modified.

Families answered from the graph: cross-reference-resolution, cross-reference-
tracing, sheet-index-consistency (graph side only, as-is), spec-drawing-sync
(pre-registered to lose; minimal answer). Other families: "not attempted" —
we do not throw garbage at graders.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hydra import Hydra          # noqa: E402
from ingest import build, norm_id  # noqa: E402

BENCH = r"C:/Dev/aec-bench/tasks"
DOCS = os.path.join(HERE, "..", "docs")
RUNS = os.path.join(HERE, "..", "runs")

FAMILIES = {
    "intradrawing/cross-reference-resolution": "resolution",
    "intradrawing/cross-reference-tracing": "tracing",
    "intradrawing/sheet-index-consistency": "sheet_index",
    "intraproject/spec-drawing-sync": "spec_sync",
}


# ---------------------------------------------------------------- graph reset

def fresh_graph(timeout=60):
    subprocess.run(["docker", "restart", "hydradb"], capture_output=True, timeout=120)
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            import urllib.request
            with urllib.request.urlopen("http://127.0.0.1:9090/readyz", timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1.5)
    return False


# ---------------------------------------------------------------- answers

def q_broken(h, page_sheet=None):
    rows = h.rows("MATCH (s)-[:REFERENCES]->(c) WHERE c.resolved = false "
                  "RETURN c.src_sheet AS src, c.raw AS raw, c.det_token AS det, "
                  "c.sheet_token AS tgt, c.resolution AS why")
    if page_sheet:
        want = norm_id(page_sheet)
        rows = [r for r in rows if norm_id(r["src"] or "") == want]
    return rows


def answer_resolution(h, instruction):
    """Broken cross-references, optionally scoped to the page the task names."""
    sheet = None
    m = re.search(r"page\s+(\d+)", instruction, re.I)
    page_no = int(m.group(1)) if m else None
    if page_no:
        r = h.rows("MATCH (s:Sheet) WHERE s.page = %d RETURN s.sheet_no AS sn" % page_no)
        sheet = r[0]["sn"] if r else None
    rows = q_broken(h, sheet)
    lines = []
    for r in rows:
        raw = (r["raw"] or "").strip()
        compact = raw.replace(" ", "")
        if r["why"] == "missing_detail":
            title = ("%s (%s) on %s: detail %s not found on sheet %s"
                     % (raw, compact, r["src"], r["det"], r["tgt"]))
        else:
            title = ("%s (%s) on %s: target sheet %s not found in set"
                     % (raw, compact, r["src"], r["tgt"]))
        lines.append({"title": title, "sheet_number": r["src"] or "N/A"})
    if not lines:
        lines = [{"title": "No issues found", "sheet_number": "N/A"}]
    return lines


def answer_tracing(h, instruction):
    """Reverse trace: everywhere detail D of sheet S is called out from."""
    # v2 parse (measured fix): instructions phrase the target as
    # "references 2 on sheet A851" — no word "detail". Accept both, plus N/S.
    # v3: detail token may be letter-first (references B1 on sheet A511)
    m = re.search(r"references\s+([A-Za-z]?\d{1,2}[A-Za-z]?)\s+on\s+sheet\s+([A-Z]{1,3}[-.]?\d[\d.\-]*)",
                  instruction, re.I)
    if not m:
        m = re.search(r"[Dd]etail\s+(\d{1,2}[A-Za-z]?)\s+on\s+[Ss]heet\s+([A-Z]{1,3}[-.]?\d[\d.\-]*)",
                      instruction)
    if not m:
        m = re.search(r"(\d{1,2}[A-Za-z]?)\s*/\s*([A-Z]{1,3}[-.]?\d[\d.\-]*)", instruction)
    if not m:
        return [{"title": "No issues found", "sheet_number": "N/A"}]
    det, tgt = m.group(1).upper(), norm_id(m.group(2))
    rows = h.rows("MATCH (s)-[:REFERENCES]->(c) "
                  "RETURN s.sheet_no AS src, c.det_token AS det, c.sheet_token AS tgt")
    hits, seen = [], set()
    for r in rows:
        if (r["det"] or "").upper() == det and norm_id(r["tgt"] or "") == tgt:
            src = r["src"] or "?"
            if src not in seen:
                seen.add(src)
                hits.append({"title": "Referenced from %s" % src, "sheet_number": src})
    if not hits:
        hits = [{"title": "No references found - detail may be orphaned",
                 "sheet_number": "N/A"}]
    return hits


def answer_sheet_index(h, instruction):
    """v2 (measured fix): IndexEntry nodes now exist. Three finding kinds:
    missing (listed, not present), unlisted (present, not listed), and title
    mismatch (index title vs title-block title, similar-but-different)."""
    from ingest import norm_id as _nid
    entries = h.rows("MATCH (e:IndexEntry) WHERE e.kind = 'index_entry' "
                     "RETURN e.listed_sheet_no AS sn, e.listed_title AS lt, "
                     "e.present AS present")
    sheets = h.rows("MATCH (s:Sheet) WHERE s.canonical = true "
                    "RETURN s.sheet_no AS sn, s.title AS title, "
                    "s.hosts_index AS hosts_index")
    if not entries:
        return [{"title": "No issues found", "sheet_number": "N/A"}]
    listed = {_nid(e["sn"]): e for e in entries}
    present = {_nid(s["sn"]): s for s in sheets}
    lines = []
    # presence decided at QUERY time across all documents in the graph --
    # the stored per-document flag would misfire on split sets
    for nid, e in listed.items():
        if nid not in present:
            lines.append({"title": "Sheet %s ('%s') is listed in the index but "
                                   "not found in the document (missing sheet)"
                                   % (e["sn"], (e["lt"] or "")[:40]),
                          "sheet_number": e["sn"]})
    for nid, s in present.items():
        # the sheet HOSTING the index (cover/title sheet) is routinely left
        # off its own list -- absence there is convention, not a defect
        if s.get("hosts_index"):
            continue
        if nid not in listed:
            lines.append({"title": "Sheet %s ('%s') exists in the document but "
                                   "is not listed in the sheet index"
                                   % (s["sn"], (s["title"] or "")[:40]),
                          "sheet_number": s["sn"]})
    for nid, e in listed.items():
        s = present.get(nid)
        if not s:
            continue
        a = set((e["lt"] or "").split())
        b = set((s["title"] or "").split())
        # token-SUBSET means truncation (corner title cut short), not a
        # defect; a real title edit (DIAGRAM -> DIAGRAMS) is never a subset
        if (a and b and a != b and not (a <= b or b <= a)
                and len(a & b) >= max(1, len(a) // 2)):
            lines.append({"title": "Sheet %s title mismatch: index says '%s' "
                                   "but title block says '%s'"
                                   % (e["sn"], e["lt"], s["title"]),
                          "sheet_number": e["sn"]})
    if not lines:
        lines = [{"title": "No issues found", "sheet_number": "N/A"}]
    return lines


def answer_spec_sync(h, instruction):
    """Pre-registered to lose: no spec-requirement comparison in the graph."""
    return [{"title": "No issues found", "sheet_number": "N/A"}]


ANSWERERS = {
    "resolution": answer_resolution,
    "tracing": answer_tracing,
    "sheet_index": answer_sheet_index,
    "spec_sync": answer_spec_sync,
}


# ---------------------------------------------------------------- grading

def grade(task_dir, output_text):
    """Run the task's own test.sh VERBATIM; only /workspace and /logs paths
    are rewritten to a temp dir. Never modify grader logic."""
    ws = tempfile.mkdtemp(prefix="plangraph_ws_")
    try:
        logs = os.path.join(ws, "logs", "verifier")
        os.makedirs(logs)
        with open(os.path.join(ws, "output.jsonl"), "w", encoding="utf-8") as f:
            f.write(output_text)
        src = open(os.path.join(task_dir, "tests", "test.sh"),
                   encoding="utf-8", errors="replace").read()
        wsp = ws.replace("\\", "/")
        src = src.replace("/workspace", wsp).replace("/logs/verifier", wsp + "/logs/verifier")
        sh = os.path.join(ws, "test.sh")
        with open(sh, "w", encoding="utf-8", newline="\n") as f:
            f.write(src)
        bash = r"C:\Program Files\Git\bin\bash.exe"
        subprocess.run([bash, sh], capture_output=True, timeout=180)
        with open(os.path.join(ws, "logs", "verifier", "reward.json"), encoding="utf-8") as f:
            return float(json.load(f).get("reward", 0.0))
    except Exception:
        return 0.0
    finally:
        shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------- main loop

def task_pdfs(task_dir):
    out = []
    for root, _, fs in os.walk(os.path.join(task_dir, "environment")):
        out += [os.path.join(root, f) for f in fs if f.lower().endswith(".pdf")]
    return sorted(out)


def run_task(rel):
    fam_dir = rel.rsplit("/", 1)[0]
    kind = FAMILIES.get(fam_dir)
    task_dir = os.path.join(BENCH, rel)
    name = os.path.basename(rel)
    t0 = time.time()
    if kind is None:
        return {"task": name, "family": fam_dir, "reward": None,
                "note": "not_attempted", "wall_s": 0}
    if not fresh_graph():
        return {"task": name, "family": fam_dir, "reward": 0.0,
                "note": "graph_restart_failed", "wall_s": round(time.time() - t0, 1)}
    h = Hydra()
    stats = []
    try:
        for pdf in task_pdfs(task_dir):
            stats.append(build(pdf, h, verbose=False))
    except Exception as e:
        return {"task": name, "family": fam_dir, "reward": 0.0,
                "note": "ingest_error: " + str(e)[:80],
                "wall_s": round(time.time() - t0, 1)}
    instruction = open(os.path.join(task_dir, "instruction.md"),
                       encoding="utf-8", errors="replace").read()
    lines = ANSWERERS[kind](h, instruction)
    out_text = "\n".join(json.dumps(l) for l in lines) + "\n"
    run_dir = os.path.join(RUNS, name)
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "output.jsonl"), "w", encoding="utf-8") as f:
        f.write(out_text)
    reward = grade(task_dir, out_text)
    return {"task": name, "family": fam_dir, "reward": reward,
            "n_lines": len(lines),
            "ingest": {"sheets": sum(s["sheets"] for s in stats),
                       "callouts": sum(s["callouts"] for s in stats)},
            "wall_s": round(time.time() - t0, 1)}


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    tasks = []
    for fam in sorted(FAMILIES):
        for d in sorted(glob.glob(os.path.join(BENCH, fam, "*"))):
            if os.path.isdir(d) and os.path.exists(os.path.join(d, "tests", "test.sh")):
                tasks.append(fam + "/" + os.path.basename(d))
    if only:
        tasks = [t for t in tasks if only in t]
    out_path = os.path.join(DOCS, "plangraph_results.jsonl")
    done = set()
    if os.path.exists(out_path):
        for l in open(out_path, encoding="utf-8"):
            try:
                done.add(json.loads(l)["task"])
            except Exception:
                pass
    todo = [t for t in tasks if os.path.basename(t) not in done]
    print("%d tasks (%d already done)" % (len(todo), len(done)), flush=True)
    for i, rel in enumerate(todo, 1):
        rec = run_task(rel)
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        print("%3d/%d  %-46s reward=%s  (%ss)%s"
              % (i, len(todo), rec["task"][:46], rec["reward"], rec["wall_s"],
                 "  " + rec.get("note", "") if rec.get("note") else ""), flush=True)


if __name__ == "__main__":
    main()

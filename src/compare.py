"""Apply docs/COMPARISON_RULES.md mechanically. No hand-picking."""
import io, json, os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "..", "docs")

ctrl = {}
for l in io.open(os.path.join(DOCS, "control_105.tsv"), encoding="utf-8"):
    p = l.rstrip("\n").split("\t")
    if p[0] == "task" or len(p) < 4 or p[2] in ("?", "None", "", "NO_TRIAL_DIR"):
        continue
    if p[1] == "?":            # off-family probe rows: excluded, stated
        continue
    ctrl[p[0]] = (p[1], float(p[2]))

pg, pg_err = {}, []
for l in io.open(os.path.join(DOCS, "plangraph_results.jsonl"), encoding="utf-8"):
    r = json.loads(l)
    if r.get("reward") is None:
        continue
    if r.get("note", "").startswith(("ingest_error", "graph_restart")):
        pg_err.append((r["task"], r["note"]))
        continue
    pg[r["task"]] = (r["family"], float(r["reward"]))

both = sorted(set(ctrl) & set(pg))
def table(name, rows):
    fam = defaultdict(list)
    for t in rows:
        f, v = rows[t] if isinstance(rows, dict) else t
        fam[f].append(v)
    print("\n== %s ==" % name)
    for f in sorted(fam):
        v = fam[f]
        print("  %-44s n=%-3d mean=%.3f" % (f.split("/")[-1], len(v), sum(v)/len(v)))
    allv = [x for v in fam.values() for x in v]
    if allv:
        print("  %-44s n=%-3d mean=%.3f" % ("OVERALL", len(allv), sum(allv)/len(allv)))

print("head-to-head tasks: %d | control-only: %d | plangraph-only: %d | plangraph errors excluded: %d"
      % (len(both), len(set(ctrl)-set(pg)), len(set(pg)-set(ctrl)), len(pg_err)))
for t, n in pg_err: print("   excluded:", t, "-", n)

table("HEAD-TO-HEAD: control", {t: ctrl[t] for t in both})
table("HEAD-TO-HEAD: plangraph", {t: pg[t] for t in both})
table("PLANGRAPH all graded", pg)

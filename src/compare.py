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


def fam_means(rows):
    fam = defaultdict(list)
    for t, (f, v) in rows.items():
        fam[f].append(v)
    out = {f: (len(v), sum(v) / len(v)) for f, v in fam.items()}
    allv = [x for v in fam.values() for x in v]
    out["OVERALL"] = (len(allv), sum(allv) / len(allv) if allv else 0.0)
    return out


c_h = fam_means({t: ctrl[t] for t in both})
p_h = fam_means({t: pg[t] for t in both})
p_all = fam_means(pg)
FAMS = ["intradrawing/cross-reference-resolution",
        "intradrawing/cross-reference-tracing",
        "intradrawing/sheet-index-consistency",
        "intraproject/spec-drawing-sync"]

lines = []
lines.append("# PlanGraph vs control -- frozen comparison")
lines.append("")
lines.append("Generated mechanically by `src/compare.py` under the pre-committed")
lines.append("rules in `docs/COMPARISON_RULES.md`. Head-to-head on the %d tasks both" % len(both))
lines.append("arms ran; %d control-only; %d PlanGraph-only; %d off-family probe rows excluded."
             % (len(set(ctrl) - set(pg)), len(set(pg) - set(ctrl)), 4))
lines.append("")
lines.append("## Head-to-head (%d tasks)" % len(both))
lines.append("")
lines.append("| Family | Control | PlanGraph |")
lines.append("|---|---|---|")
for f in FAMS:
    cn, cm = c_h.get(f, (0, 0.0))
    pn, pm = p_h.get(f, (0, 0.0))
    if cn == 0 and pn == 0:
        continue
    lines.append("| %s | %.3f (n=%d) | %.3f |" % (f.split("/")[-1], cm, cn, pm))
cn, cm = c_h["OVERALL"]
pn, pm = p_h["OVERALL"]
lines.append("| **overall** | **%.3f** | **%.3f** |" % (cm, pm))
lines.append("")
lines.append("## PlanGraph, all graded tasks")
lines.append("")
lines.append("| Family | n | Score |")
lines.append("|---|---|---|")
for f in FAMS:
    n, m = p_all.get(f, (0, 0.0))
    if n:
        lines.append("| %s | %d | %.3f |" % (f.split("/")[-1], n, m))
n, m = p_all["OVERALL"]
lines.append("| **all** | **%d** | **%.3f** |" % (n, m))
lines.append("")
lines.append("Tracing grader ceiling is 0.416: control reaches %.0f%% of it, PlanGraph %.0f%%."
             % (100 * c_h.get(FAMS[1], (0, 0.0))[1] / 0.416,
                100 * p_h.get(FAMS[1], (0, 0.0))[1] / 0.416))
NL = chr(10)
with io.open(os.path.join(DOCS, "COMPARISON.md"), "w", encoding="utf-8", newline="") as md:
    md.write(NL.join(lines) + NL)
print("wrote docs/COMPARISON.md")

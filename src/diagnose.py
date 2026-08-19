"""Post-hoc diagnosis of resolution misses -> buckets A/B/C.

gt.json is opened HERE ONLY, after grading. Never during answering.
  A extraction miss  - defect text absent from our Callout nodes
  B resolution miss  - node exists, verdict/scoping wrong
  C format miss      - our output contains the finding, grader keywords missed it
"""
import glob, io, json, os, re, sys, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hydra import Hydra
from ingest import build, normalise

BENCH = r"C:/Dev/aec-bench/tasks"
DOCS = os.path.join(HERE, "..", "docs")
RUNS = os.path.join(HERE, "..", "runs")
FAM = "intradrawing/cross-reference-resolution"

def fresh():
    subprocess.run(["docker","restart","hydradb"], capture_output=True, timeout=120)
    import urllib.request
    for _ in range(40):
        try:
            with urllib.request.urlopen("http://127.0.0.1:9090/readyz", timeout=3) as r:
                if r.status==200: return True
        except Exception: pass
        time.sleep(1.5)
    return False

misses=[]
for l in io.open(os.path.join(DOCS,"plangraph_results.jsonl"),encoding="utf-8"):
    r=json.loads(l)
    if r["family"]==FAM and r.get("reward") is not None and r["reward"]<1.0:
        misses.append(r["task"])
print("%d resolution tasks < 1.0" % len(misses))

for task in misses:
    td=os.path.join(BENCH,FAM,task)
    try: gt=json.load(open(os.path.join(td,"gt.json"),encoding="utf-8"))
    except Exception: print("  %s: no gt.json readable" % task); continue
    out=""
    op=os.path.join(RUNS,task,"output.jsonl")
    if os.path.exists(op): out=io.open(op,encoding="utf-8").read().lower()
    fresh(); h=Hydra()
    for root,_,fs in os.walk(os.path.join(td,"environment")):
        for f in fs:
            if f.lower().endswith(".pdf"):
                try: build(os.path.join(root,f),h,verbose=False)
                except Exception: pass
    calls=[normalise((r0.get("raw") or "")).replace(" ","").lower()
           for r0 in h.rows("MATCH (s)-[:REFERENCES]->(c) RETURN c.raw AS raw")]
    for d in gt.get("defects",[]):
        rep=normalise(d.get("replacement_text") or d.get("original_text") or "").replace(" ","").lower()
        kws=[k.lower() for k in d.get("eval_keywords",[])]
        in_graph = any(rep and rep in c for c in calls)
        in_out   = any(k in out for k in kws) if kws else False
        if not in_graph: bucket="A extraction (callout never captured)"
        elif in_out:     bucket="C format (finding present, keywords missed)"
        else:            bucket="B resolution (node exists, verdict/scope wrong)"
        print("  %-40s %-22s -> %s" % (task[:40], (d.get("replacement_text") or "")[:22], bucket))

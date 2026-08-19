"""Parallel census: extract each UNIQUE PDF once across a process pool,
then assemble per-task sums instantly. Resumes from census_196.log.
Output: docs/ingest_report.tsv (same format as ingest_report.py).
"""
from __future__ import annotations

import glob
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_report import BENCH, DOCS, prior_rows, task_pdfs  # noqa: E402
OUT = __import__("os").path.join(DOCS, "ingest_report_fast.tsv")

WORKERS = 6


def one_pdf(pdf):
    from ingest import extract, norm_id
    try:
        pages, _idx, _ip = extract(pdf)
        return (os.path.basename(pdf), os.path.getsize(pdf)), (
            len(pages),
            len({norm_id(p["sheet_no"]) for p in pages if p["sheet_no"]}),
            sum(len(p["callouts"]) for p in pages),
            sum(len(p["details"]) for p in pages)), ""
    except Exception as e:
        return (os.path.basename(pdf), os.path.getsize(pdf)), (0, 0, 0, 0), (
            type(e).__name__ + ": " + str(e)[:80])


def main():
    fams = sorted(
        os.path.relpath(d, BENCH).replace(os.sep, "/")
        for scope in glob.glob(os.path.join(BENCH, "*"))
        for d in glob.glob(os.path.join(scope, "*"))
        if os.path.isdir(d)
    )
    done = prior_rows()
    tasks = []
    for fam in fams:
        for d in sorted(glob.glob(os.path.join(BENCH, fam, "*"))):
            if os.path.isdir(d) and os.path.exists(os.path.join(d, "tests", "test.sh")):
                tasks.append((fam + "/" + os.path.basename(d), d))
    todo = [(t, d) for t, d in tasks if os.path.basename(t) not in done]
    print("%d tasks total | %d resumed | %d to extract" % (len(tasks), len(done), len(todo)), flush=True)

    need = {}
    for t, d in todo:
        for pdf in task_pdfs(d):
            need.setdefault((os.path.basename(pdf), os.path.getsize(pdf)), pdf)
    print("%d unique PDFs across remaining tasks | %d workers" % (len(need), WORKERS), flush=True)

    memo, errs = {}, {}
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(one_pdf, p): k for k, p in need.items()}
        for i, f in enumerate(as_completed(futs), 1):
            key, st, err = f.result()
            memo[key] = st
            if err:
                errs[key] = err
            print("  pdf %3d/%d  %-50s pages=%4d%s"
                  % (i, len(need), key[0][:50], st[0], ("  <-- " + err) if err else ""), flush=True)

    with open(OUT, "a", encoding="utf-8", newline="") as out:
        if os.path.getsize(OUT) == 0 if os.path.exists(OUT) else True:
            out.write("task\tpdfs\tpages\tsheets\tcallouts\tdetails\terror\n")
        written = set()
        if os.path.exists(OUT):
            for l in open(OUT, encoding="utf-8"):
                written.add(l.split("\t")[0])
        n_bad = 0
        for t, d in tasks:
            base = os.path.basename(t)
            if base in done:
                row = (t,) + done[base]
            else:
                pdfs = task_pdfs(d)
                agg = [0, 0, 0, 0]
                err = ""
                for pdf in pdfs:
                    k = (os.path.basename(pdf), os.path.getsize(pdf))
                    st = memo.get(k, (0, 0, 0, 0))
                    for j in range(4):
                        agg[j] += st[j]
                    if k in errs and not err:
                        err = errs[k]
                row = (t, len(pdfs), agg[0], agg[1], agg[2], agg[3], err)
                print("%-70s pdfs=%d pages=%4d sheets=%4d callouts=%5d details=%5d%s"
                      % (base, len(pdfs), agg[0], agg[1], agg[2], agg[3],
                         (" <-- " + err) if err else (" <-- ZERO SHEETS" if agg[1] == 0 else "")), flush=True)
            if t not in written:
                out.write("\t".join(str(x) for x in row) + "\n")
                out.flush()
                written.add(t)
            if row[6] or row[3] == 0:
                n_bad += 1
    print("\nCENSUS COMPLETE: %d tasks | %d need attention" % (len(tasks), n_bad), flush=True)


if __name__ == "__main__":
    main()

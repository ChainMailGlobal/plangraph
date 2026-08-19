"""Ingest pass over every task: extraction counts per task, NO graph writes.

Run FIRST, separately, so a set that fails to extract lands on a readable list
instead of appearing as a silent zero in a results table. Pure PyMuPDF -- no
HydraDB, no network, no LLM. Output: docs/ingest_report.tsv (written
incrementally, resumable).

Many tasks ship COPIES of the same environment (one 89-PDF set backs a dozen
tasks), so per-PDF results are memoised on (filename, size) -- identical
copies extract once.
"""
from __future__ import annotations

import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest import extract, norm_id  # noqa: E402

BENCH = r"C:/Dev/aec-bench/tasks"
DOCS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs")
OUT = os.path.join(DOCS, "ingest_report.tsv")
OLD_LOG = os.path.join(DOCS, "census_196.log")

_memo = {}


def pdf_stats(pdf):
    key = (os.path.basename(pdf), os.path.getsize(pdf))
    if key in _memo:
        return _memo[key]
    pages, _idx, _ip = extract(pdf)
    st = (len(pages),
          len({norm_id(p["sheet_no"]) for p in pages if p["sheet_no"]}),
          sum(len(p["callouts"]) for p in pages),
          sum(len(p["details"]) for p in pages))
    _memo[key] = st
    return st


def task_pdfs(task_dir):
    pdfs = []
    for root, _, fs in os.walk(os.path.join(task_dir, "environment")):
        pdfs += [os.path.join(root, f) for f in fs if f.lower().endswith(".pdf")]
    return sorted(pdfs)


def prior_rows():
    """Recover completed tasks from an interrupted run's log and any TSV."""
    done = {}
    pat = re.compile(r"^(\S+)\s+pdfs=(\d+)\s+pages=\s*(\d+)\s+sheets=\s*(\d+)"
                     r"\s+callouts=\s*(\d+)\s+details=\s*(\d+)(\s+<--\s+(.*))?")
    if os.path.exists(OLD_LOG):
        for l in open(OLD_LOG, encoding="utf-8", errors="replace"):
            m = pat.match(l.strip())
            if m:
                err = (m.group(8) or "").strip()
                if err == "ZERO SHEETS":
                    err = ""
                done[m.group(1)] = tuple(int(m.group(i)) for i in range(2, 7)) + (err,)
    # NOTE: the log is the ONLY resume source -- an ingest_report.tsv from an
    # older extractor version must not masquerade as current-code results.
    return done


def main():
    fams = sys.argv[1:] or sorted(
        os.path.relpath(d, BENCH).replace(os.sep, "/")
        for scope in glob.glob(os.path.join(BENCH, "*"))
        for d in glob.glob(os.path.join(scope, "*"))
        if os.path.isdir(d)
    )
    done = prior_rows()
    print("resuming with %d tasks already recorded" % len(done), flush=True)

    fresh = not os.path.exists(OUT) or os.path.getsize(OUT) == 0
    out = open(OUT, "a", encoding="utf-8", newline="")
    if fresh:
        out.write("task\tpdfs\tpages\tsheets\tcallouts\tdetails\terror\n")
        out.flush()

    written = set()
    if not fresh:
        for l in open(OUT, encoding="utf-8"):
            written.add(l.split("\t")[0])

    n_bad = n_all = 0
    for fam in fams:
        for d in sorted(glob.glob(os.path.join(BENCH, fam, "*"))):
            if not os.path.isdir(d) or not os.path.exists(os.path.join(d, "tests", "test.sh")):
                continue
            task = fam + "/" + os.path.basename(d)
            base = os.path.basename(d)
            n_all += 1
            if base in done:
                row = (task,) + done[base]
            else:
                pdfs = task_pdfs(d)
                np_ = ns = nc = nd = 0
                err = ""
                try:
                    for pdf in pdfs:
                        p_, s_, c_, d_ = pdf_stats(pdf)
                        np_ += p_; ns += s_; nc += c_; nd += d_
                except Exception as e:
                    err = type(e).__name__ + ": " + str(e)[:80]
                row = (task, len(pdfs), np_, ns, nc, nd, err)
                flag = " <-- " + err if err else (" <-- ZERO SHEETS" if ns == 0 else "")
                print("%-70s pdfs=%d pages=%4d sheets=%4d callouts=%5d details=%5d%s"
                      % (base, len(pdfs), np_, ns, nc, nd, flag), flush=True)
            if task not in written:
                out.write("\t".join(str(x) for x in row) + "\n")
                out.flush()
                written.add(task)
            if row[6] or row[3] == 0:
                n_bad += 1

    out.close()
    print("\nCENSUS COMPLETE: %d tasks | %d need attention (error or zero sheets)"
          % (n_all, n_bad), flush=True)


if __name__ == "__main__":
    main()

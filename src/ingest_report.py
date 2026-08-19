"""Ingest pass over every task: extraction counts per task, NO graph writes.

Run FIRST, separately, so a set that fails to extract lands on a readable list
instead of appearing as a silent zero in a results table. Pure PyMuPDF — no
HydraDB, no network, no LLM. Output: docs/ingest_report.tsv.
"""
from __future__ import annotations

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest import extract, norm_id  # noqa: E402

BENCH = r"C:/Dev/aec-bench/tasks"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "ingest_report.tsv")


def task_pdfs(task_dir):
    pdfs = []
    for root, _, fs in os.walk(os.path.join(task_dir, "environment")):
        pdfs += [os.path.join(root, f) for f in fs if f.lower().endswith(".pdf")]
    return sorted(pdfs)


def main():
    # ALL families — the census covers the full 196. Extraction is free, and a
    # set that fails to parse should be on this list no matter which family
    # its graders belong to.
    fams = sys.argv[1:] or sorted(
        os.path.relpath(d, BENCH).replace(os.sep, "/")
        for scope in glob.glob(os.path.join(BENCH, "*"))
        for d in glob.glob(os.path.join(scope, "*"))
        if os.path.isdir(d)
    )
    rows = []
    for fam in fams:
        for d in sorted(glob.glob(os.path.join(BENCH, fam, "*"))):
            if not os.path.isdir(d) or not os.path.exists(os.path.join(d, "tests", "test.sh")):
                continue
            task = fam + "/" + os.path.basename(d)
            pdfs = task_pdfs(d)
            n_pages = n_sheets = n_callouts = n_details = 0
            err = ""
            try:
                for pdf in pdfs:
                    pages = extract(pdf)
                    n_pages += len(pages)
                    sheets = {norm_id(p["sheet_no"]) for p in pages if p["sheet_no"]}
                    n_sheets += len(sheets)
                    n_callouts += sum(len(p["callouts"]) for p in pages)
                    n_details += sum(len(p["details"]) for p in pages)
            except Exception as e:
                err = type(e).__name__ + ": " + str(e)[:80]
            rows.append((task, len(pdfs), n_pages, n_sheets, n_callouts, n_details, err))
            flag = " <-- " + err if err else (" <-- ZERO SHEETS" if n_sheets == 0 else "")
            print("%-70s pdfs=%d pages=%3d sheets=%3d callouts=%4d details=%3d%s"
                  % (os.path.basename(task), len(pdfs), n_pages, n_sheets,
                     n_callouts, n_details, flag), flush=True)

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        f.write("task\tpdfs\tpages\tsheets\tcallouts\tdetails\terror\n")
        for r in rows:
            f.write("\t".join(str(x) for x in r) + "\n")

    bad = [r for r in rows if r[6] or r[3] == 0]
    print("\n%d tasks | %d need attention (error or zero sheets)" % (len(rows), len(bad)))
    for r in bad:
        print("  ", r[0], "-", r[6] or "zero sheets extracted")


if __name__ == "__main__":
    main()

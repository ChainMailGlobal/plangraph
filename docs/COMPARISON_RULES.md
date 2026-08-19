# Comparison rules — written BEFORE the PlanGraph results were seen

Timestamp: 2026-08-18, PlanGraph as-is run in flight, zero results read.

## 1. The head-to-head set (the intersection rule)

Head-to-head = tasks where BOTH arms produced a graded answer:
  { control rows with a numeric reward }  INTERSECT  { plangraph rows with a
    numeric reward and note != not_attempted / ingest_error / restart_failed }

- The 4 off-family probe rows in the control TSV are excluded (stated).
- A PlanGraph ingest_error does NOT drop the task silently: it is reported in
  the PlanGraph-only table as a 0 with its error, and excluded from
  head-to-head with the exclusion counted and printed.
- Everything else PlanGraph graded is reported in the PlanGraph-only table.
- NO other filter of any kind. The intersection is computed by this rule,
  by script (`src/compare.py`), not by hand.

## 2. Resolution-miss diagnostic buckets (for the failure list)

Every resolution task scoring < 1.0 is classified POST-HOC (gt.json is opened
only here, after grading — never during answering) into:

  A. EXTRACTION MISS — the defect's callout text does not exist as a Callout
     node in our graph (the grammar/span layer never captured it).
     -> span-merge or grammar work could help. This is the ONLY bucket that
        justifies the extraction fix.
  B. RESOLUTION MISS — the callout node exists but our verdict disagrees with
     gt (wrong resolved flag, wrong verdict kind, or scoped to the wrong page).
     -> graph/logic work, not extraction.
  C. FORMAT MISS — our output.jsonl contains the finding but the grader's
     keywords don't match our phrasing.
     -> answer-formatting work; looks identical to A/B in the score alone.

## 3. Uniform-zero guard

If ANY family is ~0 across the board, the FIRST hypothesis is output format
(bucket C), not capability: a correct finding phrased wrong scores zero and is
indistinguishable from total failure in the aggregate. Check 3 sample tasks'
output.jsonl against their graders' grep patterns before touching extraction.

## 4. Spec-sync honesty clause

Spec-sync is pre-registered to LOSE, and the premise behind that prediction
(perception-bound) was RETRACTED before the run. If spec-sync WINS anyway,
that is a hit to our stated model and is reported as one — not reframed as a
bonus finding.

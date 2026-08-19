# PlanGraph vs control -- frozen comparison

Generated mechanically by `src/compare.py` under the pre-committed
rules in `docs/COMPARISON_RULES.md`. Head-to-head on the 57 tasks both
arms ran; 0 control-only; 48 PlanGraph-only; 4 off-family probe rows excluded.

## Head-to-head (57 tasks)

| Family | Control | PlanGraph |
|---|---|---|
| cross-reference-resolution | 0.761 (n=23) | 0.565 |
| cross-reference-tracing | 0.236 (n=16) | 0.219 |
| sheet-index-consistency | 0.875 (n=4) | 0.917 |
| spec-drawing-sync | 0.429 (n=14) | 0.214 |
| **overall** | **0.540** | **0.407** |

## PlanGraph, all graded tasks

| Family | n | Score |
|---|---|---|
| cross-reference-resolution | 51 | 0.670 |
| cross-reference-tracing | 24 | 0.348 |
| sheet-index-consistency | 14 | 0.698 |
| spec-drawing-sync | 16 | 0.250 |
| **all** | **105** | **0.536** |

Tracing grader ceiling is 0.416: control reaches 57% of it, PlanGraph 53%.

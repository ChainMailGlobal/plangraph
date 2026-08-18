#!/usr/bin/env bash
# Control arm: the benchmark's PUBLISHED agent config on the 105 graph-shaped tasks.
# Resumable, per-task logged, hard spend ceiling.
set -uo pipefail

cd /c/Dev/aec-bench
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="C:/Dev/aec-bench"
export ANTHROPIC_API_KEY=$(grep -m1 '^ANTHROPIC_API_KEY=' .env | cut -d= -f2- | tr -d '\r\n"'"'"' ')

OUT=/c/Dev/plangraph/docs/control_105.tsv
LOG=/c/Dev/plangraph/docs/control_105.log
CEILING=75.00                       # hard stop; budget is $83.63

[ -f "$OUT" ] || printf "task\tfamily\treward\tcost_usd\twall_s\tturns\n" > "$OUT"

# resume: tasks already recorded
done_list=$(cut -f1 "$OUT" | tail -n +2)

spent=$(awk -F'\t' 'NR>1 {s+=$4} END {printf "%.4f", s+0}' "$OUT")
echo "resuming: $(echo "$done_list" | grep -c . ) done, \$${spent} spent" | tee -a "$LOG"

mapfile -t TASKS < <(tr -d '\r' < /c/Dev/vis4d-archive/bench_local/graph_families.txt)

for T in "${TASKS[@]}"; do
  [ -z "$T" ] && continue
  name=$(basename "$T")
  if echo "$done_list" | grep -qx "$name"; then continue; fi

  # spend ceiling check BEFORE each task
  spent=$(awk -F'\t' 'NR>1 {s+=$4} END {printf "%.4f", s+0}' "$OUT")
  over=$(awk -v a="$spent" -v b="$CEILING" 'BEGIN{print (a>=b)?1:0}')
  if [ "$over" -eq 1 ]; then
    echo "STOP: spend ceiling reached (\$${spent} >= \$${CEILING})" | tee -a "$LOG"
    break
  fi

  before=$(ls trials 2>/dev/null | wc -l)
  start=$(date +%s)
  MSYS_NO_PATHCONV=1 timeout 2400 harbor trials start -p "tasks/$T" \
    --agent aec_bench.agents.claude_agent:ClaudeAgent \
    -m anthropic/claude-sonnet-4-6 </dev/null >>"$LOG" 2>&1
  wall=$(( $(date +%s) - start ))
  after=$(ls trials 2>/dev/null | wc -l)

  if [ "$after" -le "$before" ]; then
    printf "%s\t%s\tNO_TRIAL_DIR\t0\t%s\t0\n" "$name" "$(dirname "$T")" "$wall" >> "$OUT"
    echo "  FAILED $name (no trial dir, ${wall}s)" | tee -a "$LOG"
    continue
  fi

  python /c/Dev/plangraph/src/record_trial.py "$T" "$(ls -t trials | head -1)" "$wall" "$OUT"
done

echo "CONTROL ARM DONE. spent=\$$(awk -F'\t' 'NR>1 {s+=$4} END {printf \"%.2f\", s+0}' "$OUT")" | tee -a "$LOG"

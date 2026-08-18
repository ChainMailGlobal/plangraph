#!/usr/bin/env bash
cd /c/Dev/aec-bench
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="C:/Dev/aec-bench"
export ANTHROPIC_API_KEY=$(grep -m1 '^ANTHROPIC_API_KEY=' .env | cut -d= -f2- | tr -d '\r\n"'"'"' ')
OUT=/c/Dev/plangraph/docs/probe_results.tsv
printf "task\tdifficulty\treward\tcost_usd\twall_s\tturns\n" > "$OUT"
mapfile -t TASKS < <(tr -d "" < /c/Dev/plangraph/docs/probe_sample.txt)
for i in "${!TASKS[@]}"; do
  T="${TASKS[$i]}"; [ -z "$T" ] && continue
  [ "$i" -eq 0 ] && continue; [ "$i" -eq 4 ] && continue
  before=$(ls trials | wc -l)
  start=$(date +%s)
  MSYS_NO_PATHCONV=1 timeout 2400 harbor trials start -p "tasks/$T" \
    --agent aec_bench.agents.claude_agent:ClaudeAgent \
    -m anthropic/claude-sonnet-4-6 </dev/null >>/c/Dev/plangraph/docs/probe_run.log 2>&1
  wall=$(( $(date +%s) - start ))
  after=$(ls trials | wc -l)
  if [ "$after" -le "$before" ]; then
    printf "%s\t?\tNO_TRIAL_DIR\t0\t%s\t0\n" "$(basename "$T")" "$wall" >> "$OUT"
    echo "  FAILED (no new trial dir): $T"; continue
  fi
  python - "$T" "$(ls -t trials | head -1)" "$wall" "$OUT" <<'PY'
import json,sys,os,re
T,d,wall,out=sys.argv[1:5]
base=os.path.join("trials",d); cost=0.0; turns=0
try:
    for line in open(os.path.join(base,"agent","claude-code.txt"),encoding='utf-8',errors='replace'):
        if line.lstrip().startswith('{'):
            try: o=json.loads(line)
            except: continue
            if o.get('type')=='result':
                cost=o.get('total_cost_usd') or 0; turns=o.get('num_turns') or 0
except Exception: pass
try: rw=json.load(open(os.path.join(base,"verifier","reward.json")))['reward']
except Exception: rw='?'
tt=os.path.join("tasks",T,"task.toml"); diff='?'
if os.path.exists(tt):
    m=re.search(r'difficulty\s*=\s*"(\w+)"',open(tt,encoding='utf-8',errors='replace').read())
    diff=m.group(1) if m else '?'
open(out,'a').write(f"{os.path.basename(T)}\t{diff}\t{rw}\t{cost:.4f}\t{wall}\t{turns}\n")
print(f"  {os.path.basename(T)}: reward={rw} cost=${cost:.4f} wall={wall}s turns={turns}")
PY
done
echo "PROBE COMPLETE"

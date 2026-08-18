"""Record one Harbor trial's outcome into the control-arm TSV.

Cost comes from the Claude CLI's own `total_cost_usd` in its result event —
Harbor's agent_result.cost_usd is null, and the raw token counts are ambiguous
between cache writes (1.25x) and cache reads (0.1x), a 12x pricing swing.
"""
from __future__ import annotations

import json
import os
import sys

task, trial_dir, wall, out = sys.argv[1:5]
base = os.path.join("trials", trial_dir)

cost = 0.0
turns = 0
try:
    with open(os.path.join(base, "agent", "claude-code.txt"), encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.lstrip().startswith("{"):
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("type") == "result":
                cost = o.get("total_cost_usd") or 0.0
                turns = o.get("num_turns") or 0
except Exception:
    pass

try:
    with open(os.path.join(base, "verifier", "reward.json"), encoding="utf-8") as f:
        reward = json.load(f)["reward"]
except Exception:
    reward = "?"

name = os.path.basename(task)
family = os.path.dirname(task)
with open(out, "a", encoding="utf-8") as f:
    f.write("%s\t%s\t%s\t%.4f\t%s\t%s\n" % (name, family, reward, cost, wall, turns))

print("  %s: reward=%s cost=$%.4f wall=%ss turns=%s" % (name, reward, cost, wall, turns))

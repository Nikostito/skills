"""Summarize the saved runs: python3 summary.py results/ prints, for each case and arm, the defects found,
mean pairwise overlap, wall-clock minutes, and cost. A run counts only when its final message holds ## Defects."""
import json, itertools, sys
from pathlib import Path
E = Path(sys.argv[1])
runs = {}
for arm in ("main", "sweep"):
    for path in sorted(E.glob(f"out*-{arm}.json")):
        for r in json.load(open(path)):
            ok = "## Defects" in (r.get("final") or "") and "hit your" not in (r.get("final") or "")
            if ok:
                runs.setdefault((r["case"], arm), []).append(r)
for case in sorted({c for c, _ in runs}):
    print(case)
    for arm in ("main", "sweep"):
        R = runs.get((case, arm), [])
        if not R: print(f"  {arm:6} no complete runs"); continue
        S = [{n for n, g in r["graders"].items() if g["passed"] and n != "defects-section"} for r in R]
        G = [n for n in R[0]["graders"] if n != "defects-section"]
        pairs = [len(a & b) / len(a | b) for a, b in itertools.combinations(S, 2) if a | b]
        ov = f"{sum(pairs)/len(pairs):.2f}" if pairs else "n/a"
        print(f"  {arm:6} runs {len(R)}  found {[len(s) for s in S]} of {len(G)}  mean {sum(map(len,S))/len(S):.1f}"
              f"  overlap {ov}  union {len(set.union(*S))}  wall min {[round(r['wall_seconds']/60) for r in R]}"
              f"  cost/run ${sum(r['total_cost_usd'] for r in R)/len(R):.2f}")

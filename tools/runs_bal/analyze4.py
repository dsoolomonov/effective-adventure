import json, pathlib
from collections import defaultdict
D = pathlib.Path("/home/ubuntu/runs_bal/data")
def load(s):
    return [(r["p"], float(r["v"])) for r in json.loads((D/f"{s}.json").read_text()) if r["v"] not in (None,"")]

def last4(s, y=2026):
    rows = [(p, v) for p, v in load(s) if p.startswith(str(y))]
    return sum(v for _, v in rows[-4:]) / 4

for s, nm in [("WGFUPUS2","gas demand"),("W_EPM0F_EEX_NUS-Z00_MBBLD","gas exports"),
              ("WGTIMUS2","gas imports"),("WDIEXUS2","dis exports"),("WDIUPUS2","dis demand"),
              ("W_EPM0F_YPR_NUS_MBBLD","gas prod"),("WDIRPUS2","dis prod"),
              ("WCRRIP22","P2 runs"),("WCRRIP32","P3 runs"),("WCRRIUS2","US runs")]:
    rows = load(s)
    cur = sum(v for _, v in rows[-4:]) / 4
    # same 4 weeks last year
    prev = [v for p, v in rows if p.startswith("2025-08") or p.startswith("2025-07-2")][-4:]
    print(f"{nm:12} last4 {cur:7.0f}  same-period-2025 {sum(prev)/len(prev):7.0f}  y/y {cur-sum(prev)/len(prev):+7.0f}")

print("\nrecord checks")
for s, nm in [("W_EPM0F_YPR_NUS_MBBLD","US gasoline prod"),("WDIRPUS2","US disty prod"),
              ("WDIEXUS2","US disty exports"),("W_EPM0F_EEX_NUS-Z00_MBBLD","US gasoline exports")]:
    rows = load(s)
    mx = max(rows, key=lambda r: r[1])
    print(f"{nm:20} max since 2014: {mx[1]:6.0f} ({mx[0]}) | latest {rows[-1][1]:6.0f} ({rows[-1][0]})")

# P2+P3 october record
p2 = defaultdict(list); p3 = defaultdict(list)
for p, v in load("WCRRIP22"): p2[p[:7]].append(v)
for p, v in load("WCRRIP32"): p3[p[:7]].append(v)
oct_ = {k: sum(p2[k])/len(p2[k]) + sum(p3[k])/len(p3[k]) for k in p2 if k.endswith("-10")}
print("\nP2+P3 October runs, best 5:", sorted(oct_.items(), key=lambda x: -x[1])[:5])
sep = {k: sum(p2[k])/len(p2[k]) + sum(p3[k])/len(p3[k]) for k in p2 if k.endswith("-09")}
print("P2+P3 September runs, best 5:", sorted(sep.items(), key=lambda x: -x[1])[:5])

cap = 4283 + 9888
for label, idle in [("user profile Sep", 433+350), ("user profile Oct", 336+350),
                    ("half-wedge Oct", 336+350+500), ("normal-wedge Oct", 336+350+1010)]:
    r = cap - idle
    print(f"{label:20} idle {idle:5.0f} -> runs {r:6.0f}  util {100*r/cap:5.1f}%")

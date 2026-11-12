import json, pathlib
from collections import defaultdict

D = pathlib.Path("/home/ubuntu/runs_bal/data")
def load(s):
    return [(r["p"], float(r["v"])) for r in json.loads((D/f"{s}.json").read_text()) if r["v"] not in (None,"")]

cu = dict(load("W_EPC0_SAX_YCUOK_MBBL")); p2c = dict(load("WCESTP21"))
usc = dict(load("WCESTUS1")); p3c = dict(load("WCESTP31"))
ex = dict(load("WCREXUS2")); im = dict(load("WCRIMUS2"))
print("=== mid-Aug crude picture (mb / kbd) ===")
for y in range(2019, 2027):
    c = [p for p in cu if p.startswith(f"{y}-08") and 10 <= int(p[-2:]) <= 18]
    if not c: continue
    p = c[0]
    print(f"{p}: US(ex-SPR) {usc[p]/1000:6.1f}  Cushing {cu[p]/1000:5.1f}  P2 {p2c[p]/1000:6.1f}  "
          f"P3 {p3c[p]/1000:6.1f} | imports {im[p]:5.0f} exports {ex[p]:5.0f}")

print("\n=== last 10 weeks: crude stocks, Cushing, distillate stocks, gasoline stocks ===")
ds = dict(load("WDISTUS1")); gs = dict(load("WGTSTUS1"))
d2 = dict(load("WDISTP21")); d3 = dict(load("WDISTP31"))
per = sorted(usc)[-10:]
for p in per:
    print(f"{p}: crude {usc[p]/1000:6.1f} cush {cu[p]/1000:5.1f} | gas {gs[p]/1000:6.1f} | "
          f"dis {ds[p]/1000:6.1f} (P2 {d2[p]/1000:5.1f} P3 {d3[p]/1000:5.1f})")

print("\n=== 5-yr (2021-25) avg mid-Aug & end-Oct stock levels, mb ===")
def pick(dic, y, mo, lo, hi):
    c = [p for p in dic if p.startswith(f"{y}-{mo:02d}") and lo <= int(p[-2:]) <= hi]
    return dic[c[0]] if c else None
for nm, dic in (("gasoline", gs), ("distillate", ds), ("crude", usc)):
    aug = [pick(dic, y, 8, 10, 18) for y in range(2021, 2026)]
    octe = [pick(dic, y, 10, 25, 31) for y in range(2021, 2026)]
    aug = [x for x in aug if x]; octe = [x for x in octe if x]
    cur = pick(dic, 2026, 8, 10, 18)
    print(f"{nm:11}: mid-Aug 5yr {sum(aug)/len(aug)/1000:6.1f}  now {cur/1000:6.1f} "
          f"({(cur-sum(aug)/len(aug))/1000:+5.1f}) | end-Oct 5yr {sum(octe)/len(octe)/1000:6.1f}")
    print(f"             end-Oct by yr: " + " ".join(f"{x/1000:.1f}" for x in octe))

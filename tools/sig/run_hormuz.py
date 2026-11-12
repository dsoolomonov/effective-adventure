import re, os, sys, time, json
src = open(os.path.expanduser("~/sig/q.py")).read()
cs = re.search(r'cs = \((.*?)\)\n', src, re.S).group(1)
cs = "".join(re.findall(r'"([^"]*)"', cs))
kv = dict(p.split("=", 1) for p in cs.split(";") if "=" in p)
os.environ["SIGNAL_SQL_SERVER"] = kv["SERVER"]; os.environ["SIGNAL_SQL_USERNAME"] = kv["UID"]; os.environ["SIGNAL_SQL_PASSWORD"] = kv["PWD"].strip("{}")
if kv.get("DATABASE"): os.environ["SIGNAL_SQL_DATABASE"] = kv["DATABASE"]
sys.path.insert(0, os.path.expanduser("~/crude-oil-analytics"))
from app.main import _signal_hormuz
t = time.time()
out = _signal_hormuz(int(sys.argv[1]) if len(sys.argv) > 1 else 270)
print("secs", round(time.time() - t, 1))
json.dump(out, open(os.path.expanduser("~/sig/hormuz_out.json"), "w"))
print(json.dumps({k: v for k, v in out.items() if k in ("days", "start", "end", "kpi", "rows", "dark_transits_total", "dest_90d_mb")}, indent=1))
print("dark sample", json.dumps(out["dark_transits"][:5], indent=1))

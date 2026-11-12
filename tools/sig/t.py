import time, json, sys
sys.path.insert(0,'/home/ubuntu/crude-oil-analytics')
from app import main as m
for name, fn in [("fleet", m._signal_fleet)]:
    t=time.time()
    try:
        r=fn()
        s=json.dumps(r, default=str)
        print(name, f"{time.time()-t:.1f}s", len(s)//1024, "KB", flush=True)
        if name=="fleet":
            print(" count", r["count"], "as_of", r["as_of"]); print(" ", r["vessels"][0]); print(" ", r["by_status"]); print(" ", r["by_region"][:5])
        if name=="flows":
            print(" weeks", len(r["weeks"]), r["weeks"][-1], "total last3", r["total_bbl"][-3:]); print(" src", list(r["by_source"].keys())); print(" matrix", len(r["matrix_90d"]), r["matrix_90d"][:2]); print(" cargo", r["cargo_90d"][:5]); print(" on_water", r["on_water"][:4], r["on_water_by_class"])
        if name=="tonnage":
            print(" as_of", r["as_of"], "ports", len(r["ports"])); p=r["ports"][0]; print(" ", p["port"], p["total"], p["prompt_available"], p["by_class_bucket"], p["by_ops"]); print(" hist", len(r["history_dates"]), list(r["history"].keys())[:3])
    except Exception as e:
        import traceback; traceback.print_exc()

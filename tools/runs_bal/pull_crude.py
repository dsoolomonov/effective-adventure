import os, json, requests, pathlib

K = os.environ["EIA"]
OUT = pathlib.Path("/home/ubuntu/runs_bal/data")

GROUPS = {
    "petroleum/stoc/wstk": ["WCESTUS1", "WCESTP21", "WCESTP31", "W_EPC0_SAX_YCUOK_MBBL"],
    "petroleum/move/wkly": ["WCRIMUS2", "WCREXUS2", "WCRIMP22", "WCRIMP32"],
    "petroleum/sup/wkly": ["WCRFPUS2"],
}
for route, series in GROUPS.items():
    params = {"api_key": K, "frequency": "weekly", "data[0]": "value",
              "start": "2014-01-01", "length": 5000,
              "sort[0][column]": "period", "sort[0][direction]": "asc"}
    for i, s in enumerate(series):
        params[f"facets[series][{i}]"] = s
    j = requests.get(f"https://api.eia.gov/v2/{route}/data", params=params, timeout=300).json()
    rows = j.get("response", {}).get("data")
    if rows is None:
        print("ERR", route, str(j)[:200]); continue
    got = {}
    for d in rows:
        got.setdefault(d["series"], []).append({"p": d["period"], "v": d["value"]})
    for s, r in got.items():
        (OUT / f"{s}.json").write_text(json.dumps(r))
        print("ok", s, len(r), r[-1]["p"], r[-1]["v"])
    print("MISSING", set(series) - set(got))

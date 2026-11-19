import os, json, requests, pathlib

K = os.environ["EIA"]
OUT = pathlib.Path("/home/ubuntu/runs_bal/data")
OUT.mkdir(parents=True, exist_ok=True)

GROUPS = {
    "petroleum/pnp/wiup": ["WCRRIP22", "WCRRIP32", "WCRRIUS2",
                           "W_NA_YUP_R20_PER", "W_NA_YUP_R30_PER", "WPULEUS3",
                           "W_NA_YRL_R20_MBBLD", "W_NA_YRL_R30_MBBLD", "WOCLEUS2",
                           "WGIRIP22", "WGIRIP32", "WGIRIUS2"],
    "petroleum/pnp/wprodrb": ["WGFRPP22", "WGFRPP32", "W_EPM0F_YPR_NUS_MBBLD", "WGFRPUS2",
                              "WDIRPP22", "WDIRPP32", "WDIRPUS2"],
    "petroleum/stoc/wstk": ["WGTSTP21", "WGTSTP31", "WGTSTUS1",
                            "WDISTP21", "WDISTP31", "WDISTUS1"],
    "petroleum/cons/wpsup": ["WGFUPUS2", "WDIUPUS2"],
    "petroleum/move/wkly": ["WGTEXUS2", "WDIEXUS2", "WGTIMUS2", "WDIIMUS2",
                            "W_EPM0F_EEX_NUS-Z00_MBBLD"],
}

for route, series in GROUPS.items():
    params = {"api_key": K, "frequency": "weekly", "data[0]": "value",
              "start": "2014-01-01", "length": 5000,
              "sort[0][column]": "period", "sort[0][direction]": "asc"}
    for i, s in enumerate(series):
        params[f"facets[series][{i}]"] = s
    got = {}
    offset = 0
    while True:
        params["offset"] = offset
        j = requests.get(f"https://api.eia.gov/v2/{route}/data", params=params, timeout=300).json()
        rows = j.get("response", {}).get("data")
        if rows is None:
            print("ERR", route, str(j)[:300]); break
        for d in rows:
            got.setdefault(d["series"], []).append({"p": d["period"], "v": d["value"]})
        if len(rows) < 5000:
            break
        offset += 5000
    for s, rows in got.items():
        (OUT / f"{s}.json").write_text(json.dumps(rows))
        print("ok", s, len(rows), rows[0]["p"], "->", rows[-1]["p"], rows[-1]["v"])
    missing = set(series) - set(got)
    if missing:
        print("MISSING", route, missing)

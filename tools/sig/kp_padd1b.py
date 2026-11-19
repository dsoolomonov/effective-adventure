import os, pandas as pd, requests
from datetime import date, timedelta
for line in open('/home/ubuntu/barrel-terminal-bundle/FILLED.env'):
    if '=' in line and not line.startswith('#'):
        k, v = line.strip().split('=', 1); os.environ.setdefault(k, v.strip().strip('"'))
from kpler.sdk.configuration import Configuration
from kpler.sdk import Platform
from kpler.sdk.resources.trades import Trades
cfg = Configuration(Platform.Liquids, os.environ['KPLER_USERNAME'], os.environ['KPLER_PASSWORD'])
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 40); pd.set_option('display.max_rows', 300)
tr = Trades(cfg)
cols = ["vessel_name","closest_ancestor_product","closest_ancestor_grade","start","end","origin_location_name","destination_location_name","cargo_origin_barrels_split_by_product","initial_seller_name","final_buyer_name","status"]
for fv in (True, False):
    try:
        df = tr.get(from_zones=["Europe"], to_zones=["PADD 1"], start_date=date(2026,8,20), end_date=date(2026,10,1), with_forecast=True, with_intra_country=False, columns=cols, size=500, with_freight_view=fv)
        print(f"\n=== freight_view={fv}: {len(df)} rows; products:", df['closest_ancestor_product'].value_counts().to_dict() if len(df) else None)
        if len(df): print(df.head(40).to_string())
    except Exception as e:
        print(f"freight_view={fv} ERR", e)

# EIA weekly PADD1 imports: finished motor gasoline + blending components
key = os.environ['EIA_API_KEY']
def eia(series_ids):
    r = requests.get("https://api.eia.gov/v2/petroleum/move/wkly/data/", params={"api_key": key, "frequency":"weekly", "data[0]":"value", "facets[series][]": series_ids, "sort[0][column]":"period","sort[0][direction]":"desc","length":80}, timeout=60)
    j = r.json(); d = pd.DataFrame(j.get('response',{}).get('data',[]))
    return d
d = eia(["W_EPM0F_IM0_R10-Z00_MBBLD","WBCIM_R10-Z00_2","WGTIM_R10-Z00_2","W_EPOBGRR_IM0_R10-Z00_MBBLD"])
if len(d):
    p = d.pivot_table(index='period', columns='series-description', values='value', aggfunc='first').sort_index(ascending=False)
    print("\n=== EIA weekly PADD1 imports (kb/d)"); print(p.head(16).to_string())
else:
    print("EIA empty", d)

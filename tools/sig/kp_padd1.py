import os, sys, pandas as pd
from datetime import date, timedelta
for line in open('/home/ubuntu/barrel-terminal-bundle/FILLED.env'):
    if line.startswith('KPLER_'):
        k, v = line.strip().split('=', 1); os.environ[k] = v.strip().strip('"')
from kpler.sdk.configuration import Configuration
from kpler.sdk import Platform, FlowsDirection, FlowsMeasurementUnit, FlowsPeriod, FlowsSplit
from kpler.sdk.resources.trades import Trades
from kpler.sdk.resources.flows import Flows
cfg = Configuration(Platform.Liquids, os.environ['KPLER_USERNAME'], os.environ['KPLER_PASSWORD'])
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 40); pd.set_option('display.max_rows', 300)
tr = Trades(cfg)
cols = ["vessel_name","vessel_type","closest_ancestor_product","closest_ancestor_grade","start","end","origin_location_name","origin_country_name","destination_location_name","destination_country_name","cargo_origin_kb","cargo_destination_kb","seller","buyer","status","charterer"]
today = date(2026, 9, 17)
# this week Monday
mon = today - timedelta(days=today.weekday())
prods = ["Gasoline", "Gasoline blending components", "Naphtha", "Alkylate", "Reformate", "MTBE", "Blending Components"]
def pull(products, label, **kw):
    try:
        df = tr.get(from_zones=["Europe"], to_zones=["PADD 1"], products=products, with_forecast=True, with_intra_country=False, columns=cols, size=2000, **kw)
        print(f"\n=== {label}: {len(df)} rows"); return df
    except Exception as e:
        print(f"\n=== {label} ERR {e}"); return pd.DataFrame()
# departures last 3 weeks (in transit + this week) and arrivals this week
d1 = pull(["Gasoline", "Gasoline blending components", "Blending Components"], "Gasoline+blend, departures since 1 Aug", start_date=date(2026,8,1), end_date=today+timedelta(days=14))
if len(d1):
    d1['start']=pd.to_datetime(d1['start']); d1['end']=pd.to_datetime(d1['end'])
    d1.to_csv('/home/ubuntu/sig/kp_padd1_trades.csv', index=False)
    print(d1.sort_values('start')[["vessel_name","closest_ancestor_product","closest_ancestor_grade","start","end","origin_location_name","destination_location_name","cargo_origin_kb","seller","buyer","status"]].to_string())
    print("\nProducts present:", d1['closest_ancestor_product'].value_counts().to_dict())
# Naphtha separately
d2 = pull(["Naphtha"], "Naphtha departures since 1 Aug", start_date=date(2026,8,1), end_date=today+timedelta(days=14))
if len(d2):
    d2['start']=pd.to_datetime(d2['start']); d2['end']=pd.to_datetime(d2['end'])
    d2.to_csv('/home/ubuntu/sig/kp_padd1_naph.csv', index=False)
    print(d2.sort_values('start')[["vessel_name","closest_ancestor_grade","start","end","origin_location_name","destination_location_name","cargo_origin_kb","seller","buyer","status"]].to_string())
# weekly flows Europe -> PADD1 gasoline, split by products, last 12 weeks
fl = Flows(cfg)
try:
    f = fl.get(flow_direction=[FlowsDirection.Import], split=[FlowsSplit.Products], granularity=[FlowsPeriod.EiaWeekly], unit=[FlowsMeasurementUnit.KBD],
               from_zones=["Europe"], to_zones=["PADD 1"], products=["Gasoline","Naphtha","Blending Components"], start_date=date(2026,6,1), end_date=date(2026,10,15), with_forecast=True, with_intra_country=False)
    print("\n=== Weekly flows Europe->PADD1 kbd by product"); print(f.to_string())
except Exception as e:
    print("flows ERR", e)
try:
    f2 = fl.get(flow_direction=[FlowsDirection.Import], split=[FlowsSplit.OriginCountries], granularity=[FlowsPeriod.EiaWeekly], unit=[FlowsMeasurementUnit.KBD],
               from_zones=["Europe"], to_zones=["PADD 1"], products=["Gasoline"], start_date=date(2026,7,1), end_date=date(2026,10,15), with_forecast=True, with_intra_country=False)
    print("\n=== Weekly gasoline Europe->PADD1 by origin country kbd"); print(f2.to_string())
except Exception as e:
    print("flows2 ERR", e)

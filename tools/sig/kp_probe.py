import os, pandas as pd
for line in open('/home/ubuntu/barrel-terminal-bundle/FILLED.env'):
    if line.startswith('KPLER_'):
        k, v = line.strip().split('=', 1); os.environ[k] = v.strip().strip('"')
from kpler.sdk.configuration import Configuration
from kpler.sdk import Platform
from kpler.sdk.resources.trades import Trades
from kpler.sdk.resources.products import Products
cfg = Configuration(Platform.Liquids, os.environ['KPLER_USERNAME'], os.environ['KPLER_PASSWORD'])
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 400); pd.set_option('display.max_colwidth', 60)
c = Trades(cfg).get_columns()
print(c[['id','name']].to_string())
p = Products(cfg).get()
print(p.to_string())

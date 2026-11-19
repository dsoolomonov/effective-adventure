from q import cur
import json, datetime
sql = """SELECT VesselName, VesselClass, FixtureDate, FixtureStatus, FixtureIsCOA, LaycanFrom, LaycanTo, Charterer, Rate, RateType,
 Quantity, QuantityUnit, QuantityInBarrels, FirstLoadPortName, FirstLoadPortCountryName, FirstLoadPortLevel0AreaName,
 LastDischargePortName, LastDischargePortCountryName, LastDischargePortLevel0AreaName, CargoGroup, CargoType, Horizon
FROM dbo.uvS_VoyagesSummary WHERE FixtureDate >= '2026-10-19'"""
cur.execute(sql)
n=[d[0] for d in cur.description]
rows=[{k:(v.isoformat() if isinstance(v,(datetime.datetime,datetime.date)) else (float(v) if hasattr(v,'as_tuple') else v)) for k,v in zip(n,r)} for r in cur.fetchall()]
json.dump(rows,open('fx19.json','w'))
print(len(rows), max(r['FixtureDate'] for r in rows))

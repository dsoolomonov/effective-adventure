from q import cur
import datetime
cur.execute("""SELECT VesselName, VesselClass, FixtureDate, FixtureStatus, FixtureIsCOA, LaycanFrom, LaycanTo, Charterer, Rate, RateType,
 QuantityInBarrels, Quantity, FirstLoadPortName, FirstLoadPortLevel0AreaName, LastDischargePortName, LastDischargePortLevel0AreaName, CargoGroup, CargoType
FROM dbo.uvS_VoyagesSummary WHERE FixtureDate >= '2026-10-18' ORDER BY FixtureDate""")
for r in cur.fetchall():
    print(' | '.join('' if v is None else (v.strftime('%m-%d %H:%M') if isinstance(v,datetime.datetime) else str(v)) for v in r))

import time
from qq import q
t=time.time()
q("""WITH v AS (SELECT DISTINCT IMO FROM dbo.uvs_AISPerDay WHERE VesselClassID IN (84,85,86) AND SubAreaID=11 AND DayDate >= DATEADD(day,-300,CAST(GETUTCDATE() AS date))),
x AS (SELECT d.IMO, d.DayDate, d.SubAreaID sa, d.DaysSinceLastAIS gap, d.VesselClassID cls,
  LAG(d.SubAreaID) OVER (PARTITION BY d.IMO ORDER BY d.DayDate) psa, LAG(d.DayDate) OVER (PARTITION BY d.IMO ORDER BY d.DayDate) pday,
  LAG(d.DaysSinceLastAIS) OVER (PARTITION BY d.IMO ORDER BY d.DayDate) pgap
  FROM dbo.uvs_AISPerDay d JOIN v ON v.IMO=d.IMO WHERE d.VesselClassID IN (84,85,86) AND d.DayDate >= DATEADD(day,-300,CAST(GETUTCDATE() AS date))),
tr AS (SELECT * FROM x WHERE (psa=11 AND ISNULL(sa,0)<>11) OR (sa=11 AND ISNULL(psa,0)<>11))
SELECT tr.IMO imo, tr.DayDate day, tr.pday, tr.gap, tr.pgap, tr.cls, CASE WHEN tr.psa=11 THEN 'out' ELSE 'in' END dir,
  e.AreaName ar, e.SubAreaName sa, e.LoadingStateID ld, e.Deadweight dwt, e.VoyageID vid, e.IsSTS sts,
  vs.QuantityInBarrels bbl, vs.CargoGroup cg, vs.CargoType ct, vs.VesselSanctionedBy sanc, vs.FirstLoadPortName lport, vs.LastDischargePortName dport, vs.LastDischargePortCountryName dctry
FROM tr JOIN dbo.uvs_VesselDataPerDayEnhanced e ON e.IMO=tr.IMO AND e.DayDate=tr.DayDate
LEFT JOIN dbo.uvS_VoyagesSummary vs ON vs.VoyageID=e.VoyageID ORDER BY tr.DayDate""", 5)
print("secs", time.time()-t); t=time.time()
q("""SELECT w.DayDate day, w.Direction dir, w.LoadingStateID ld, w.VesselClassID cls, w.IMO imo, w.Deadweight dwt, e.DaysSinceLastAIS gap, e2.DaysSinceLastAIS pgap,
  vs.QuantityInBarrels bbl, vs.CargoGroup cg, vs.CargoType ct, vs.VesselSanctionedBy sanc, vs.FirstLoadPortName lport, vs.LastDischargePortName dport, vs.LastDischargePortCountryName dctry
FROM dbo.uvs_WaypointsTracking w
LEFT JOIN dbo.uvs_VesselDataPerDayEnhanced e ON e.IMO=w.IMO AND e.DayDate=w.DayDate
LEFT JOIN dbo.uvs_VesselDataPerDayEnhanced e2 ON e2.IMO=w.IMO AND e2.DayDate=DATEADD(day,-1,w.DayDate)
LEFT JOIN dbo.uvS_VoyagesSummary vs ON vs.VoyageID=e.VoyageID
WHERE w.WaypointID=18 AND w.VesselClassID IN (84,85,86) AND w.DayDate >= DATEADD(day,-305,CAST(GETUTCDATE() AS date)) ORDER BY w.DayDate""", 5)
print("secs", time.time()-t); t=time.time()
q("""SELECT COUNT(*) n FROM dbo.uvs_WaypointsTracking w WHERE w.WaypointID=18 AND w.VesselClassID IN (84,85,86) AND w.DayDate >= DATEADD(day,-305,CAST(GETUTCDATE() AS date))""")
q("""SELECT w.DayDate day, w.WaypointID wp, w.Direction dir, w.VesselClassID cls, w.IMO imo, vs.QuantityInBarrels bbl, vs.CargoGroup cg, vs.VesselSanctionedBy sanc, vs.FirstLoadPortName lport, vs.LastDischargePortName dport
FROM dbo.uvs_WaypointsTracking w
LEFT JOIN dbo.uvs_VesselDataPerDayEnhanced e ON e.IMO=w.IMO AND e.DayDate=w.DayDate
LEFT JOIN dbo.uvS_VoyagesSummary vs ON vs.VoyageID=e.VoyageID
WHERE w.WaypointID IN (16,17) AND w.LoadingStateID=1 AND ((w.WaypointID=16 AND w.Direction='SN') OR (w.WaypointID=17 AND w.Direction='WE')) AND w.VesselClassID IN (84,85,86) AND w.DayDate >= DATEADD(day,-300,CAST(GETUTCDATE() AS date)) ORDER BY w.DayDate""", 5)
print("secs", time.time()-t); t=time.time()
q("""SELECT FirstLoadPortName port, FirstLoadPortSailingDate sail, VesselClassID cls, StsLoadInd sts, CargoGroup cg, CargoType ct, QuantityInBarrels bbl, VesselSanctionedBy sanc, LastDischargePortName dport, LastDischargePortCountryName dctry, Deadweight dwt
FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND FirstLoadPortSailingDate >= DATEADD(day,-300,CAST(GETUTCDATE() AS date)) AND FirstLoadPortSailingDate < GETUTCDATE()
AND (FirstLoadPortName IN ('Fujairah','Khor Fakkan','Khor al Fakkan','Sohar','Mina Al Fahal','Duqm','Sur','Salalah','Yanbu','Muscat') OR FirstLoadPortCountryName='Oman')""", 5)
print("secs", time.time()-t); t=time.time()
q("""SELECT FirstLoadPortName port, COUNT(*) n FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND FirstLoadPortSailingDate >= DATEADD(day,-300,CAST(GETUTCDATE() AS date)) AND (FirstLoadPortCountryName='Oman' OR FirstLoadPortName LIKE '%Fuj%' OR FirstLoadPortName LIKE '%Fakkan%') GROUP BY FirstLoadPortName""")
q("""SELECT LastDischargePortName port, COUNT(*) n FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND FirstLoadPortSailingDate >= DATEADD(day,-300,CAST(GETUTCDATE() AS date)) AND (LastDischargePortCountryName='Oman' OR LastDischargePortName LIKE '%Fuj%' OR LastDischargePortName LIKE '%Fakkan%') GROUP BY LastDischargePortName""")
q("""SELECT LastDischargePortArrivalDate arr, VesselClassID cls, QuantityInBarrels bbl, CargoGroup cg, VesselSanctionedBy sanc, FirstLoadPortName lport FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND LastDischargePortName='Ain Sukhna' AND LastDischargePortArrivalDate >= DATEADD(day,-300,CAST(GETUTCDATE() AS date)) AND LastDischargePortArrivalDate < GETUTCDATE()""", 3)
print("secs", time.time()-t)

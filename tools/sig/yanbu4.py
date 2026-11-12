from q import q
names = "('Hala Light','Sikinos I','Bluebell','Nasledie','Sinfa','Blue Sea','Jiaolong','HTM Titan','Demantoid','Skif','Aristodimos','Key','Camel','Triumf','Sierra','Roberta B')"
print("=== daily rows last 5 days for movers")
q(f"""SELECT v.VesselName, d.DayDate, d.VesselClass vc, d.LoadingState ls, d.Activity, d.Purpose, d.ClosestGeoAssetName loc, ROUND(d.AverageLatitude,2) la, ROUND(d.AverageLongitude,2) lo, d.AverageDraught dr, d.AISDestinationGeoAssetName dest, d.DaysSinceLastAIS dark
FROM dbo.uvs_VesselDataPerDayEnhanced d JOIN dbo.uvs_Vessels v ON v.IMO=d.IMO
WHERE v.VesselName IN {names} AND d.DayDate BETWEEN '2026-09-10' AND '2026-09-15' AND d.VesselClassID IN (84,85,86)
ORDER BY v.VesselName, d.DayDate""", 120)
print("=== voyages: Red Sea Saudi loads (Yanbu/Rabigh/Jeddah/Al-Muajjiz) sailing since 8 Sep or current")
q("""SELECT VesselName, VesselClass vc, CommercialOperator op, FirstLoadPortName lp, FirstLoadGeoAssetName ga, FirstLoadPortArrivalDate arr, FirstLoadPortSailingDate sail, QuantityInBarrels/1e3 kb, CargoGroup cg, CargoSubType cst, LastDischargePortName dp, LastDischargePortCountryName dc, Horizon, FixtureStatus fs, IsImpliedByAIS ais_impl
FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND (FirstLoadPortName IN ('Yanbu','Rabigh','Jeddah') OR FirstLoadGeoAssetName LIKE '%Muajjiz%')
AND FirstLoadPortSailingDate BETWEEN '2026-09-08' AND '2026-09-20' ORDER BY sail""", 60)
print("=== voyages for movers (latest voyage per vessel)")
q(f"""SELECT VesselName, VesselClass vc, FirstLoadPortName lp, FirstLoadPortArrivalDate arr, FirstLoadPortSailingDate sail, QuantityInBarrels/1e3 kb, CargoGroup cg, CargoSubType cst, LastDischargePortName dp, LastDischargePortCountryName dc, Horizon, VesselStatus vs
FROM dbo.uvS_VoyagesSummary WHERE VesselName IN {names} AND StartDate>='2026-08-15' ORDER BY VesselName, StartDate""", 80)
print("=== Bab el-Mandeb / Suez crossings last 3 days by Red-Sea-loaded DPP")
q("""SELECT w.DayDate, w.WaypointDescription wp, w.Direction, w.LoadingStateID ls, v.VesselName, w.VesselClass vc
FROM dbo.uvs_WaypointsTracking w JOIN dbo.uvs_Vessels v ON v.IMO=w.IMO
WHERE w.DayDate>='2026-09-13' AND w.VesselClassID IN (84,85,86) AND (w.WaypointDescription LIKE '%Mandeb%' OR w.WaypointDescription LIKE '%Suez%') AND w.LoadingStateID=1
ORDER BY w.DayDate DESC, wp""", 60)

from q import q, cur

print("=== Yanbu named sailings 14 Sep onward (model, incl future)")
q("""SELECT CAST(s.FirstLoadPortSailingDate AS date) sail, s.VesselName, s.VesselClass vc, s.CargoSubType grade, s.CargoType ct, s.QuantityInBarrels/1e6 mb, s.LastDischargePortName dis, s.Horizon h, s.FixtureStatus fx, s.Charterer ch
FROM dbo.uvS_VoyagesSummary s WHERE s.VesselClassID IN (84,85,86) AND s.FirstLoadPortName='Yanbu' AND s.FirstLoadPortSailingDate>='2026-09-14' AND s.FirstLoadPortSailingDate<'2026-09-30' ORDER BY sail""", 40)

print("=== Inside-Gulf terminal loadings by day (model) mb")
q("""SELECT CAST(FirstLoadPortSailingDate AS date) d, COUNT(*) n, SUM(QuantityInBarrels)/1e6 mb FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND FirstLoadPortSailingDate>='2026-09-10' AND FirstLoadPortSailingDate<'2026-09-19'
AND FirstLoadPortCountryName IN ('Iraq','Saudi Arabia','United Arab Emirates','Kuwait','Qatar','Iran','Bahrain') AND FirstLoadPortName NOT IN ('Yanbu','Fujairah','Khor Fakkan','Jeddah','Rabigh','Ras Tanura Anchorage') GROUP BY CAST(FirstLoadPortSailingDate AS date) ORDER BY d DESC""", 12)

print("=== Sidi Kerir sailings 16-19 Sep")
q("""SELECT CAST(s.FirstLoadPortSailingDate AS date) sail, s.VesselName, s.VesselClass vc, s.QuantityInBarrels/1e6 mb, s.LastDischargePortName dis, s.Horizon h
FROM dbo.uvS_VoyagesSummary s WHERE s.VesselClassID IN (84,85,86) AND s.FirstLoadPortName='Sidi Kerir' AND s.FirstLoadPortSailingDate>='2026-09-16' AND s.FirstLoadPortSailingDate<'2026-09-20' ORDER BY sail""", 20)

print("=== Zaynah daily since 20 Aug")
q("""SELECT d.DayDate, d.LoadingState ls, d.AverageDraught dr, d.ClosestGeoAssetName loc, d.DaysSinceLastAIS dark, d.Activity, d.Purpose, d.AISDestinationGeoAssetName dest
FROM dbo.uvs_VesselDataPerDayEnhanced d JOIN dbo.uvs_Vessels v ON v.IMO=d.IMO WHERE v.VesselName='Zaynah' AND d.DayDate>='2026-08-18' ORDER BY d.DayDate""", 40)
print("=== Zaynah voyages")
q("""SELECT s.VesselName, s.FirstLoadPortName lp, CAST(s.FirstLoadPortSailingDate AS date) sail, s.CargoSubType grade, s.QuantityInBarrels/1e6 mb, s.LastDischargePortName dis, s.Horizon h, s.Charterer ch
FROM dbo.uvS_VoyagesSummary s JOIN dbo.uvs_Vessels v ON v.IMO=s.IMO WHERE v.VesselName IN ('Zaynah','Ajwad','Nafees','Vieira','Kenya B','Kiara M','Gagat') AND s.FirstLoadPortSailingDate>='2026-08-15' ORDER BY s.VesselName, sail""", 40)

print("=== Fujairah/Khor Fakkan sailings 16-18 Sep (model)")
q("""SELECT CAST(s.FirstLoadPortSailingDate AS date) sail, s.VesselName, s.VesselClass vc, s.CargoSubType grade, s.QuantityInBarrels/1e6 mb, s.LastDischargePortName dis, s.Horizon h, s.Charterer ch
FROM dbo.uvS_VoyagesSummary s WHERE s.VesselClassID IN (84,85,86) AND s.FirstLoadPortName IN ('Fujairah','Khor Fakkan') AND s.FirstLoadPortSailingDate>='2026-09-16' AND s.FirstLoadPortSailingDate<'2026-09-19' AND s.Horizon<>'Future' ORDER BY sail DESC""", 40)
print("=== Fujairah sailings by day mb")
q("""SELECT CAST(FirstLoadPortSailingDate AS date) d, COUNT(*) n, SUM(QuantityInBarrels)/1e6 mb FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND FirstLoadPortName IN ('Fujairah','Khor Fakkan') AND FirstLoadPortSailingDate>='2026-09-10' AND FirstLoadPortSailingDate<'2026-09-19' GROUP BY CAST(FirstLoadPortSailingDate AS date) ORDER BY d DESC""", 12)

print("=== Outside Hormuz waiting-to-load / dark counts by day")
q("""SELECT DayDate, COUNT(*) n, SUM(CASE WHEN LoadingState='Laden' THEN 1 ELSE 0 END) laden, SUM(CASE WHEN Activity='Waiting' AND Purpose='Load' THEN 1 ELSE 0 END) wtl, SUM(CASE WHEN Activity='Operating' THEN 1 ELSE 0 END) oper, SUM(CASE WHEN DaysSinceLastAIS>=3 THEN 1 ELSE 0 END) dark
FROM dbo.uvs_VesselDataPerDayEnhanced WHERE VesselClassID IN (84,85,86) AND SubAreaName='Outside Hormuz' AND DayDate>='2026-09-12' GROUP BY DayDate ORDER BY DayDate DESC""", 10)

print("=== Newly full at Fujairah 17-18 Sep (draught jump >=3m, outside Hormuz)")
q("""SELECT v.VesselName, b.VesselClassID vc, a.AverageDraught dr0, b.AverageDraught dr1, b.ClosestGeoAssetName loc, b.LoadingState ls, b.Purpose, b.AISDestinationGeoAssetName dest, b.CommercialOperator op, b.DaysSinceLastAIS dark
FROM dbo.uvs_VesselDataPerDayEnhanced b JOIN dbo.uvs_VesselDataPerDayEnhanced a ON a.IMO=b.IMO AND a.DayDate='2026-09-16' JOIN dbo.uvs_Vessels v ON v.IMO=b.IMO
WHERE b.DayDate='2026-09-18' AND b.VesselClassID IN (84,85,86) AND b.SubAreaName='Outside Hormuz' AND b.AverageDraught-a.AverageDraught>=3 ORDER BY b.VesselClassID""", 40)

print("=== Bab el-Mandeb 16-18 Sep")
q("""SELECT w.DayDate, w.Direction, w.LoadingStateID ls, w.VesselClassID vc, v.VesselName, d.AISDestinationGeoAssetName dest
FROM dbo.uvs_WaypointsTracking w LEFT JOIN dbo.uvs_Vessels v ON v.IMO=w.IMO LEFT JOIN dbo.uvs_VesselDataPerDayEnhanced d ON d.IMO=w.IMO AND d.DayDate=w.DayDate
WHERE w.DayDate>='2026-09-16' AND w.VesselClassID IN (84,85,86) AND w.WaypointDescription LIKE '%Mandeb%' ORDER BY w.DayDate DESC""", 40)

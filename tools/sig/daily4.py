from q import q, cur
import datetime as dt
r = cur.execute("SELECT MAX(DayDate) FROM dbo.uvs_VesselDataPerDayEnhanced").fetchone(); print("AIS max day", r[0])
r = cur.execute("SELECT MAX(DayDate) FROM dbo.uvs_WaypointsTracking").fetchone(); print("WP max day", r[0])
D = str(cur.execute("SELECT MAX(DayDate) FROM dbo.uvs_VesselDataPerDayEnhanced").fetchone()[0])[:10]
d0 = dt.date.fromisoformat(D)
D1 = str(d0 - dt.timedelta(days=1)); D2 = str(d0 - dt.timedelta(days=2)); D3 = str(d0 - dt.timedelta(days=3))
print("D=", D)

print("=== Hormuz crossings since 16 Sep (named)")
q(f"""SELECT w.DayDate, w.Direction, w.LoadingStateID ls, w.VesselClassID vc, v.VesselName, d.AverageDraught dr, d.AISDestinationGeoAssetName dest, d.CommercialOperatorName op
FROM dbo.uvs_WaypointsTracking w LEFT JOIN dbo.uvs_Vessels v ON v.IMO=w.IMO LEFT JOIN dbo.uvs_VesselDataPerDayEnhanced d ON d.IMO=w.IMO AND d.DayDate=w.DayDate
WHERE w.DayDate>='2026-09-16' AND w.VesselClassID IN (84,85,86) AND w.WaypointDescription LIKE '%Hormuz%' ORDER BY w.DayDate DESC""", 40)

print("=== Hormuz weekly counts last 6 weeks")
q("""SELECT DATEADD(day, -DATEPART(weekday, DayDate)+1, CAST(DayDate AS date)) wk, Direction, LoadingStateID ls, COUNT(*) n
FROM dbo.uvs_WaypointsTracking WHERE DayDate>='2026-08-05' AND VesselClassID IN (84,85,86) AND WaypointDescription LIKE '%Hormuz%'
GROUP BY DATEADD(day, -DATEPART(weekday, DayDate)+1, CAST(DayDate AS date)), Direction, LoadingStateID ORDER BY wk DESC, Direction, ls""", 40)

print("=== Inside Gulf counts by day")
q(f"""SELECT DayDate, COUNT(*) n, SUM(CASE WHEN LoadingState='Laden' THEN 1 ELSE 0 END) laden, SUM(CASE WHEN DaysSinceLastAIS>=3 THEN 1 ELSE 0 END) dark, SUM(CASE WHEN LoadingState='Laden' AND DaysSinceLastAIS>=3 THEN 1 ELSE 0 END) dark_laden
FROM dbo.uvs_VesselDataPerDayEnhanced WHERE DayDate>='2026-09-12' AND VesselClassID IN (84,85,86) AND AreaName='Arabian Gulf' AND SubAreaName='Inside Hormuz' GROUP BY DayDate ORDER BY DayDate DESC""", 10)

print("=== Inside 3 days ago -> outside now (escapees)")
q(f"""SELECT v.VesselName, a.VesselClassID vc, a.LoadingState ls0, b.LoadingState ls1, a.AverageDraught dr0, b.AverageDraught dr1, a.ClosestGeoAssetName loc0, b.ClosestGeoAssetName loc1, a.DaysSinceLastAIS dark0, b.DaysSinceLastAIS dark1, b.AISDestinationGeoAssetName dest, b.CommercialOperatorName op
FROM dbo.uvs_VesselDataPerDayEnhanced a JOIN dbo.uvs_VesselDataPerDayEnhanced b ON b.IMO=a.IMO AND b.DayDate='{D}' LEFT JOIN dbo.uvs_Vessels v ON v.IMO=a.IMO
WHERE a.DayDate='{D3}' AND a.VesselClassID IN (84,85,86) AND a.AreaName='Arabian Gulf' AND a.SubAreaName='Inside Hormuz'
AND NOT (b.AreaName='Arabian Gulf' AND b.SubAreaName='Inside Hormuz')""", 40)

print("=== Outside -> inside (entering) 3 days")
q(f"""SELECT v.VesselName, a.VesselClassID vc, a.LoadingState ls0, b.LoadingState ls1, a.AverageDraught dr0, b.AverageDraught dr1, a.ClosestGeoAssetName loc0, b.ClosestGeoAssetName loc1, b.DaysSinceLastAIS dark1, b.AISDestinationGeoAssetName dest, b.CommercialOperatorName op
FROM dbo.uvs_VesselDataPerDayEnhanced a JOIN dbo.uvs_VesselDataPerDayEnhanced b ON b.IMO=a.IMO AND b.DayDate='{D}' LEFT JOIN dbo.uvs_Vessels v ON v.IMO=a.IMO
WHERE a.DayDate='{D3}' AND a.VesselClassID IN (84,85,86) AND NOT (a.AreaName='Arabian Gulf' AND a.SubAreaName='Inside Hormuz')
AND b.AreaName='Arabian Gulf' AND b.SubAreaName='Inside Hormuz'""", 40)

print("=== Reappeared after >=5 days dark (Gulf/Oman/Red Sea/Arabian Sea), draught change")
q(f"""SELECT v.VesselName, b.VesselClassID vc, a.DaysSinceLastAIS was_dark, a.ClosestGeoAssetName loc_before, b.ClosestGeoAssetName loc_now, b.LoadingState ls, a.AverageDraught dr0, b.AverageDraught dr1, b.AISDestinationGeoAssetName dest, b.CommercialOperatorName op
FROM dbo.uvs_VesselDataPerDayEnhanced a JOIN dbo.uvs_VesselDataPerDayEnhanced b ON b.IMO=a.IMO AND b.DayDate='{D}' LEFT JOIN dbo.uvs_Vessels v ON v.IMO=a.IMO
WHERE a.DayDate='{D1}' AND a.VesselClassID IN (84,85,86) AND a.DaysSinceLastAIS>=5 AND b.DaysSinceLastAIS<=1
AND (a.AreaName IN ('Arabian Gulf','Red Sea') OR b.AreaName IN ('Arabian Gulf','Red Sea') OR a.AreaName LIKE '%Arabian Sea%' OR b.AreaName LIKE '%Arabian Sea%' OR a.AreaName LIKE '%Oman%' OR b.AreaName LIKE '%Oman%')
ORDER BY a.DaysSinceLastAIS DESC""", 40)

print("=== Watchlist daily since 16 Sep")
q(f"""SELECT v.VesselName, d.DayDate, d.LoadingState ls, d.AverageDraught dr, d.ClosestGeoAssetName loc, d.DaysSinceLastAIS dark, d.Activity, d.Purpose, d.AISDestinationGeoAssetName dest
FROM dbo.uvs_VesselDataPerDayEnhanced d JOIN dbo.uvs_Vessels v ON v.IMO=d.IMO
WHERE v.VesselName IN ('Supreme','Roberta B','Ajwad','Nafees','Vieira','Kenya B','C. Brave','Plata West','Panama Prosperity','New Andros','New Dynasty','Singapore Loyalty') AND d.DayDate>='2026-09-16' AND d.VesselClassID IN (84,85,86)
ORDER BY v.VesselName, d.DayDate""", 80)

print("=== Yanbu daily activity")
q(f"""SELECT DayDate, COUNT(*) n, SUM(CASE WHEN LoadingState='Laden' THEN 1 ELSE 0 END) laden, SUM(CASE WHEN Activity='Operating' THEN 1 ELSE 0 END) oper, SUM(CASE WHEN Purpose='Load' THEN 1 ELSE 0 END) purp_load, SUM(CASE WHEN DaysSinceLastAIS>=3 THEN 1 ELSE 0 END) dark
FROM dbo.uvs_VesselDataPerDayEnhanced WHERE DayDate>='2026-09-12' AND VesselClassID IN (84,85,86) AND (ClosestGeoAssetName LIKE '%Yanbu%' OR ClosestGeoAssetName LIKE '%Muajjiz%')
GROUP BY DayDate ORDER BY DayDate DESC""", 10)

print("=== Yanbu vessels today (all)")
q(f"""SELECT v.VesselName, d.VesselClassID vc, d.LoadingState ls, d.AverageDraught dr, d.ClosestGeoAssetName loc, d.Activity, d.Purpose, d.DaysSinceLastAIS dark, d.AISDestinationGeoAssetName dest, d.CommercialOperatorName op
FROM dbo.uvs_VesselDataPerDayEnhanced d LEFT JOIN dbo.uvs_Vessels v ON v.IMO=d.IMO
WHERE d.DayDate='{D}' AND d.VesselClassID IN (84,85,86) AND (d.ClosestGeoAssetName LIKE '%Yanbu%' OR d.ClosestGeoAssetName LIKE '%Muajjiz%') ORDER BY d.VesselClassID, d.LoadingState""", 40)

print("=== Yanbu draught changes 16 Sep -> today (loading evidence)")
q(f"""SELECT v.VesselName, b.VesselClassID vc, a.AverageDraught dr0, b.AverageDraught dr1, a.ClosestGeoAssetName loc0, b.ClosestGeoAssetName loc1, b.LoadingState ls, b.Activity, b.Purpose, b.AISDestinationGeoAssetName dest
FROM dbo.uvs_VesselDataPerDayEnhanced a JOIN dbo.uvs_VesselDataPerDayEnhanced b ON b.IMO=a.IMO AND b.DayDate='{D}' LEFT JOIN dbo.uvs_Vessels v ON v.IMO=a.IMO
WHERE a.DayDate='2026-09-16' AND a.VesselClassID IN (84,85,86) AND (a.ClosestGeoAssetName LIKE '%Yanbu%' OR a.ClosestGeoAssetName LIKE '%Muajjiz%' OR b.ClosestGeoAssetName LIKE '%Yanbu%')
AND ABS(ISNULL(a.AverageDraught,0)-ISNULL(b.AverageDraught,0))>=1.5""", 30)

print("=== Yanbu sailings by day Sep (model)")
q("""SELECT CAST(FirstLoadPortSailingDate AS date) d, COUNT(*) n, SUM(QuantityInBarrels)/1e6 mb FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND FirstLoadPortName='Yanbu' AND FirstLoadPortSailingDate>='2026-09-01' AND FirstLoadPortSailingDate<'2026-09-30' GROUP BY CAST(FirstLoadPortSailingDate AS date) ORDER BY d DESC""", 30)

print("=== Yanbu named sailings 16 Sep onward (model, incl future)")
q("""SELECT CAST(s.FirstLoadPortSailingDate AS date) sail, s.VesselName, s.VesselClass vc, s.CargoSubType grade, s.CargoType ct, s.QuantityInBarrels/1e6 mb, s.LastDischargePortName dis, s.Horizon h, s.FixtureStatus fx, s.Charterer ch
FROM dbo.uvS_VoyagesSummary s WHERE s.VesselClassID IN (84,85,86) AND s.FirstLoadPortName='Yanbu' AND s.FirstLoadPortSailingDate>='2026-09-14' AND s.FirstLoadPortSailingDate<'2026-09-28' ORDER BY sail""", 40)

print("=== Inside-Gulf terminal loadings by day (model) mb")
q("""SELECT CAST(FirstLoadPortSailingDate AS date) d, COUNT(*) n, SUM(QuantityInBarrels)/1e6 mb FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND FirstLoadPortSailingDate>='2026-09-10' AND FirstLoadPortSailingDate<'2026-09-19'
AND FirstLoadPortCountryName IN ('Iraq','Saudi Arabia','United Arab Emirates','Kuwait','Qatar','Iran','Bahrain') AND FirstLoadPortName NOT IN ('Yanbu','Fujairah','Khor Fakkan','Jeddah','Rabigh','Ras Tanura Anchorage') GROUP BY CAST(FirstLoadPortSailingDate AS date) ORDER BY d DESC""", 12)

print("=== Sidi Kerir & Ain Sukhna arrivals/sailings 16-18 Sep")
q("""SELECT CAST(s.FirstLoadPortSailingDate AS date) sail, s.VesselName, s.VesselClass vc, s.FirstLoadPortName lp, s.QuantityInBarrels/1e6 mb, s.LastDischargePortName dis, s.Horizon h
FROM dbo.uvS_VoyagesSummary s WHERE s.VesselClassID IN (84,85,86) AND s.FirstLoadPortName='Sidi Kerir' AND s.FirstLoadPortSailingDate>='2026-09-16' AND s.FirstLoadPortSailingDate<'2026-09-20' ORDER BY sail""", 20)

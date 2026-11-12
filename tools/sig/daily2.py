from q import q, cur
import datetime as dt
D = '2026-09-17'; d0 = dt.date.fromisoformat(D)
D1 = str(d0 - dt.timedelta(days=1)); D2 = str(d0 - dt.timedelta(days=2)); D3 = str(d0 - dt.timedelta(days=3))

print("=== Key waypoint crossings last 3 days (named)")
q(f"""SELECT w.DayDate, w.WaypointDescription wp, w.Direction, w.LoadingStateID ls, w.VesselClassID vc, v.VesselName
FROM dbo.uvs_WaypointsTracking w LEFT JOIN dbo.uvs_Vessels v ON v.IMO=w.IMO
WHERE w.DayDate>='{D2}' AND w.VesselClassID IN (84,85,86) AND (w.WaypointDescription LIKE '%Hormuz%' OR w.WaypointDescription LIKE '%Mandeb%')
ORDER BY w.WaypointDescription, w.DayDate DESC""", 120)

print("=== Inside Hormuz 2 days ago -> Outside today (escapees)")
q(f"""SELECT v.VesselName, a.VesselClassID vc, a.LoadingState ls0, b.LoadingState ls1, a.AverageDraught dr0, b.AverageDraught dr1, a.ClosestGeoAssetName loc0, b.AreaName area1, b.ClosestGeoAssetName loc1, a.DaysSinceLastAIS dark0, b.DaysSinceLastAIS dark1, b.AISDestinationGeoAssetName dest, b.CommercialOperatorName op
FROM dbo.uvs_VesselDataPerDayEnhanced a JOIN dbo.uvs_VesselDataPerDayEnhanced b ON b.IMO=a.IMO AND b.DayDate='{D}' LEFT JOIN dbo.uvs_Vessels v ON v.IMO=a.IMO
WHERE a.DayDate='{D3}' AND a.VesselClassID IN (84,85,86) AND a.AreaName='Arabian Gulf' AND a.SubAreaName='Inside Hormuz'
AND NOT (b.AreaName='Arabian Gulf' AND b.SubAreaName='Inside Hormuz')""", 40)

print("=== Outside -> Inside (entering Gulf) 3 days")
q(f"""SELECT v.VesselName, a.VesselClassID vc, a.LoadingState ls0, b.LoadingState ls1, a.AverageDraught dr0, b.AverageDraught dr1, a.ClosestGeoAssetName loc0, b.ClosestGeoAssetName loc1, b.DaysSinceLastAIS dark1, b.AISDestinationGeoAssetName dest, b.CommercialOperatorName op
FROM dbo.uvs_VesselDataPerDayEnhanced a JOIN dbo.uvs_VesselDataPerDayEnhanced b ON b.IMO=a.IMO AND b.DayDate='{D}' LEFT JOIN dbo.uvs_Vessels v ON v.IMO=a.IMO
WHERE a.DayDate='{D3}' AND a.VesselClassID IN (84,85,86) AND NOT (a.AreaName='Arabian Gulf' AND a.SubAreaName='Inside Hormuz')
AND b.AreaName='Arabian Gulf' AND b.SubAreaName='Inside Hormuz'""", 40)

print("=== Reappeared after >=5 days dark (Gulf/Oman/Red Sea/Arabian Sea)")
q(f"""SELECT v.VesselName, b.VesselClassID vc, a.DaysSinceLastAIS was_dark, a.ClosestGeoAssetName loc_before, b.ClosestGeoAssetName loc_now, b.LoadingState ls, a.AverageDraught dr0, b.AverageDraught dr1, b.AISDestinationGeoAssetName dest, b.CommercialOperatorName op, b.AreaName area
FROM dbo.uvs_VesselDataPerDayEnhanced a JOIN dbo.uvs_VesselDataPerDayEnhanced b ON b.IMO=a.IMO AND b.DayDate='{D}' LEFT JOIN dbo.uvs_Vessels v ON v.IMO=a.IMO
WHERE a.DayDate='{D2}' AND a.VesselClassID IN (84,85,86) AND a.DaysSinceLastAIS>=5 AND b.DaysSinceLastAIS<=1
AND (a.AreaName IN ('Arabian Gulf','Red Sea') OR b.AreaName IN ('Arabian Gulf','Red Sea') OR a.AreaName LIKE '%Arabian Sea%' OR b.AreaName LIKE '%Arabian Sea%' OR a.AreaName LIKE '%Oman%' OR b.AreaName LIKE '%Oman%')
ORDER BY a.DaysSinceLastAIS DESC""", 40)

print("=== Newly dark laden inside Gulf")
q(f"""SELECT v.VesselName, b.VesselClassID vc, a.ClosestGeoAssetName loc0, b.ClosestGeoAssetName loc1, b.LoadingState ls, b.AverageDraught dr, b.DaysSinceLastAIS dark, b.AISDestinationGeoAssetName dest, b.CommercialOperatorName op
FROM dbo.uvs_VesselDataPerDayEnhanced a JOIN dbo.uvs_VesselDataPerDayEnhanced b ON b.IMO=a.IMO AND b.DayDate='{D}' LEFT JOIN dbo.uvs_Vessels v ON v.IMO=a.IMO
WHERE a.DayDate='{D2}' AND a.VesselClassID IN (84,85,86) AND a.DaysSinceLastAIS<=1 AND b.DaysSinceLastAIS>=2 AND b.AreaName='Arabian Gulf' AND b.LoadingState='Laden'""", 30)

print("=== Named sailings last 2 days Gulf/Oman/Red Sea (model)")
q(f"""SELECT CAST(s.FirstLoadPortSailingDate AS date) d, v.VesselName, s.VesselClassID vc, s.FirstLoadPortName port, s.CargoSubType grade, s.QuantityInBarrels/1e6 mb, s.LastDischargePortName dis, s.LastDischargePortCountryName ctry, s.Charterer ch, s.VesselSanctionedBy sanc, s.StsLoadInd sts, s.Horizon h, s.FixtureStatus fx
FROM dbo.uvS_VoyagesSummary s LEFT JOIN dbo.uvs_Vessels v ON v.IMO=s.IMO
WHERE s.VesselClassID IN (84,85,86) AND s.FirstLoadPortSailingDate >= '{D1}' AND s.FirstLoadPortSailingDate < '{str(d0 + dt.timedelta(days=1))}'
AND s.FirstLoadPortCountryName IN ('Iraq','Saudi Arabia','United Arab Emirates','Kuwait','Qatar','Iran','Bahrain','Oman','Egypt')
ORDER BY d DESC, mb DESC""", 60)

print("=== Yanbu: laden vessels there now - their voyage records")
q(f"""SELECT v.VesselName, s.FirstLoadPortName port, CAST(s.FirstLoadPortArrivalDate AS date) arr, CAST(s.FirstLoadPortSailingDate AS date) sail, s.CargoSubType grade, s.QuantityInBarrels/1e6 mb, s.LastDischargePortName dis, s.Charterer ch, s.Horizon h, s.FixtureStatus fx
FROM dbo.uvS_VoyagesSummary s JOIN dbo.uvs_Vessels v ON v.IMO=s.IMO
WHERE v.VesselName IN ('Maui','Minerva Clara','Maran Solon','Pirop','Asp Luna','Karneol','Tai Harmony','Roberta B','Kenya B','Angelonia','Yantar','Kemerovo','Alberta')
AND s.FirstLoadPortSailingDate >= '2026-09-05' ORDER BY sail""", 40)

print("=== Yanbu daily activity 10-17 Sep")
q(f"""SELECT DayDate, COUNT(*) n, SUM(CASE WHEN LoadingState='Laden' THEN 1 ELSE 0 END) laden, SUM(CASE WHEN Activity='Operating' THEN 1 ELSE 0 END) oper, SUM(CASE WHEN Purpose='Load' THEN 1 ELSE 0 END) purp_load, SUM(CASE WHEN DaysSinceLastAIS>=3 THEN 1 ELSE 0 END) dark
FROM dbo.uvs_VesselDataPerDayEnhanced WHERE DayDate>='2026-09-10' AND VesselClassID IN (84,85,86) AND (ClosestGeoAssetName LIKE '%Yanbu%' OR ClosestGeoAssetName LIKE '%Muajjiz%')
GROUP BY DayDate ORDER BY DayDate DESC""", 10)

print("=== Yanbu sailings 14-17 Sep by day (model)")
q(f"""SELECT CAST(FirstLoadPortSailingDate AS date) d, COUNT(*) n, SUM(QuantityInBarrels)/1e6 mb FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND FirstLoadPortName='Yanbu' AND FirstLoadPortSailingDate>='2026-09-01' GROUP BY CAST(FirstLoadPortSailingDate AS date) ORDER BY d DESC""", 20)

print("=== Fujairah sailings named 16-17 Sep")
q(f"""SELECT CAST(s.FirstLoadPortSailingDate AS date) d, v.VesselName, s.VesselClassID vc, s.CargoSubType grade, s.QuantityInBarrels/1e6 mb, s.LastDischargePortName dis, s.LastDischargePortCountryName ctry, s.Charterer ch, s.StsLoadInd sts, s.VesselSanctionedBy sanc
FROM dbo.uvS_VoyagesSummary s LEFT JOIN dbo.uvs_Vessels v ON v.IMO=s.IMO
WHERE s.VesselClassID IN (84,85,86) AND s.FirstLoadPortName IN ('Fujairah','Khor Fakkan','Sohar','Mina Al Fahal') AND s.FirstLoadPortSailingDate >= '{D1}' AND s.FirstLoadPortSailingDate < '{str(d0 + dt.timedelta(days=1))}'
ORDER BY d DESC, mb DESC""", 30)

print("=== Sanctioned laden/loading movements last 3 days in Gulf (state change)")
q(f"""SELECT v.VesselName, b.VesselClassID vc, a.ClosestGeoAssetName loc0, b.ClosestGeoAssetName loc1, a.LoadingState ls0, b.LoadingState ls1, a.AverageDraught dr0, b.AverageDraught dr1, b.AISDestinationGeoAssetName dest, s.VesselSanctionedBy sanc
FROM dbo.uvs_VesselDataPerDayEnhanced a JOIN dbo.uvs_VesselDataPerDayEnhanced b ON b.IMO=a.IMO AND b.DayDate='{D}' LEFT JOIN dbo.uvs_Vessels v ON v.IMO=a.IMO
JOIN (SELECT IMO, MAX(VesselSanctionedBy) VesselSanctionedBy FROM dbo.uvS_VoyagesSummary WHERE VesselSanctionedBy IS NOT NULL AND VesselSanctionedBy<>'' GROUP BY IMO) s ON s.IMO=a.IMO
WHERE a.DayDate='{D3}' AND a.VesselClassID IN (84,85,86) AND (a.AreaName='Arabian Gulf' OR b.AreaName='Arabian Gulf') AND b.DaysSinceLastAIS<=1
AND (a.ClosestGeoAssetName<>b.ClosestGeoAssetName OR ABS(ISNULL(a.AverageDraught,0)-ISNULL(b.AverageDraught,0))>=2)""", 40)

print("=== Bab el Mandeb named crossings 15-16 Sep")
q(f"""SELECT w.DayDate, w.Direction, w.LoadingStateID ls, w.VesselClassID vc, v.VesselName, d.AISDestinationGeoAssetName dest, d.CommercialOperatorName op
FROM dbo.uvs_WaypointsTracking w LEFT JOIN dbo.uvs_Vessels v ON v.IMO=w.IMO LEFT JOIN dbo.uvs_VesselDataPerDayEnhanced d ON d.IMO=w.IMO AND d.DayDate=w.DayDate
WHERE w.DayDate>='{D2}' AND w.VesselClassID IN (84,85,86) AND w.WaypointDescription LIKE '%Mandeb%' ORDER BY w.DayDate DESC, w.Direction""", 40)

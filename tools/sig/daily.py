from q import q, cur

mx = cur.execute("SELECT MAX(DayDate) FROM dbo.uvs_VesselDataPerDayEnhanced").fetchone()[0]
print("MAX daily", mx)
mw = cur.execute("SELECT MAX(DayDate) FROM dbo.uvs_WaypointsTracking").fetchone()[0]
print("MAX wp", mw)
D = str(mx)[:10]
import datetime as dt
d0 = dt.date.fromisoformat(D)
D1 = str(d0 - dt.timedelta(days=1)); D2 = str(d0 - dt.timedelta(days=2)); D7 = str(d0 - dt.timedelta(days=7))

print("=== Key waypoint crossings last 3 days (named)")
q(f"""SELECT w.DayDate, w.WaypointDescription wp, w.Direction, w.LoadingStateID ls, w.VesselClassID vc, v.VesselName, v.CommercialOperatorName op
FROM dbo.uvs_WaypointsTracking w LEFT JOIN dbo.uvs_Vessels v ON v.IMO=w.IMO
WHERE w.DayDate>='{D2}' AND w.VesselClassID IN (84,85,86) AND (w.WaypointDescription LIKE '%Hormuz%' OR w.WaypointDescription LIKE '%Mandeb%' OR w.WaypointDescription LIKE '%Suez%')
ORDER BY w.WaypointDescription, w.DayDate DESC""", 120)

print("=== Daily crossings by key waypoint last 8 days")
q(f"""SELECT WaypointDescription wp, DayDate, Direction, LoadingStateID ls, COUNT(*) n
FROM dbo.uvs_WaypointsTracking WHERE DayDate>='{D7}' AND VesselClassID IN (84,85,86) AND (WaypointDescription LIKE '%Hormuz%' OR WaypointDescription LIKE '%Mandeb%')
GROUP BY WaypointDescription, DayDate, Direction, LoadingStateID ORDER BY wp, DayDate DESC""", 80)

print("=== Inside/Outside Hormuz daily counts last 5 days")
q(f"""SELECT DayDate, SubAreaName sa, COUNT(*) n,
SUM(CASE WHEN LoadingState='Laden' THEN 1 ELSE 0 END) laden,
SUM(CASE WHEN DaysSinceLastAIS>=3 THEN 1 ELSE 0 END) dark,
SUM(CASE WHEN IsSTS=1 THEN 1 ELSE 0 END) sts,
SUM(CASE WHEN Purpose='Load' AND Activity='Waiting' THEN 1 ELSE 0 END) wait_load,
SUM(CASE WHEN Purpose='Load' AND Activity='Operating' THEN 1 ELSE 0 END) oper_load
FROM dbo.uvs_VesselDataPerDayEnhanced WHERE DayDate>='{str(d0 - dt.timedelta(days=4))}' AND VesselClassID IN (84,85,86) AND AreaName='Arabian Gulf'
GROUP BY DayDate, SubAreaName ORDER BY DayDate DESC, sa""", 20)

print("=== Inside Hormuz 2 days ago -> Outside today (escapees)")
q(f"""SELECT v.VesselName, a.VesselClassID vc, a.LoadingState ls0, b.LoadingState ls1, a.AverageDraught dr0, b.AverageDraught dr1, a.ClosestGeoAssetName loc0, b.AreaName area1, b.ClosestGeoAssetName loc1, a.DaysSinceLastAIS dark0, b.DaysSinceLastAIS dark1, b.AISDestinationGeoAssetName dest, v.CommercialOperatorName op
FROM dbo.uvs_VesselDataPerDayEnhanced a JOIN dbo.uvs_VesselDataPerDayEnhanced b ON b.IMO=a.IMO AND b.DayDate='{D}' LEFT JOIN dbo.uvs_Vessels v ON v.IMO=a.IMO
WHERE a.DayDate='{D2}' AND a.VesselClassID IN (84,85,86) AND a.AreaName='Arabian Gulf' AND a.SubAreaName='Inside Hormuz'
AND NOT (b.AreaName='Arabian Gulf' AND b.SubAreaName='Inside Hormuz')""", 40)

print("=== Reappeared after >=5 days dark, anywhere Gulf/Oman/Red Sea, laden or big draught change")
q(f"""SELECT v.VesselName, b.VesselClassID vc, a.DaysSinceLastAIS was_dark, a.ClosestGeoAssetName loc_before, b.ClosestGeoAssetName loc_now, b.LoadingState ls, a.AverageDraught dr0, b.AverageDraught dr1, b.AISDestinationGeoAssetName dest, v.CommercialOperatorName op, b.AreaName area
FROM dbo.uvs_VesselDataPerDayEnhanced a JOIN dbo.uvs_VesselDataPerDayEnhanced b ON b.IMO=a.IMO AND b.DayDate='{D}' LEFT JOIN dbo.uvs_Vessels v ON v.IMO=a.IMO
WHERE a.DayDate='{D2}' AND a.VesselClassID IN (84,85,86) AND a.DaysSinceLastAIS>=5 AND b.DaysSinceLastAIS<=1
AND (a.AreaName IN ('Arabian Gulf','Red Sea') OR b.AreaName IN ('Arabian Gulf','Red Sea') OR a.AreaName LIKE '%Arabian Sea%' OR b.AreaName LIKE '%Arabian Sea%' OR a.AreaName LIKE '%Oman%' OR b.AreaName LIKE '%Oman%')
ORDER BY a.DaysSinceLastAIS DESC""", 40)

print("=== Newly dark (were transmitting 2 days ago, now dark>=2) laden inside Gulf")
q(f"""SELECT v.VesselName, b.VesselClassID vc, a.ClosestGeoAssetName loc0, b.ClosestGeoAssetName loc1, b.LoadingState ls, b.AverageDraught dr, b.DaysSinceLastAIS dark, b.AISDestinationGeoAssetName dest, v.CommercialOperatorName op
FROM dbo.uvs_VesselDataPerDayEnhanced a JOIN dbo.uvs_VesselDataPerDayEnhanced b ON b.IMO=a.IMO AND b.DayDate='{D}' LEFT JOIN dbo.uvs_Vessels v ON v.IMO=a.IMO
WHERE a.DayDate='{D2}' AND a.VesselClassID IN (84,85,86) AND a.DaysSinceLastAIS<=1 AND b.DaysSinceLastAIS>=2 AND b.AreaName='Arabian Gulf' AND b.LoadingState='Laden'""", 30)

print("=== Voyage sailings by load port, last 2 days (model)")
q(f"""SELECT CAST(FirstLoadPortSailingDate AS date) d, FirstLoadPortName port, COUNT(*) n, SUM(QuantityInBarrels)/1e6 mb
FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND FirstLoadPortSailingDate >= '{D1}' AND FirstLoadPortSailingDate < '{str(d0 + dt.timedelta(days=1))}'
AND FirstLoadPortCountryName IN ('Iraq','Saudi Arabia','United Arab Emirates','Kuwait','Qatar','Iran','Bahrain','Oman')
GROUP BY CAST(FirstLoadPortSailingDate AS date), FirstLoadPortName ORDER BY d DESC, mb DESC""", 40)

print("=== Named sailings last 2 days Gulf/Oman/Red Sea")
q(f"""SELECT CAST(s.FirstLoadPortSailingDate AS date) d, v.VesselName, s.VesselClassID vc, s.FirstLoadPortName port, s.CargoSubType grade, s.QuantityInBarrels/1e6 mb, s.LastDischargePortName dis, s.LastDischargePortCountryName ctry, s.ChartererName ch, s.VesselSanctionedBy sanc, s.StsLoadInd sts, s.Horizon h
FROM dbo.uvS_VoyagesSummary s LEFT JOIN dbo.uvs_Vessels v ON v.IMO=s.IMO
WHERE s.VesselClassID IN (84,85,86) AND s.FirstLoadPortSailingDate >= '{D1}' AND s.FirstLoadPortSailingDate < '{str(d0 + dt.timedelta(days=1))}'
AND s.FirstLoadPortCountryName IN ('Iraq','Saudi Arabia','United Arab Emirates','Kuwait','Qatar','Iran','Bahrain','Oman','Egypt')
ORDER BY d DESC, mb DESC""", 60)

print("=== Yanbu today")
q(f"""SELECT v.VesselName, d.VesselClassID vc, d.Activity, d.Purpose, d.LoadingState ls, d.AverageDraught dr, d.ClosestGeoAssetName loc, d.DaysSinceLastAIS dark, d.AISDestinationGeoAssetName dest
FROM dbo.uvs_VesselDataPerDayEnhanced d LEFT JOIN dbo.uvs_Vessels v ON v.IMO=d.IMO
WHERE d.DayDate='{D}' AND d.VesselClassID IN (84,85,86) AND (d.ClosestGeoAssetName LIKE '%Yanbu%' OR d.ClosestGeoAssetName LIKE '%Muajjiz%' OR d.ClosestGeoAssetName LIKE '%Samref%' OR d.ClosestGeoAssetName LIKE '%Yasref%')
ORDER BY d.Activity""", 40)

print("=== Basrah queue today")
q(f"""SELECT v.VesselName, d.VesselClassID vc, d.Activity, d.Purpose, d.LoadingState ls, d.AverageDraught dr, d.ClosestGeoAssetName loc, d.DaysSinceLastAIS dark, d.AISDestinationGeoAssetName dest
FROM dbo.uvs_VesselDataPerDayEnhanced d LEFT JOIN dbo.uvs_Vessels v ON v.IMO=d.IMO
WHERE d.DayDate='{D}' AND d.VesselClassID IN (84,85,86) AND (d.ClosestGeoAssetName LIKE '%Basrah%' OR d.ClosestGeoAssetName LIKE '%ABOT%' OR d.ClosestGeoAssetName LIKE '%Khor Al Amaya%' OR d.ClosestGeoAssetName LIKE '%Al Zubair%')
ORDER BY d.Activity""", 40)

print("=== STS tagged anywhere, last 3 days")
q(f"""SELECT d.DayDate, v.VesselName, d.VesselClassID vc, d.Purpose, d.LoadingState ls, d.AverageDraught dr, d.AreaName area, d.ClosestGeoAssetName loc
FROM dbo.uvs_VesselDataPerDayEnhanced d LEFT JOIN dbo.uvs_Vessels v ON v.IMO=d.IMO
WHERE d.DayDate>='{D2}' AND d.VesselClassID IN (84,85,86) AND d.IsSTS=1 ORDER BY d.DayDate DESC, d.AreaName""", 60)

print("=== Sanctioned vessels active Gulf/Oman today")
q(f"""SELECT v.VesselName, d.VesselClassID vc, d.LoadingState ls, d.Activity, d.Purpose, d.ClosestGeoAssetName loc, d.DaysSinceLastAIS dark, d.AISDestinationGeoAssetName dest, s.VesselSanctionedBy sanc
FROM dbo.uvs_VesselDataPerDayEnhanced d LEFT JOIN dbo.uvs_Vessels v ON v.IMO=d.IMO
JOIN (SELECT IMO, MAX(VesselSanctionedBy) VesselSanctionedBy FROM dbo.uvS_VoyagesSummary WHERE VesselSanctionedBy IS NOT NULL AND VesselSanctionedBy<>'' GROUP BY IMO) s ON s.IMO=d.IMO
WHERE d.DayDate='{D}' AND d.VesselClassID IN (84,85,86) AND d.AreaName='Arabian Gulf'""", 40)

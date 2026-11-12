from q import q
print("=== Hormuz crossings by day, last 10 days")
q("""SELECT DayDate, Direction, LoadingStateID ls, VesselClassID vc, COUNT(*) n
FROM dbo.uvs_WaypointsTracking WHERE DayDate>='2026-09-06' AND VesselClassID IN (84,85,86) AND WaypointDescription LIKE '%Hormuz%'
GROUP BY DayDate, Direction, LoadingStateID, VesselClassID ORDER BY DayDate DESC, Direction, ls""", 80)
print("=== Hormuz crossings named 13-16 Sep")
q("""SELECT w.DayDate, w.Direction, w.LoadingStateID ls, w.VesselClassID vc, v.VesselName
FROM dbo.uvs_WaypointsTracking w LEFT JOIN dbo.uvs_Vessels v ON v.IMO=w.IMO
WHERE w.DayDate>='2026-09-13' AND w.VesselClassID IN (84,85,86) AND w.WaypointDescription LIKE '%Hormuz%' ORDER BY w.DayDate DESC""", 60)
print("=== Hormuz weekly crossings laden outbound (WE) vs year ago")
q("""SELECT DATEPART(isowk, DayDate) wk, MIN(DayDate) d0, LoadingStateID ls, Direction, COUNT(*) n
FROM dbo.uvs_WaypointsTracking WHERE VesselClassID IN (84,85,86) AND WaypointDescription LIKE '%Hormuz%' AND DayDate>='2026-08-17'
GROUP BY DATEPART(isowk, DayDate), LoadingStateID, Direction ORDER BY wk DESC, ls, Direction""", 40)
print("=== Inside-Hormuz-terminal loadings by sailing day (Signal model), mb, last 10 days")
q("""SELECT CAST(FirstLoadPortSailingDate AS date) d, COUNT(*) n, SUM(QuantityInBarrels)/1e6 mb,
SUM(CASE WHEN Horizon='Historical' THEN QuantityInBarrels ELSE 0 END)/1e6 mb_hist
FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND FirstLoadPortSailingDate BETWEEN '2026-09-06' AND '2026-09-16'
AND FirstLoadPortName IN ('Basrah','Khor Al Zubair','Ras Tanura','Juaymah','Jubail','Ras Al Khafji','Mina Al Ahmadi','Mina Saud','Mina Abdulla','Das Island','Zirku Island','Ruwais','Jebel Dhanna','Mesaieed','Ras Laffan','Halul Island','Al Shaheen Oil Field','Sitra','Kharg Island','Mubarraz','Dubai','Jebel Ali','Sharjah','Hamriyah','Umm Said','Doha','Mina Al Zour','Shuaiba','Bandar Abbas','Lavan Island','Sirri Island','Assaluyeh','Bahregan')
GROUP BY CAST(FirstLoadPortSailingDate AS date) ORDER BY d DESC""", 20)
print("=== Aug daily avg same basis (for comparison)")
q("""SELECT DATEFROMPARTS(YEAR(FirstLoadPortSailingDate),MONTH(FirstLoadPortSailingDate),1) m, COUNT(*) n, SUM(QuantityInBarrels)/1e6 mb
FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND FirstLoadPortSailingDate BETWEEN '2025-06-01' AND '2026-09-16'
AND FirstLoadPortName IN ('Basrah','Khor Al Zubair','Ras Tanura','Juaymah','Jubail','Ras Al Khafji','Mina Al Ahmadi','Mina Saud','Mina Abdulla','Das Island','Zirku Island','Ruwais','Jebel Dhanna','Mesaieed','Ras Laffan','Halul Island','Al Shaheen Oil Field','Sitra','Kharg Island','Mubarraz','Dubai','Jebel Ali','Sharjah','Hamriyah','Umm Said','Doha','Mina Al Zour','Shuaiba','Bandar Abbas','Lavan Island','Sirri Island','Assaluyeh','Bahregan')
GROUP BY DATEFROMPARTS(YEAR(FirstLoadPortSailingDate),MONTH(FirstLoadPortSailingDate),1) ORDER BY m DESC""", 20)
print("=== Inside 14 Sep -> Outside 16 Sep")
q("""SELECT v.VesselName, a.VesselClassID vc, a.LoadingState ls14, b.LoadingState ls16, a.AverageDraught dr14, b.AverageDraught dr16, a.ClosestGeoAssetName loc14, b.SubAreaName sub16, b.ClosestGeoAssetName loc16, b.DaysSinceLastAIS dark16, b.AISDestinationGeoAssetName dest
FROM dbo.uvs_VesselDataPerDayEnhanced a JOIN dbo.uvs_VesselDataPerDayEnhanced b ON b.IMO=a.IMO AND b.DayDate='2026-09-16' LEFT JOIN dbo.uvs_Vessels v ON v.IMO=a.IMO
WHERE a.DayDate='2026-09-14' AND a.VesselClassID IN (84,85,86) AND a.AreaName='Arabian Gulf' AND a.SubAreaName='Inside Hormuz'
AND NOT (b.AreaName='Arabian Gulf' AND b.SubAreaName='Inside Hormuz') ORDER BY a.LoadingState DESC""", 60)
print("=== laden dark inside Hormuz today: who/where/how long")
q("""SELECT v.VesselName, d.VesselClassID vc, d.AverageDraught dr, d.ClosestGeoAssetName loc, d.DaysSinceLastAIS dark, d.AISDestinationGeoAssetName dest, d.CommercialOperatorName op
FROM dbo.uvs_VesselDataPerDayEnhanced d LEFT JOIN dbo.uvs_Vessels v ON v.IMO=d.IMO
WHERE d.DayDate='2026-09-16' AND d.VesselClassID IN (84,85,86) AND d.AreaName='Arabian Gulf' AND d.SubAreaName='Inside Hormuz' AND d.LoadingState='Laden' AND d.DaysSinceLastAIS>=3 ORDER BY d.DaysSinceLastAIS""", 30)
print("=== Outside Hormuz today: laden by location")
q("""SELECT d.ClosestGeoAssetName loc, COUNT(*) n, SUM(CASE WHEN LoadingState='Laden' THEN 1 ELSE 0 END) laden, SUM(CASE WHEN Purpose='Load' AND Activity='Waiting' THEN 1 ELSE 0 END) wait_load, SUM(CASE WHEN DaysSinceLastAIS>=3 THEN 1 ELSE 0 END) dark
FROM dbo.uvs_VesselDataPerDayEnhanced d WHERE d.DayDate='2026-09-16' AND d.VesselClassID IN (84,85,86) AND d.AreaName='Arabian Gulf' AND d.SubAreaName='Outside Hormuz'
GROUP BY d.ClosestGeoAssetName ORDER BY n DESC""", 15)

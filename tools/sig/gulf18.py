from q import q
print("=== currency")
q("SELECT MAX(DayDate) mx FROM dbo.uvs_VesselDataPerDayEnhanced", 1)
q("SELECT MAX(DayDate) mx FROM dbo.uvs_WaypointsTracking WHERE DayDate>='2026-09-10'", 1)
print("=== Hormuz crossings by day, last 10 days")
q("""SELECT DayDate, Direction, LoadingStateID ls, VesselClass vc, COUNT(*) n
FROM dbo.uvs_WaypointsTracking WHERE DayDate>='2026-09-06' AND VesselClassID IN (84,85,86) AND WaypointDescription LIKE '%Hormuz%'
GROUP BY DayDate, Direction, LoadingStateID, VesselClass ORDER BY DayDate DESC, Direction, ls""", 80)
print("=== Hormuz crossings named 13-16 Sep")
q("""SELECT w.DayDate, w.Direction, w.LoadingStateID ls, w.VesselClass vc, v.VesselName
FROM dbo.uvs_WaypointsTracking w LEFT JOIN dbo.uvs_Vessels v ON v.IMO=w.IMO
WHERE w.DayDate>='2026-09-13' AND w.VesselClassID IN (84,85,86) AND w.WaypointDescription LIKE '%Hormuz%' ORDER BY w.DayDate DESC""", 60)
print("=== Gulf inside/outside daily counts, laden, dark, STS, waiting-load: last 14 days")
q("""SELECT DayDate, SubAreaName sa,
COUNT(*) n,
SUM(CASE WHEN LoadingState='Laden' THEN 1 ELSE 0 END) laden,
SUM(CASE WHEN LoadingState='Laden' AND DaysSinceLastAIS>=3 THEN 1 ELSE 0 END) laden_dark,
SUM(CASE WHEN DaysSinceLastAIS>=3 THEN 1 ELSE 0 END) dark,
SUM(CASE WHEN IsSTS=1 THEN 1 ELSE 0 END) sts,
SUM(CASE WHEN Purpose='Load' AND Activity='Waiting' THEN 1 ELSE 0 END) wait_load,
SUM(CASE WHEN Purpose='Load' AND Activity='Operating' THEN 1 ELSE 0 END) oper_load,
SUM(CASE WHEN Purpose='Discharge' AND Activity='Operating' THEN 1 ELSE 0 END) oper_dis
FROM dbo.uvs_VesselDataPerDayEnhanced
WHERE DayDate>='2026-09-02' AND VesselClassID IN (84,85,86) AND AreaName='Arabian Gulf'
GROUP BY DayDate, SubAreaName ORDER BY DayDate DESC, sa""", 40)
print("=== vessels Inside Hormuz on 13 Sep that are Outside Hormuz / Arabian Sea / elsewhere on 15 Sep (crossed dark or not)")
q("""SELECT v.VesselName, a.VesselClass vc, a.LoadingState ls13, b.LoadingState ls15, a.AverageDraught dr13, b.AverageDraught dr15, a.ClosestGeoAssetName loc13, b.AreaName area15, b.SubAreaName sub15, b.ClosestGeoAssetName loc15, b.DaysSinceLastAIS dark15, b.AISDestinationGeoAssetName dest
FROM dbo.uvs_VesselDataPerDayEnhanced a JOIN dbo.uvs_VesselDataPerDayEnhanced b ON b.IMO=a.IMO AND b.DayDate='2026-09-15' LEFT JOIN dbo.uvs_Vessels v ON v.IMO=a.IMO
WHERE a.DayDate='2026-09-13' AND a.VesselClassID IN (84,85,86) AND a.AreaName='Arabian Gulf' AND a.SubAreaName='Inside Hormuz'
AND NOT (b.AreaName='Arabian Gulf' AND b.SubAreaName='Inside Hormuz') ORDER BY a.LoadingState DESC, v.VesselName""", 60)
print("=== reappearances: vessels dark>=3 on 14 Sep, dark=0 on 15 Sep, anywhere in Arabian Gulf / Arabian Sea / Indian Ocean")
q("""SELECT v.VesselName, b.VesselClass vc, a.DaysSinceLastAIS dark14, a.ClosestGeoAssetName loc14, b.LoadingState ls15, b.AverageDraught dr15, b.AreaName area15, b.SubAreaName sub15, b.ClosestGeoAssetName loc15, b.AISDestinationGeoAssetName dest
FROM dbo.uvs_VesselDataPerDayEnhanced a JOIN dbo.uvs_VesselDataPerDayEnhanced b ON b.IMO=a.IMO AND b.DayDate='2026-09-15' LEFT JOIN dbo.uvs_Vessels v ON v.IMO=a.IMO
WHERE a.DayDate='2026-09-14' AND a.VesselClassID IN (84,85,86) AND a.DaysSinceLastAIS>=3 AND b.DaysSinceLastAIS=0
AND (a.AreaName='Arabian Gulf' OR b.AreaName='Arabian Gulf' OR b.AreaName LIKE '%Arabian Sea%' OR b.AreaName LIKE '%Indian%' OR b.AreaName LIKE '%Red Sea%')
ORDER BY b.LoadingState DESC""", 60)
print("=== Signal voyage model: Gulf loadings by sailing day, last 10 days (mb) - dirty+clean, DPP")
q("""SELECT CAST(FirstLoadPortSailingDate AS date) d, COUNT(*) n, SUM(QuantityInBarrels)/1e6 mb,
SUM(CASE WHEN IsImpliedByAIS='True' THEN 1 ELSE 0 END) n_implied,
SUM(CASE WHEN StsLoadInd='True' THEN QuantityInBarrels ELSE 0 END)/1e6 mb_sts_load
FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND FirstLoadPortSailingDate BETWEEN '2026-09-06' AND '2026-09-16'
AND FirstLoadPortName IN ('Basrah','Khor Al Zubair','Ras Tanura','Juaymah','Jubail','Ras Al Khafji','Mina Al Ahmadi','Mina Saud','Mina Abdulla','Das Island','Zirku Island','Ruwais','Jebel Dhanna','Mesaieed','Ras Laffan','Halul Island','Al Shaheen Oil Field','Sitra','Kharg Island','Mubarraz','Dubai','Jebel Ali','Fujairah','Khor Fakkan','Sohar','Mina Al Fahal','Duqm','Sharjah','Hamriyah')
GROUP BY CAST(FirstLoadPortSailingDate AS date) ORDER BY d DESC""", 20)
print("=== same, by load port for 14-15 Sep")
q("""SELECT CAST(FirstLoadPortSailingDate AS date) d, FirstLoadPortName lp, VesselName, VesselClass vc, QuantityInBarrels/1e3 kb, CargoSubType cst, LastDischargePortName dp, LastDischargePortCountryName dc, IsImpliedByAIS impl, StsLoadInd sts, Horizon
FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND FirstLoadPortSailingDate BETWEEN '2026-09-14' AND '2026-09-16'
AND FirstLoadPortName IN ('Basrah','Khor Al Zubair','Ras Tanura','Juaymah','Jubail','Ras Al Khafji','Mina Al Ahmadi','Mina Saud','Mina Abdulla','Das Island','Zirku Island','Ruwais','Jebel Dhanna','Mesaieed','Ras Laffan','Halul Island','Al Shaheen Oil Field','Sitra','Kharg Island','Mubarraz','Dubai','Jebel Ali','Fujairah','Khor Fakkan','Sohar','Mina Al Fahal','Duqm','Sharjah','Hamriyah')
ORDER BY d DESC, kb DESC""", 80)
print("=== Outside Hormuz / Oman / Arabian Sea: STS daily last 14 days")
q("""SELECT DayDate, AreaName, SubAreaName, COUNT(*) n, SUM(CASE WHEN Purpose='Load' THEN 1 ELSE 0 END) ld, SUM(CASE WHEN Purpose='Discharge' THEN 1 ELSE 0 END) dis
FROM dbo.uvs_VesselDataPerDayEnhanced WHERE DayDate>='2026-09-02' AND VesselClassID IN (84,85,86) AND IsSTS=1
AND (AreaName IN ('Arabian Gulf') OR AreaName LIKE '%Arabian Sea%' OR AreaName LIKE '%Oman%' OR AreaName LIKE '%Indian%')
GROUP BY DayDate, AreaName, SubAreaName ORDER BY DayDate DESC""", 60)

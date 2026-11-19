from qq import q
q("""
WITH v AS (
  SELECT IMO, DayDate, SubAreaName, AreaName, LoadingState, DaysSinceLastAIS, VoyageID,
         LAG(SubAreaName) OVER (PARTITION BY IMO ORDER BY DayDate) prev_sub,
         LAG(AreaName) OVER (PARTITION BY IMO ORDER BY DayDate) prev_area,
         LAG(DaysSinceLastAIS) OVER (PARTITION BY IMO ORDER BY DayDate) prev_gap,
         LAG(DayDate) OVER (PARTITION BY IMO ORDER BY DayDate) prev_day
  FROM dbo.uvs_VesselDataPerDayEnhanced
  WHERE VesselClassID IN (84,85,86) AND DayDate >= '2026-05-15'
)
SELECT TOP 60 IMO, prev_day, DayDate, prev_sub, SubAreaName, AreaName, LoadingState, prev_gap, DaysSinceLastAIS,
  (SELECT COUNT(*) FROM dbo.uvs_WaypointsTracking w WHERE w.IMO=v.IMO AND w.WaypointID=18 AND w.DayDate BETWEEN DATEADD(day,-3,prev_day) AND DATEADD(day,3,v.DayDate)) wp
FROM v WHERE prev_sub='Inside Hormuz' AND ISNULL(SubAreaName,'') <> 'Inside Hormuz' AND DayDate>='2026-06-01'
ORDER BY DayDate DESC
""")
q("""
WITH v AS (
  SELECT IMO, DayDate, SubAreaName, LoadingState, DaysSinceLastAIS,
         LAG(SubAreaName) OVER (PARTITION BY IMO ORDER BY DayDate) prev_sub,
         LAG(DaysSinceLastAIS) OVER (PARTITION BY IMO ORDER BY DayDate) prev_gap,
         LAG(DayDate) OVER (PARTITION BY IMO ORDER BY DayDate) prev_day
  FROM dbo.uvs_VesselDataPerDayEnhanced
  WHERE VesselClassID IN (84,85,86) AND DayDate >= '2026-05-15'
)
SELECT LoadingState, CASE WHEN wp>0 THEN 'wp' ELSE 'nowp' END k, CASE WHEN prev_gap>=1 OR DaysSinceLastAIS>=1 THEN 'gap' ELSE 'nogap' END g, COUNT(*) n FROM (
SELECT *, (SELECT COUNT(*) FROM dbo.uvs_WaypointsTracking w WHERE w.IMO=v.IMO AND w.WaypointID=18 AND w.DayDate BETWEEN DATEADD(day,-3,prev_day) AND DATEADD(day,3,v.DayDate)) wp
FROM v WHERE prev_sub='Inside Hormuz' AND ISNULL(SubAreaName,'') <> 'Inside Hormuz' AND DayDate>='2026-06-01') x
GROUP BY LoadingState, CASE WHEN wp>0 THEN 'wp' ELSE 'nowp' END, CASE WHEN prev_gap>=1 OR DaysSinceLastAIS>=1 THEN 'gap' ELSE 'nogap' END
""")

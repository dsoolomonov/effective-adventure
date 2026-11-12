import time
from qq import q
t=time.time()
q("""WITH v AS (SELECT DISTINCT IMO FROM dbo.uvs_VesselDataPerDayEnhanced WHERE VesselClassID IN (84,85,86) AND SubAreaName='Inside Hormuz' AND DayDate >= DATEADD(day,-300,CAST(GETUTCDATE() AS date))),
x AS (SELECT d.IMO, d.DayDate, d.SubAreaName sa, d.AreaName ar, d.LoadingStateID ld, d.DaysSinceLastAIS gap, d.VoyageID vid, d.VesselClassID cls, d.Deadweight dwt,
  LAG(d.SubAreaName) OVER (PARTITION BY d.IMO ORDER BY d.DayDate) psa, LAG(d.DayDate) OVER (PARTITION BY d.IMO ORDER BY d.DayDate) pday,
  LAG(d.DaysSinceLastAIS) OVER (PARTITION BY d.IMO ORDER BY d.DayDate) pgap, LAG(d.LoadingStateID) OVER (PARTITION BY d.IMO ORDER BY d.DayDate) pld
  FROM dbo.uvs_VesselDataPerDayEnhanced d JOIN v ON v.IMO=d.IMO WHERE d.VesselClassID IN (84,85,86) AND d.DayDate >= DATEADD(day,-300,CAST(GETUTCDATE() AS date)))
SELECT COUNT(*) n, SUM(CASE WHEN psa='Inside Hormuz' THEN 1 ELSE 0 END) exits, SUM(CASE WHEN sa='Inside Hormuz' THEN 1 ELSE 0 END) entries FROM x WHERE (psa='Inside Hormuz' AND ISNULL(sa,'')<>'Inside Hormuz') OR (sa='Inside Hormuz' AND ISNULL(psa,'')<>'Inside Hormuz')""")
print("secs", time.time()-t)

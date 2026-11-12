import time
from qq import q
q("SELECT TOP 3 * FROM dbo.uvs_SubAreasFlattened")
q("SELECT * FROM dbo.uvs_SubAreasFlattened WHERE 1=1", 60)
q("SELECT TOP 3 * FROM dbo.uvS_AreasFlattened")
q("SELECT * FROM dbo.uvS_AreasFlattened WHERE AreaID IN (24777,24772,24764,24767,24655)")
t=time.time()
q("""WITH v AS (SELECT DISTINCT IMO FROM dbo.uvs_AISPerDay WHERE VesselClassID IN (84,85,86) AND SubAreaID=12 AND DayDate >= DATEADD(day,-300,CAST(GETUTCDATE() AS date))),
x AS (SELECT d.IMO, d.DayDate, d.SubAreaID sa, d.AreaID ar, d.DaysSinceLastAIS gap, d.VesselClassID cls, d.AverageDraught dr,
  LAG(d.SubAreaID) OVER (PARTITION BY d.IMO ORDER BY d.DayDate) psa, LAG(d.DayDate) OVER (PARTITION BY d.IMO ORDER BY d.DayDate) pday,
  LAG(d.DaysSinceLastAIS) OVER (PARTITION BY d.IMO ORDER BY d.DayDate) pgap
  FROM dbo.uvs_AISPerDay d JOIN v ON v.IMO=d.IMO WHERE d.VesselClassID IN (84,85,86) AND d.DayDate >= DATEADD(day,-300,CAST(GETUTCDATE() AS date)))
SELECT COUNT(*) n, SUM(CASE WHEN psa=12 THEN 1 ELSE 0 END) exits FROM x WHERE (psa=12 AND ISNULL(sa,0)<>12) OR (sa=12 AND ISNULL(psa,0)<>12)""")
print("secs", time.time()-t)

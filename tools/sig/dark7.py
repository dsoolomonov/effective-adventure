import time
from qq import q
q("SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME LIKE '%rea%' OR TABLE_NAME LIKE '%AIS%' ORDER BY 2")
t=time.time()
q("SELECT COUNT(*) FROM dbo.uvs_AISPerDay WHERE VesselClassID IN (84,85,86) AND DayDate >= DATEADD(day,-300,CAST(GETUTCDATE() AS date))")
print("secs", time.time()-t); t=time.time()
q("SELECT COUNT(*) FROM dbo.uvs_VesselDataPerDayEnhanced WHERE VesselClassID IN (84,85,86) AND DayDate >= DATEADD(day,-300,CAST(GETUTCDATE() AS date))")
print("secs", time.time()-t); t=time.time()
q("SELECT TOP 5 AreaID, SubAreaID, COUNT(*) n FROM dbo.uvs_AISPerDay WHERE DayDate='2026-09-20' AND VesselClassID IN (84,85,86) GROUP BY AreaID, SubAreaID ORDER BY 3 DESC")
print("secs", time.time()-t)

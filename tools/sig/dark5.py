from qq import q
q("""SELECT w.WaypointID, w.Direction, w.LoadingStateID, vs.FirstLoadPortName, COUNT(*) n FROM dbo.uvs_WaypointsTracking w
JOIN dbo.uvs_VesselDataPerDayEnhanced d ON d.IMO=w.IMO AND d.DayDate=w.DayDate JOIN dbo.uvS_VoyagesSummary vs ON vs.VoyageID=d.VoyageID
WHERE w.WaypointID IN (16,17) AND w.DayDate>='2026-06-01' AND w.VesselClassID=84 AND vs.FirstLoadPortName IN ('Yanbu','Basrah','Ras Tanura','Sidi Kerir','Fujairah')
GROUP BY w.WaypointID, w.Direction, w.LoadingStateID, vs.FirstLoadPortName ORDER BY 1,2,3""")
q("""SELECT DATEPART(month, LastDischargePortArrivalDate) m, VesselClassID, COUNT(*) n, SUM(CAST(QuantityInBarrels AS bigint))/1000 kb FROM dbo.uvS_VoyagesSummary WHERE LastDischargePortName='Ain Sukhna' AND LastDischargePortArrivalDate>='2026-01-01' AND LastDischargePortArrivalDate<GETUTCDATE() GROUP BY DATEPART(month, LastDischargePortArrivalDate), VesselClassID ORDER BY 1,2""")
q("""SELECT MIN(DayDate) mn, MAX(DayDate) mx, COUNT(*) n FROM dbo.uvs_VesselDataPerDayEnhanced WHERE VesselClassID IN (84,85,86)""")
q("""SELECT MIN(DayDate) mn, MAX(DayDate) mx FROM dbo.uvs_WaypointsTracking WHERE WaypointID=18""")
q("""SELECT SubAreaName, AreaName, COUNT(*) n FROM dbo.uvs_VesselDataPerDayEnhanced WHERE DayDate='2026-09-20' AND VesselClassID IN (84,85,86) AND AreaName IN ('Arabian Gulf','Red Sea','East Africa','West Indian Ocean') GROUP BY SubAreaName, AreaName ORDER BY 2,3 DESC""")

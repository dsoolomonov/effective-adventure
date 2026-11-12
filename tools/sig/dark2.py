from qq import q
q("""SELECT FirstLoadPortCountryName c, COUNT(*) n FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND FirstLoadPortSailingDate>='2026-06-01' AND FirstLoadPortLevel0AreaName='Arabian Gulf' GROUP BY FirstLoadPortCountryName ORDER BY n DESC""")
q("""SELECT VesselSanctionedBy, COUNT(*) n FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND FirstLoadPortSailingDate>='2026-06-01' AND FirstLoadPortLevel0AreaName='Arabian Gulf' GROUP BY VesselSanctionedBy ORDER BY n DESC""")
q("""SELECT FirstLoadPortName p, StsLoadInd sts, CargoGroup, COUNT(*) n, SUM(CAST(QuantityInBarrels AS bigint))/1000 kb, SUM(CASE WHEN QuantityInBarrels IS NULL THEN 1 ELSE 0 END) nullq FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND FirstLoadPortSailingDate>='2026-06-01' AND FirstLoadPortSailingDate<GETUTCDATE() AND FirstLoadPortName IN ('Fujairah','Khor al Fakkan','Sohar','Mina Al Fahal','Duqm','Sur','Salalah','Yanbu') GROUP BY FirstLoadPortName, StsLoadInd, CargoGroup ORDER BY 1,2""")
# quantity coverage for hormuz laden WE transits
q("""SELECT COUNT(*) n, SUM(CASE WHEN vs.QuantityInBarrels IS NULL THEN 1 ELSE 0 END) noq, SUM(CASE WHEN d.VoyageID IS NULL THEN 1 ELSE 0 END) novoy,
 SUM(CASE WHEN vs.VesselSanctionedBy IS NOT NULL THEN 1 ELSE 0 END) sanc, SUM(CASE WHEN vs.CargoGroup='Dirty' THEN 1 ELSE 0 END) dirty, SUM(CASE WHEN vs.CargoGroup='Clean' THEN 1 ELSE 0 END) clean
FROM dbo.uvs_WaypointsTracking w
LEFT JOIN dbo.uvs_VesselDataPerDayEnhanced d ON d.IMO=w.IMO AND d.DayDate=w.DayDate
LEFT JOIN dbo.uvS_VoyagesSummary vs ON vs.VoyageID=d.VoyageID
WHERE w.WaypointID=18 AND w.Direction='WE' AND w.LoadingStateID=1 AND w.DayDate>='2026-06-01'""")
q("""SELECT TOP 20 w.DayDate, w.IMO, w.VesselClassID, w.Deadweight, w.CargoTypeID, vs.CargoType, vs.QuantityInBarrels, vs.FirstLoadPortName, vs.LastDischargePortName, vs.VesselSanctionedBy, d.DaysSinceLastAIS
FROM dbo.uvs_WaypointsTracking w
LEFT JOIN dbo.uvs_VesselDataPerDayEnhanced d ON d.IMO=w.IMO AND d.DayDate=w.DayDate
LEFT JOIN dbo.uvS_VoyagesSummary vs ON vs.VoyageID=d.VoyageID
WHERE w.WaypointID=18 AND w.Direction='WE' AND w.LoadingStateID=1 AND w.DayDate>='2026-09-01' ORDER BY w.DayDate DESC""")
q("""SELECT ed.GeoAssetName, COUNT(*) n FROM dbo.uvS_VoyageEventDetails ed JOIN dbo.uvS_VoyageEvents e ON e.VoyageEventID=ed.VoyageEventID WHERE ed.StsID IS NOT NULL AND e.Purpose='Load' AND e.EventDate>='2026-06-01' AND e.VesselTypeID=1 AND e.PortName IN ('Fujairah','Khor al Fakkan','Sohar') GROUP BY ed.GeoAssetName ORDER BY n DESC""")

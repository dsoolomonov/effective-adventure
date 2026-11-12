from qq import q
base="VesselClassID IN (84,85,86) AND FirstLoadPortSailingDate>='2026-09-01' AND FirstLoadPortSailingDate<GETUTCDATE() AND FirstLoadPortName='Fujairah' AND StsLoadInd=0 AND CargoGroup='Dirty'"
q(f"SELECT QuantitySource, CargoTypeSource, IsImpliedByAIS, Horizon, COUNT(*) n, SUM(CAST(QuantityInBarrels AS bigint))/1000 kb FROM dbo.uvS_VoyagesSummary WHERE {base} GROUP BY QuantitySource, CargoTypeSource, IsImpliedByAIS, Horizon ORDER BY kb DESC")
q(f"SELECT ISNULL(LastDischargePortCountryName,'?') dst, COUNT(*) n, SUM(CAST(QuantityInBarrels AS bigint))/1000 kb FROM dbo.uvS_VoyagesSummary WHERE {base} GROUP BY LastDischargePortCountryName ORDER BY kb DESC")
q(f"SELECT VesselClassID, COUNT(*) n, SUM(CAST(QuantityInBarrels AS bigint))/1000 kb, AVG(DATEDIFF(hour, FirstLoadPortArrivalDate, FirstLoadPortSailingDate)) hrs FROM dbo.uvS_VoyagesSummary WHERE {base} GROUP BY VesselClassID")
q(f"SELECT TOP 25 IMO, VesselName, VesselClass, FirstLoadPortArrivalDate, FirstLoadPortSailingDate, QuantityInBarrels, CargoSubType, QuantitySource, LastDischargePortName, StartingPortName, VesselSanctionedBy FROM dbo.uvS_VoyagesSummary WHERE {base} ORDER BY FirstLoadPortSailingDate DESC")

from q import q
print("=== Supreme / Roberta B / Ajwad / Nafees / Singapore Loyalty daily 10-17 Sep")
q("""SELECT v.VesselName, d.DayDate, d.LoadingState ls, d.AverageDraught dr, d.ClosestGeoAssetName loc, d.DaysSinceLastAIS dark, d.Activity, d.Purpose, d.AISDestinationGeoAssetName dest
FROM dbo.uvs_VesselDataPerDayEnhanced d JOIN dbo.uvs_Vessels v ON v.IMO=d.IMO
WHERE v.VesselName IN ('Supreme','Roberta B','Ajwad','Nafees','Singapore Loyalty','Vieira') AND d.DayDate>='2026-09-10' AND d.VesselClassID IN (84,85,86)
ORDER BY v.VesselName, d.DayDate""", 80)
print("=== Supreme voyages current")
q("""SELECT v.VesselName, s.FirstLoadPortName port, CAST(s.FirstLoadPortSailingDate AS date) sail, s.CargoSubType grade, s.QuantityInBarrels/1e6 mb, s.LastDischargePortName dis, CAST(s.LastDischargePortArrivalDate AS date) arr, s.Horizon h, s.StsLoadInd stsl, s.StsDischargeInd stsd
FROM dbo.uvS_VoyagesSummary s JOIN dbo.uvs_Vessels v ON v.IMO=s.IMO WHERE v.VesselName IN ('Supreme','Roberta B','Ajwad','Nafees','Vieira','Singapore Loyalty') AND s.FirstLoadPortSailingDate>='2026-08-20' ORDER BY v.VesselName, sail""", 30)
print("=== Sidi Kerir sailings Sep by day")
q("""SELECT CAST(FirstLoadPortSailingDate AS date) d, COUNT(*) n, SUM(QuantityInBarrels)/1e6 mb FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND FirstLoadPortName='Sidi Kerir' AND FirstLoadPortSailingDate>='2026-09-01' AND FirstLoadPortSailingDate<'2026-09-18' GROUP BY CAST(FirstLoadPortSailingDate AS date) ORDER BY d DESC""", 20)
print("=== Sidi Kerir monthly")
q("""SELECT DATEFROMPARTS(YEAR(FirstLoadPortSailingDate),MONTH(FirstLoadPortSailingDate),1) m, COUNT(*) n, SUM(QuantityInBarrels)/1e6 mb FROM dbo.uvS_VoyagesSummary WHERE VesselClassID IN (84,85,86) AND FirstLoadPortName='Sidi Kerir' AND FirstLoadPortSailingDate>='2025-09-01' AND FirstLoadPortSailingDate<'2026-09-18' GROUP BY DATEFROMPARTS(YEAR(FirstLoadPortSailingDate),MONTH(FirstLoadPortSailingDate),1) ORDER BY m DESC""", 14)
print("=== Yemen SBM (Rudum/Ash Shihir/Ras Isa) liftings Aug-Sep")
q("""SELECT CAST(s.FirstLoadPortSailingDate AS date) d, v.VesselName, s.VesselClassID vc, s.FirstLoadPortName port, s.CargoSubType grade, s.QuantityInBarrels/1e6 mb, s.LastDischargePortName dis, s.VesselSanctionedBy sanc, s.Horizon h
FROM dbo.uvS_VoyagesSummary s JOIN dbo.uvs_Vessels v ON v.IMO=s.IMO WHERE s.VesselClassID IN (84,85,86) AND s.FirstLoadPortCountryName='Yemen' AND s.FirstLoadPortSailingDate>='2026-08-01' ORDER BY d DESC""", 30)
print("=== Duqm shipyard sanctioned count by day")
q("""SELECT d.DayDate, COUNT(*) n, SUM(CASE WHEN LoadingState='Laden' THEN 1 ELSE 0 END) laden
FROM dbo.uvs_VesselDataPerDayEnhanced d JOIN (SELECT IMO, MAX(VesselSanctionedBy) sb FROM dbo.uvS_VoyagesSummary WHERE VesselSanctionedBy IS NOT NULL AND VesselSanctionedBy<>'' GROUP BY IMO) s ON s.IMO=d.IMO
WHERE d.DayDate IN ('2026-09-17','2026-09-10','2026-09-01','2026-08-15','2026-07-15') AND d.VesselClassID IN (84,85,86) AND d.ClosestGeoAssetName='Duqm Shipyard' GROUP BY d.DayDate ORDER BY d.DayDate DESC""", 10)

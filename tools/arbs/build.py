import json
N=None
EA="https://my.energyaspects.com"
def T(fig,title,kind,region,dest,months,rows): return dict(fig=fig,title=title,kind=kind,region=region,dest=dest,months=months,rows=[dict(grade=g,v=v) for g,v in rows])
M4=["Dec-26","Jan-27","Feb-27","Mar-27"]; M3=["Jan-27","Feb-27","Mar-27"]; M2=["Feb-27","Mar-27"]
tables=[
 T(3,"USGC sweet arbs","sweet","Americas","USGC",M4,[("Azeri Lt.",[N,-30.16,-26.93,-24.38]),("Bakken",[0.25,0.23,0.32,0.30]),("Bonga",[N,-21.21,-17.58,-12.73]),("Dalia",[N,-15.19,-11.12,-5.61]),("Es Sider",[N,-30.15,-26.74,-23.91])]),
 T(4,"Northwest Europe sweet arbs","sweet","Europe","NWE",M4,[("Azeri Lt.",[1.68,1.02,1.47,2.05]),("CPC Blend",[12.92,12.09,12.67,13.30]),("Forcados",[N,1.79,3.07,5.80]),("Qua Iboe",[N,0.44,1.82,4.57]),("Saharan",[1.59,0.75,1.32,1.91]),("WTI",[N,1.35,4.43,4.73])]),
 T(5,"Mediterranean sweet arbs","sweet","Europe","Med",M4,[("CPC Blend",[23.95,24.81,25.31,25.11]),("Ekofisk",[-17.78,-14.77,-15.22,-15.79]),("Es Sider",[-6.71,-7.03,-7.25,-7.50]),("Forties",[-13.00,-10.20,-10.54,-11.02]),("Saharan",[-9.70,-10.44,-10.52,-10.74]),("WTI",[N,-8.27,-7.27,-8.89])]),
 T(6,"Asia-Pacific sweet arbs","sweet","Asia","Asia-Pac",M2,[("Azeri Lt.",[-5.57,-4.92]),("CPC Blend",[6.02,6.76]),("Cabinda",[12.80,12.51]),("Forcados",[9.34,9.48]),("Forties",[-7.49,-5.17]),("WTI",[0.20,1.45])]),
 T(7,"India sweet arbs","sweet","Asia","India",M3,[("Agbami",[-9.03,-6.84,-4.70]),("Bonny Light",[-9.27,-6.95,-4.75]),("Dalia",[2.62,4.23,6.05]),("Forcados",[-7.20,-5.02,-2.98]),("WTI",[-7.13,-5.34,-3.76])]),
 T(8,"USGC sour arbs","sour","Americas","USGC",M4,[("Arab Lt.",[N,-24.16,-22.68,-17.17]),("Basrah Hvy.",[N,-30.71,-29.10,-22.98]),("Castilla",[-2.44,0.38,1.53,2.47]),("Maya",[-1.80,-0.05,0.74,1.30]),("WCS",[13.52,14.35,14.11,14.51])]),
 T(9,"Northwest Europe sour arbs","sour","Europe","NWE",M4,[("Arab Lt.",[-26.25,-25.63,-20.62,N]),("Basrah Hvy.",[-31.63,-31.91,-25.66,-23.43]),("Basrah Med.",[-32.84,-33.13,-27.04,-24.91]),("Mars",[N,-12.06,-10.57,-11.28]),("WCS",[N,2.30,4.45,3.83])]),
 T(10,"Mediterranean sour arbs","sour","Europe","Med",M4,[("Arab Lt.",[-20.16,-22.17,-17.19,N]),("Basrah Hvy.",[-26.75,-29.64,-23.37,-21.15]),("Basrah Med.",[-27.35,-30.27,-24.19,-22.07]),("Mars",[N,-9.09,-7.60,-8.34]),("WCS",[N,4.93,7.09,6.46])]),
 T(11,"Asia-Pacific sour arbs","sour","Asia","Asia-Pac",M2,[("Castilla",[11.82,11.03]),("Johan Sv.",[-10.01,-7.71]),("Mars",[-5.40,-5.41]),("WCS",[13.29,13.50])]),
 T(12,"India sour arbs","sour","Asia","India",M3,[("Arab Lt.",[8.56,8.93,N]),("Basrah Hvy.",[2.66,2.52,N]),("Castilla",[-4.72,-3.52,-1.53]),("Mars",[-14.24,-12.59,-10.53]),("WCS",[3.00,4.67,6.52])]),
]
cells=[(t,r,m,x) for t in tables for r in t["rows"] for m,x in zip(t["months"],r["v"]) if x is not None]
print("cells",len(cells),"open",sum(1 for c in cells if c[3]>0))
a=lambda href,txt:f'<a href="{EA}{href}" target="_blank" rel="noopener">{txt}</a>'
note=dict(
 headline="Dubai recovered from a weak start to January trade as Asian margins strengthened. Arbs to Asia softened w/w, but the Atlantic has to keep discounting to fill Asia's Q1-27 gap.",
 verdict="East of Suez is the tight market. The Atlantic has to clear cheaply into it: WAF and LatAm are open into Asia, while US barrels (WTI, Mars) are marginal or closed and Middle East sours are shut out of the West.",
 ea=[
  "<b>Hormuz:</b> STS constraints persist. "+a("/live/blt2432bda58f99d6ee","Middle East Gulf flows can be sustained at around 11 mb/d")+" through STS, with weekly loadings picking up to more than 6 vessels a day. "+a("/research/crude-oil/reports/sour-crude-outlook/2026-10-29-sour-crude-outlook-no-margin-for-error__blte706e1eb0c4906b1","Asia is increasingly exposed to supply disruptions")+".",
  "<b>Atlantic to Asia:</b> WTI became marginal into Asia late last week, but LatAm and WAF grades will dominate Atlantic flows. "+a("/live/bltab13c11aec6e7bcc","European and US forward balances remain oversupplied")+", so softer diffs are needed to pull crude East. Atlantic fixtures to Asia need to pick up m/m for Dec-loading to ease Asian tightness in Q1-27.",
  "<b>Sweet, Americas:</b> LatAm dominates, and Brazil absorbs most incoming VLCC tonnage. "+a("/research/refining/reports/weekly-margins-report/2026-11-02-weekly-margins-update__blt8e60094d9","Weaker Tupi diffs put it in Asian optimised slates")+", replacing Castilla. Nov-loading USGC fixtures to Asia are below their 11-month minimum and LatAm fixtures above their maximum. WTI arbs to Asia weakened w/w to marginal as Murban fell at the start of Dubai trading.",
  "<b>Sweet, WAF:</b> flows favour Asia, whose forward balances are tighter than Europe's, and Atlantic inflows to Asia fall sharply from January. Europe's optimised slate favours residue-rich LatAm and WAF (Girassol leads the mediums). Lights are priced out except CPC. WAF to Europe is marginal on paper but closes once Ekofisk is reassessed lower.",
  "<b>Sour:</b> North American sour oversupply keeps US sour diffs weak, and Oman needs to be stronger to open arbs to Asia. SPR releases from Texas caverns are hitting SGC (about $9/bbl discounts) harder than Mars. Mars is closed to Europe and Asia: it weakened w/w to Asia on softer Oman and improved to Europe on lower TD25.",
 ],
 ours=[
  "<b>Azeri (SOCAR):</b> NWE is the only open outlet, at +1.02 to +2.05 $/bbl and widening to Mar-27. It is closed to Asia-Pac (−5.57 Feb, −4.92 Mar) and the USGC (−24 to −30).",
  "<b>CPC is open everywhere it's quoted:</b> Med +24 to +25, NWE +12 to +13, Asia-Pac +6 to +7. It is the main competitor for light sweet slots in the Med and NWE.",
  "<b>North Sea lights are shut into the Med:</b> Ekofisk −15 to −18, Forties −10 to −13. Forties into Asia is −7.49 Feb, narrowing to −5.17 Mar.",
  "<b>WAF:</b> Cabinda (+12.5–12.8) and Forcados (+9.3–9.5) are wide open into Asia-Pac. Into India only Dalia is open (+2.6 to +6.1); Agbami, Bonny and Forcados are −3 to −9, narrowing into Mar.",
  "<b>Middle East sour is shut West:</b> Basrah and Arab Light are −17 to −33 into NWE, the Med and the USGC, but Arab Lt (+8.6/+8.9) and Basrah Hvy (+2.5/+2.7) are open into India.",
  "<b>Heavy Canadian/LatAm open:</b> WCS is open in every table (+2.3 to +14.5). Castilla is wide open to Asia-Pac (+11–12) but closed to India (−4.7 to −1.5).",
 ],
 trade="Place Azeri into NWE rather than offering it East. Expect CPC to keep pressing Med light sweet diffs, and stay positioned for CPC to stay cheap against Azeri/BTC while CPC's arbs are this wide open.",
 kill="Oman/Dubai firming enough to push WTI into Asia above about +2 (more US competition East), or the Azeri NWE arb turning negative.",
 caveat="Typed in by hand from EA's crude arbs report (3 Nov 2026; sources: Argus, LSEG, CME, EA). Positive = arb open (the grade is economic in that destination), negative = closed. Blanks are months EA doesn't assess. The w/w sparklines in EA's tables aren't transcribed; the w/w comments come from EA's text.",
)
out=dict(as_of="2026-11-03",source="Energy Aspects — crude arbs (Argus Media Group, LSEG, CME, Energy Aspects)",unit="$/bbl",tables=tables,note=note)
json.dump(out,open("/home/ubuntu/crude-oil-analytics/app/crude_arbs.json","w"),indent=1)

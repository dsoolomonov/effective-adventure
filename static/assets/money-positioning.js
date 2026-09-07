/**
 * Money Positioning Analysis (OIES Insight 177) + Contract Roll Analysis + Trading Decision
 * Full-screen overlay dashboard injected into the platform
 */
(function () {
  "use strict";

  const C = {
    bg: "#05070e", card: "#0b101c", border: "#1a2338",
    text: "#e8edf8", muted: "#7e8ba8",
    green: "#10b981", red: "#ef4444", blue: "#3b82f6",
    amber: "#38bdf8", purple: "#8b5cf6", cyan: "#22d3ee",
    accent: "#38bdf8", gold: "#f5b90f",
  };

  let plotlyReady = false;
  let injected = false;

  function loadPlotly(cb) {
    if (plotlyReady) return cb();
    const s = document.createElement("script");
    s.src = "https://cdn.plot.ly/plotly-2.27.0.min.js";
    s.onload = () => { plotlyReady = true; cb(); };
    document.head.appendChild(s);
  }

  function el(tag, a, ch) {
    const e = document.createElement(tag);
    if (a) Object.entries(a).forEach(([k, v]) => {
      if (k === "style" && typeof v === "object") Object.assign(e.style, v);
      else if (k.startsWith("on")) e.addEventListener(k.slice(2).toLowerCase(), v);
      else e.setAttribute(k, v);
    });
    if (ch) { if (typeof ch === "string") e.textContent = ch; else if (Array.isArray(ch)) ch.forEach(c => c && e.appendChild(c)); else e.appendChild(ch); }
    return e;
  }

  function fmt(n) { return n == null ? "N/A" : typeof n === "number" ? n.toLocaleString() : String(n); }

  function card(title, content, extra) {
    const d = el("div", { style: { background: "linear-gradient(180deg, #0d1322 0%, #0a0f1b 100%)", border: `1px solid ${C.border}`, borderRadius: "12px", padding: "18px", marginBottom: "14px", boxShadow: "0 4px 24px rgba(0,0,0,0.35)", ...(extra || {}) } });
    if (title) d.appendChild(el("div", { style: { fontSize: "11.5px", fontWeight: "700", color: C.amber, marginBottom: "12px", textTransform: "uppercase", letterSpacing: "1.2px" } }, title));
    if (typeof content === "string") d.appendChild(el("div", { style: { color: C.text, fontSize: "13px", lineHeight: "1.6" } }, content)); else if (content) d.appendChild(content);
    return d;
  }

  function statBox(label, value, color) {
    const b = el("div", { style: { textAlign: "center", padding: "8px 12px" } });
    b.appendChild(el("div", { style: { fontSize: "10px", color: C.muted, marginBottom: "3px" } }, label));
    b.appendChild(el("div", { style: { fontSize: "17px", fontWeight: "700", color: color || C.text } }, String(value)));
    return b;
  }

  function statRow(stats) {
    const r = el("div", { style: { display: "grid", gridTemplateColumns: `repeat(${Math.min(stats.length, 6)}, 1fr)`, gap: "6px" } });
    stats.forEach(s => r.appendChild(statBox(s[0], s[1], s[2])));
    return r;
  }

  const plotLayout = {
    paper_bgcolor: C.card, plot_bgcolor: C.card,
    font: { color: C.muted, size: 12 },
    margin: { t: 30, b: 50, l: 65, r: 30 },
    xaxis: { gridcolor: "#1e293b", tickfont: { size: 11 } }, yaxis: { gridcolor: "#1e293b", tickfont: { size: 11 } },
    legend: { orientation: "h", y: -0.15, font: { size: 11, color: C.text }, bgcolor: "rgba(0,0,0,0)", itemclick: "toggle", itemdoubleclick: "toggleothers" }, showlegend: true,
    hovermode: "x unified",
  };

  // Live-feed status badge (green when the Bloomberg bridge is pushing fresh
  // ticks; grey "SNAPSHOT" when no live feed). Self-refreshes every 5s while
  // attached to the DOM.
  function liveBadge() {
    const b = el("span", {
      style: {
        fontSize: "10px", fontWeight: "800", letterSpacing: ".05em",
        borderRadius: "999px", padding: "3px 10px", whiteSpace: "nowrap",
        border: "1px solid #334155", color: C.muted, background: "#0b1220",
      },
    }, "○ SNAPSHOT");
    async function tick() {
      if (!document.body.contains(b)) return;
      try {
        const r = await fetch("/api/pricing/live");
        const d = await r.json();
        const s = d.stale_seconds;
        if (d.count && s != null && s < 120) {
          b.textContent = `● LIVE · ${d.count} tickers · ${Math.round(s)}s ago`;
          b.style.color = "#000"; b.style.background = C.green;
          b.style.borderColor = C.green;
        } else if (d.count) {
          const ago = s == null ? "?" : (s > 3600 ? Math.round(s / 3600) + "h" : Math.round(s / 60) + "m");
          b.textContent = `○ STALE · last ${ago} ago`;
          b.style.color = C.gold; b.style.background = "#0b1220";
          b.style.borderColor = C.gold;
        } else {
          b.textContent = "○ SNAPSHOT (no live feed)";
          b.style.color = C.muted; b.style.background = "#0b1220";
          b.style.borderColor = "#334155";
        }
      } catch (e) { /* keep last state */ }
      setTimeout(tick, 5000);
    }
    tick();
    return b;
  }

  // ========== LIVE POSITIONING (order-level model grid, streamed by bridge) ==========
  function _posShortName(title) {
    if (!title) return "";
    return String(title).split(" (")[0];
  }

  function _posSummaryCard(insts) {
    const heads = ["Instrument", "Trend Bias", "Trend %Pos", "Net Lots", "Buy Lvls", "Sell Lvls", "Alerts"];
    const t = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px" } });
    const hr = el("tr");
    heads.forEach((h, i) => hr.appendChild(el("th", { style: { color: C.muted, fontSize: "9.5px", fontWeight: "700", padding: "5px 8px", textAlign: i === 0 ? "left" : "right", borderBottom: `1px solid ${C.border}`, textTransform: "uppercase", letterSpacing: ".5px" } }, h)));
    t.appendChild(hr);
    insts.forEach(ins => {
      const f = (ins.families && ins.families.trend) || {};
      const tp = f.pct;
      const bias = tp == null ? "—" : tp > 0.33 ? "LONG" : tp < -0.33 ? "SHORT" : "NEUTRAL";
      const bcol = bias === "LONG" ? C.green : bias === "SHORT" ? C.red : C.muted;
      let buys = 0, sells = 0, alerts = 0;
      (ins.rows || []).forEach(r => {
        const i = (r.inst || "").toUpperCase();
        if (i.indexOf("BUY") === 0) buys++; else if (i.indexOf("SELL") === 0) sells++;
        if ((r.alert || "").toUpperCase() === "ALERT") alerts++;
      });
      const tr = el("tr");
      const td = (v, opt) => el("td", { style: { padding: "5px 8px", textAlign: (opt && opt.left) ? "left" : "right", color: (opt && opt.color) || C.text, borderBottom: `1px solid #121a2c`, whiteSpace: "nowrap", ...(opt && opt.style || {}) } }, v);
      tr.appendChild(td(_posShortName(ins.title), { left: true, style: { fontWeight: "600" } }));
      tr.appendChild(td(bias, { color: bcol, style: { fontWeight: "700" } }));
      tr.appendChild(td(tp == null ? "—" : (tp * 100).toFixed(0) + "%", { color: bcol }));
      tr.appendChild(td(fmt(f.net_lots), { color: f.net_lots > 0 ? C.green : f.net_lots < 0 ? C.red : C.text }));
      tr.appendChild(td(buys ? String(buys) : "—", { color: buys ? C.green : C.muted }));
      tr.appendChild(td(sells ? String(sells) : "—", { color: sells ? C.red : C.muted }));
      tr.appendChild(td(alerts ? "⚠ " + alerts : "—", { color: alerts ? C.gold : C.muted }));
      t.appendChild(tr);
    });
    return card("Positioning Signal Summary", t);
  }

  function _posTable(rows) {
    const wrap = el("div", { style: { maxHeight: "260px", overflow: "auto", border: `1px solid ${C.border}`, borderRadius: "8px" } });
    const t = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "10.5px" } });
    const heads = [["Strat", true], ["Inst", true], ["Level", false], ["Dist $", false], ["Dist %", false], ["Est", false], ["%LS", false], ["New", false]];
    const thead = el("thead"), hr = el("tr");
    heads.forEach(([h, left]) => hr.appendChild(el("th", { style: { position: "sticky", top: "0", background: "#0b1220", color: C.muted, fontSize: "9px", fontWeight: "700", padding: "5px 6px", textAlign: left ? "left" : "right", borderBottom: `1px solid ${C.border}` } }, h)));
    thead.appendChild(hr); t.appendChild(thead);
    const tb = el("tbody");
    rows.forEach(rw => {
      const inst = (rw.inst || "").toUpperCase();
      const isBuy = inst.indexOf("BUY") === 0, isSell = inst.indexOf("SELL") === 0;
      const isAlert = (rw.alert || "").toUpperCase() === "ALERT";
      const bg = isAlert ? "rgba(245,185,15,0.12)" : isBuy ? "rgba(16,185,129,0.08)" : isSell ? "rgba(239,68,68,0.08)" : "transparent";
      const tr = el("tr", { style: { background: bg, borderLeft: isAlert ? `3px solid ${C.gold}` : "3px solid transparent" } });
      const famCol = rw.mset === "TREND" ? C.blue : rw.mset === "REVERSION" ? C.purple : rw.mset === "VALUE" ? C.cyan : C.muted;
      const instCol = isBuy ? C.green : isSell ? C.red : C.muted;
      const td = (v, opt) => el("td", { style: { padding: "4px 6px", textAlign: (opt && opt.left) ? "left" : "right", color: (opt && opt.color) || C.text, whiteSpace: "nowrap", ...(opt && opt.style || {}) } }, v);
      tr.appendChild(td(rw.strategy || "", { left: true, color: famCol, style: { fontWeight: "600" } }));
      tr.appendChild(td((isAlert ? "⚠ " : "") + (rw.inst || ""), { left: true, color: instCol, style: { fontWeight: "700" } }));
      tr.appendChild(td(rw.level == null ? "—" : fmt(rw.level)));
      tr.appendChild(td(rw.dist_usd == null ? "—" : fmt(rw.dist_usd)));
      tr.appendChild(td(rw.dist_pct == null ? "—" : (rw.dist_pct * 100).toFixed(1) + "%"));
      tr.appendChild(td(rw.est_lots == null ? "—" : fmt(rw.est_lots)));
      tr.appendChild(td(rw.new_pct_ls == null ? "—" : (rw.new_pct_ls * 100).toFixed(0) + "%"));
      tr.appendChild(td(rw.new_lots == null ? "—" : fmt(rw.new_lots), { color: rw.new_lots > 0 ? C.green : rw.new_lots < 0 ? C.red : C.text }));
      tb.appendChild(tr);
    });
    t.appendChild(tb); wrap.appendChild(t); return wrap;
  }

  function _posCard(ins) {
    const c = el("div", { style: { background: "linear-gradient(180deg,#0d1322 0%,#0a0f1b 100%)", border: `1px solid ${C.border}`, borderRadius: "12px", padding: "14px" } });
    c.appendChild(el("div", { style: { fontSize: "12.5px", fontWeight: "700", color: C.text, marginBottom: "8px" } }, _posShortName(ins.title)));
    const fam = ins.families || {};
    const famRow = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: "6px", marginBottom: "8px" } });
    [["TREND", fam.trend], ["REVERSION", fam.reversion], ["VALUE", fam.value]].forEach(([lab, f]) => {
      f = f || {}; const pct = f.pct;
      const col = pct > 0.02 ? C.green : pct < -0.02 ? C.red : C.muted;
      const b = el("div", { style: { textAlign: "center", padding: "6px", background: "#0b1220", borderRadius: "8px", border: `1px solid ${C.border}` } });
      b.appendChild(el("div", { style: { fontSize: "8.5px", color: C.muted, letterSpacing: ".5px" } }, lab));
      b.appendChild(el("div", { style: { fontSize: "15px", fontWeight: "700", color: col } }, pct == null ? "—" : (pct * 100).toFixed(0) + "%"));
      b.appendChild(el("div", { style: { fontSize: "9.5px", color: C.muted } }, "net " + fmt(f.net_lots)));
      famRow.appendChild(b);
    });
    c.appendChild(famRow);
    const pr = el("div", { style: { display: "flex", gap: "14px", fontSize: "11px", marginBottom: "8px", flexWrap: "wrap" } });
    [["Last", ins.last], ["High", ins.high], ["Low", ins.low], ["Settle", ins.settle]].forEach(([l, v]) => {
      pr.appendChild(el("span", {}, [el("span", { style: { color: C.muted } }, l + " "), el("b", { style: { color: C.text } }, v == null ? "—" : fmt(v))]));
    });
    c.appendChild(pr);
    c.appendChild(_posTable(ins.rows || []));
    return c;
  }

  async function renderLivePositioning(box) {
    const section = el("div", { id: "live-pos-section", style: { marginBottom: "20px", display: "none" } });
    box.appendChild(section);
    const badge = el("span", { style: { fontSize: "10px", fontWeight: "800", letterSpacing: ".05em", borderRadius: "999px", padding: "3px 10px", whiteSpace: "nowrap", border: "1px solid #334155", color: C.muted, background: "#0b1220" } }, "○ NO LIVE FEED");
    const updatedLbl = el("span", { style: { fontSize: "11px", color: C.muted } }, "");
    section.appendChild(el("div", { style: { display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px", flexWrap: "wrap" } }, [
      el("div", { style: { fontSize: "15px", fontWeight: "700", color: C.gold } }, "⚡ LIVE POSITIONING — Order Levels & Model Signals"),
      badge, updatedLbl,
    ]));
    section.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, marginBottom: "12px" } }, "Streamed live from your order-level workbook via the bridge (updates automatically). BUY levels shaded green, SELL red, triggered ALERT levels highlighted. Not investment advice."));
    const summaryBox = el("div", {});
    section.appendChild(summaryBox);
    const grid = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(460px,1fr))", gap: "12px" } });
    section.appendChild(grid);

    async function update() {
      if (!document.body.contains(section)) return;
      let d;
      try { const r = await fetch("/api/positioning/live"); d = await r.json(); }
      catch (e) { setTimeout(update, 10000); return; }
      const insts = (d.data && d.data.instruments) || [];
      if (!insts.length) { section.style.display = "none"; setTimeout(update, 10000); return; }
      section.style.display = "block";
      const s = d.stale_seconds;
      if (s != null && s < 120) {
        badge.textContent = `● LIVE · ${insts.length} instruments · ${Math.round(s)}s ago`;
        badge.style.color = "#000"; badge.style.background = C.green; badge.style.borderColor = C.green;
      } else {
        const ago = s == null ? "?" : (s > 3600 ? Math.round(s / 3600) + "h" : s > 60 ? Math.round(s / 60) + "m" : Math.round(s) + "s");
        badge.textContent = `○ STALE · last ${ago} ago`;
        badge.style.color = C.gold; badge.style.background = "#0b1220"; badge.style.borderColor = C.gold;
      }
      updatedLbl.textContent = d.generated ? "updated " + new Date(d.generated).toLocaleTimeString() : "";
      summaryBox.innerHTML = ""; summaryBox.appendChild(_posSummaryCard(insts));
      grid.innerHTML = ""; insts.forEach(ins => grid.appendChild(_posCard(ins)));
      setTimeout(update, 10000);
    }
    await update();
  }

  // ========== MONEY POSITIONING ==========
  async function renderMP(box) {
    box.innerHTML = '<div style="color:#94a3b8;padding:40px;text-align:center;">Loading Money Positioning analysis...</div>';
    let data;
    try { const r = await fetch("/api/money_positioning"); if (!r.ok) throw new Error(await r.text()); data = await r.json(); }
    catch (e) {
      box.innerHTML = "";
      await renderLivePositioning(box);
      box.appendChild(el("div", { style: { color: C.muted, padding: "12px", fontSize: "12px", background: C.card, borderRadius: "8px", marginBottom: "16px" } }, "Note: OIES Money Positioning requires COTnew.xlsx upload. Showing multi-commodity COT below."));
      await renderCOTMultiInline(box);
      return;
    }

    box.innerHTML = "";
    await renderLivePositioning(box);
    const s = data.summary || {}, decomp = data.decomposition || [], overlay = data.momentum_overlay || [], meth = data.methodology || {};

    // Title
    box.appendChild(el("div", { style: { fontSize: "15px", fontWeight: "700", color: C.amber, marginBottom: "4px" } }, "MONEY POSITIONING — OIES Energy Insight 177"));
    box.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, marginBottom: "14px" } }, `${meth.authors || ""}`));

    // Stats
    const fast = s.fast_component;
    const fc = fast > 0.3 ? C.green : fast < -0.3 ? C.red : C.amber;
    box.appendChild(card("Current Positioning", statRow([
      ["Net Position", fmt(s.net_position)],
      ["Slow (52w MA)", fmt(s.slow_component), C.blue],
      ["Fast Z-Score", fast != null ? fast.toFixed(2) + "σ" : "N/A", fc],
      ["Percentile", s.net_percentile != null ? s.net_percentile.toFixed(0) + "%" : "N/A", s.net_percentile > 80 ? C.red : s.net_percentile < 20 ? C.green : C.amber],
      ["1w Δ", fmt(s.weekly_change), s.weekly_change > 0 ? C.green : C.red],
      ["4w Δ", fmt(s.monthly_change), s.monthly_change > 0 ? C.green : C.red],
    ])));

    // Methodology
    box.appendChild(card("Methodology", el("div", { style: { color: C.muted, fontSize: "11px", lineHeight: "1.5" } }, meth.approach || "")));

    // Charts in 2-col grid
    const grid = el("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" } });

    const ch1 = el("div", { id: "mp-ch1", style: { width: "100%", height: "280px" } });
    grid.appendChild(card("Slow-Fast Decomposition", ch1));

    const ch2 = el("div", { id: "mp-ch2", style: { width: "100%", height: "280px" } });
    grid.appendChild(card("CTA Z-Score (Fast Component)", ch2));

    if (overlay.length > 0) {
      const ch3 = el("div", { id: "mp-ch3", style: { width: "100%", height: "280px" } });
      grid.appendChild(card("Trend Score vs CTA Positioning", ch3));
    }

    // L/S Ratio chart
    const ch4 = el("div", { id: "mp-ch4", style: { width: "100%", height: "280px" } });
    grid.appendChild(card("Long/Short Ratio & Net Percentile", ch4));

    box.appendChild(grid);

    // Interpretation
    let interp = "";
    if (fast != null) {
      if (fast > 1.5) interp = "CTAs heavily long — approaching saturation per reaction function R(u). Limited dry powder. Risk of reversal if trend breaks.";
      else if (fast > 0.5) interp = "CTAs moderately long — active trend-following. Room to extend if price trend continues. Acceleration watch above 1σ.";
      else if (fast > -0.5) interp = "CTAs near neutral — low conviction. Watch for directional breakout to trigger positioning cascade.";
      else if (fast > -1.5) interp = "CTAs moderately short — bearish trend active. Short-squeeze risk if fundamentals shift. Room for more selling.";
      else interp = "CTAs heavily short — saturation zone. High squeeze risk. Counter-trend rally probable.";
    }
    box.appendChild(card("Interpretation", interp));

    // Draw
    loadPlotly(() => {
      const dates = decomp.map(d => d.date);
      Plotly.newPlot("mp-ch1", [
        { x: dates, y: decomp.map(d => d.net_position), name: "Net Position", line: { color: C.cyan, width: 1.5 } },
        { x: dates, y: decomp.map(d => d.slow_component), name: "Slow (52w MA)", line: { color: C.amber, width: 2, dash: "dash" } },
      ], { ...plotLayout, yaxis: { ...plotLayout.yaxis, title: "Contracts" } }, { responsive: true });

      const zC = decomp.map(d => d.fast_component > 0.3 ? C.green : d.fast_component < -0.3 ? C.red : C.amber);
      Plotly.newPlot("mp-ch2", [
        { x: dates, y: decomp.map(d => d.fast_component), type: "bar", marker: { color: zC }, name: "Z-Score" },
        { x: [dates[0], dates[dates.length - 1]], y: [1.5, 1.5], mode: "lines", line: { color: C.red, width: 1, dash: "dot" }, name: "+1.5σ" },
        { x: [dates[0], dates[dates.length - 1]], y: [-1.5, -1.5], mode: "lines", line: { color: C.green, width: 1, dash: "dot" }, name: "-1.5σ" },
      ], { ...plotLayout, yaxis: { ...plotLayout.yaxis, title: "Z-Score" } }, { responsive: true });

      if (overlay.length > 0) {
        Plotly.newPlot("mp-ch3", [
          { x: overlay.map(d => d.date), y: overlay.map(d => d.fast_component), name: "CTA Z-Score", line: { color: C.cyan, width: 1.5 } },
          { x: overlay.map(d => d.date), y: overlay.map(d => d.trend_score), name: "Trend R(x)", yaxis: "y2", line: { color: C.purple, width: 1.5 } },
        ], {
          ...plotLayout,
          yaxis: { ...plotLayout.yaxis, title: "Z-Score" },
          yaxis2: { overlaying: "y", side: "right", title: "Trend Score", gridcolor: "transparent" },
        }, { responsive: true });
      }

      Plotly.newPlot("mp-ch4", [
        { x: dates, y: decomp.map(d => d.ls_ratio), name: "L/S Ratio", line: { color: C.cyan, width: 1.5 } },
        { x: dates, y: decomp.map(d => d.net_percentile), name: "Net %ile", yaxis: "y2", line: { color: C.purple, width: 1 } },
      ], {
        ...plotLayout,
        yaxis: { ...plotLayout.yaxis, title: "Long/Short Ratio" },
        yaxis2: { overlaying: "y", side: "right", title: "Percentile (%)", range: [0, 100], gridcolor: "transparent" },
      }, { responsive: true });
    });

    // --- MULTI-COMMODITY COT SECTION ---
    await renderCOTMultiInline(box);
  }

  async function renderCOTMultiInline(box) {
    let allData = {}, summaryData = {};
    try {
      const [brent, wti, gasoil, rbob] = await Promise.all([
        fetch("/api/cot_multi/data?commodity=brent").then(r => r.ok ? r.json() : null),
        fetch("/api/cot_multi/data?commodity=wti").then(r => r.ok ? r.json() : null),
        fetch("/api/cot_multi/data?commodity=gasoil").then(r => r.ok ? r.json() : null),
        fetch("/api/cot_multi/data?commodity=rbob").then(r => r.ok ? r.json() : null),
      ]);
      if (brent) allData.brent = brent.data;
      if (wti) allData.wti = wti.data;
      if (gasoil) allData.gasoil = gasoil.data;
      if (rbob) allData.rbob = rbob.data;
      const [sBrent, sWti, sGasoil, sRbob] = await Promise.all([
        fetch("/api/cot_multi/summary?commodity=brent").then(r => r.ok ? r.json() : null),
        fetch("/api/cot_multi/summary?commodity=wti").then(r => r.ok ? r.json() : null),
        fetch("/api/cot_multi/summary?commodity=gasoil").then(r => r.ok ? r.json() : null),
        fetch("/api/cot_multi/summary?commodity=rbob").then(r => r.ok ? r.json() : null),
      ]);
      if (sBrent) summaryData.brent = sBrent;
      if (sWti) summaryData.wti = sWti;
      if (sGasoil) summaryData.gasoil = sGasoil;
      if (sRbob) summaryData.rbob = sRbob;
    } catch(e) { return; }

    if (!Object.keys(allData).length) return;

    let currentCommodity = "brent";
    const container = el("div", { style: { marginTop: "30px" } });
    box.appendChild(container);

    function renderMulti() {
      container.innerHTML = "";
      const data = allData[currentCommodity] || [];
      const summary = summaryData[currentCommodity] || {};
      const labels = { brent: "ICE Brent Crude", wti: "NYMEX WTI Crude", gasoil: "ICE Gasoil", rbob: "NYMEX RBOB Gasoline" };

      // Section header
      container.appendChild(el("div", { style: { borderTop: `1px solid #334155`, paddingTop: "20px", marginTop: "10px" } }));
      const hdr = el("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "10px" } });
      hdr.appendChild(el("div", { style: { fontSize: "16px", fontWeight: "800", color: C.amber } }, `📉 MULTI-COMMODITY COT — ${labels[currentCommodity]}`));
      const selRow = el("div", { style: { display: "flex", gap: "6px" } });
      Object.keys(labels).filter(k => allData[k]).forEach(k => {
        const btn = el("button", {
          style: { padding: "6px 14px", border: k === currentCommodity ? `2px solid ${C.amber}` : "1px solid #334155", background: k === currentCommodity ? C.amber + "22" : C.card, color: k === currentCommodity ? C.amber : C.text, borderRadius: "6px", cursor: "pointer", fontSize: "11px", fontWeight: "600" },
          onClick: () => { currentCommodity = k; renderMulti(); }
        });
        btn.textContent = labels[k];
        selRow.appendChild(btn);
      });
      hdr.appendChild(selRow);
      container.appendChild(hdr);

      if (!data.length) return;

      // Summary cards
      const cats = summary.categories || {};
      const cardRow = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "10px", marginBottom: "20px" } });
      const catLabels = { mm_net: "Managed Money", pm_net: "Producers", sd_net: "Swap Dealers", or_net: "Other Reportables", oi: "Open Interest" };
      ["mm_net", "pm_net", "sd_net", "or_net", "oi"].forEach(k => {
        const c = cats[k]; if (!c) return;
        const cd = el("div", { style: { background: C.card, border: "1px solid #1e293b", borderRadius: "8px", padding: "12px" } });
        cd.innerHTML = `<div style="font-size:10px;color:${C.muted};text-transform:uppercase;font-weight:600;margin-bottom:4px">${catLabels[k]}</div><div style="font-size:20px;font-weight:800;color:${C.text}">${(c.value/1000).toFixed(0)}K</div><div style="font-size:11px;color:${c.w_change >= 0 ? '#10b981' : '#ef4444'};margin-top:3px">W/W: ${c.w_change >= 0 ? '+' : ''}${(c.w_change/1000).toFixed(1)}K</div><div style="font-size:10px;color:${C.muted};margin-top:2px">Pctl: ${c.percentile.toFixed(0)}% | Z: ${c.z_score >= 0 ? '+' : ''}${c.z_score.toFixed(2)}</div><div style="margin-top:4px;height:3px;background:#1e293b;border-radius:2px;overflow:hidden"><div style="height:100%;width:${c.percentile}%;background:${c.percentile > 75 ? '#10b981' : c.percentile < 25 ? '#ef4444' : C.amber}"></div></div>`;
        cardRow.appendChild(cd);
      });
      container.appendChild(cardRow);

      // Chart containers
      const uid = "cmi-" + currentCommodity + "-";
      const ch1 = el("div", { id: uid+"1", style: { width: "100%", height: "480px", marginBottom: "20px" } });
      container.appendChild(el("div", { style: { fontSize: "13px", fontWeight: "700", color: C.amber, marginBottom: "6px" } }, "Net Positioning vs Price"));
      container.appendChild(ch1);

      const ch2 = el("div", { id: uid+"2", style: { width: "100%", height: "460px", marginBottom: "20px" } });
      container.appendChild(el("div", { style: { fontSize: "13px", fontWeight: "700", color: C.amber, marginBottom: "6px" } }, "Managed Money Net — Seasonal Overlay (by Year)"));
      container.appendChild(ch2);

      const ch3 = el("div", { id: uid+"3", style: { width: "100%", height: "460px", marginBottom: "20px" } });
      container.appendChild(el("div", { style: { fontSize: "13px", fontWeight: "700", color: C.amber, marginBottom: "6px" } }, "Net as % of Open Interest"));
      container.appendChild(ch3);

      const ch4 = el("div", { id: uid+"4", style: { width: "100%", height: "460px", marginBottom: "20px" } });
      container.appendChild(el("div", { style: { fontSize: "13px", fontWeight: "700", color: C.amber, marginBottom: "6px" } }, "Managed Money — Longs vs Shorts"));
      container.appendChild(ch4);

      const ch5 = el("div", { id: uid+"5", style: { width: "100%", height: "460px", marginBottom: "20px" } });
      container.appendChild(el("div", { style: { fontSize: "13px", fontWeight: "700", color: C.amber, marginBottom: "6px" } }, "All Categories — Net Positioning"));
      container.appendChild(ch5);

      const ch6 = el("div", { id: uid+"6", style: { width: "100%", height: "420px", marginBottom: "20px" } });
      container.appendChild(el("div", { style: { fontSize: "13px", fontWeight: "700", color: C.amber, marginBottom: "6px" } }, "Managed Money — Weekly Change"));
      container.appendChild(ch6);

      const ch7 = el("div", { id: uid+"7", style: { width: "100%", height: "460px", marginBottom: "20px" } });
      container.appendChild(el("div", { style: { fontSize: "13px", fontWeight: "700", color: C.amber, marginBottom: "6px" } }, "Open Interest vs Price"));
      container.appendChild(ch7);

      const ch8 = el("div", { id: uid+"8", style: { width: "100%", height: "460px", marginBottom: "20px" } });
      container.appendChild(el("div", { style: { fontSize: "13px", fontWeight: "700", color: C.amber, marginBottom: "6px" } }, "Cross-Commodity Comparison — MM Net % OI"));
      container.appendChild(ch8);

      // Weekly table
      container.appendChild(el("div", { style: { fontSize: "13px", fontWeight: "700", color: C.amber, marginBottom: "8px", marginTop: "10px" } }, "Recent Weekly Data (Last 12 Weeks)"));
      const tbl = el("div", { style: { overflowX: "auto" } });
      const recent = data.slice(-12).reverse();
      let thtml = `<table style="width:100%;border-collapse:collapse;font-size:11px;color:${C.text}"><thead><tr style="background:${C.card};border-bottom:1px solid #334155"><th style="padding:8px;text-align:left">Date</th><th style="padding:8px;text-align:right">Price</th><th style="padding:8px;text-align:right">MM Net</th><th style="padding:8px;text-align:right">MM Chg</th><th style="padding:8px;text-align:right">Prod Net</th><th style="padding:8px;text-align:right">Swap Net</th><th style="padding:8px;text-align:right">OI</th><th style="padding:8px;text-align:right">MM %OI</th></tr></thead><tbody>`;
      recent.forEach((r, i) => {
        const prev = i < recent.length - 1 ? recent[i + 1] : r;
        const mmChg = (r.mm_net || 0) - (prev.mm_net || 0);
        const chgC = mmChg >= 0 ? "#10b981" : "#ef4444";
        thtml += `<tr style="border-bottom:1px solid #1e293b"><td style="padding:6px 8px">${r.date}</td><td style="padding:6px 8px;text-align:right">${r.price ? r.price.toFixed(2) : '-'}</td><td style="padding:6px 8px;text-align:right;font-weight:600">${r.mm_net ? (r.mm_net/1000).toFixed(1)+'K' : '-'}</td><td style="padding:6px 8px;text-align:right;color:${chgC}">${mmChg ? (mmChg>=0?'+':'')+(mmChg/1000).toFixed(1)+'K' : '-'}</td><td style="padding:6px 8px;text-align:right">${r.pm_net ? (r.pm_net/1000).toFixed(1)+'K' : '-'}</td><td style="padding:6px 8px;text-align:right">${r.sd_net ? (r.sd_net/1000).toFixed(1)+'K' : '-'}</td><td style="padding:6px 8px;text-align:right">${r.oi ? (r.oi/1000).toFixed(0)+'K' : '-'}</td><td style="padding:6px 8px;text-align:right">${r.mm_pct_oi != null ? r.mm_pct_oi.toFixed(1)+'%' : '-'}</td></tr>`;
      });
      thtml += `</tbody></table>`;
      tbl.innerHTML = thtml;
      container.appendChild(tbl);

      // Draw charts
      loadPlotly(() => requestAnimationFrame(() => {
        const dates = data.map(r => r.date);
        const mmNet = data.map(r => r.mm_net);
        const pmNet = data.map(r => r.pm_net);
        const sdNet = data.map(r => r.sd_net);
        const orNet = data.map(r => r.or_net);
        const prices = data.map(r => r.price);
        const oi = data.map(r => r.oi);
        const mmLong = data.map(r => r.mm_long);
        const mmShort = data.map(r => r.mm_short);

        const ly = (yTitle, opts = {}) => ({
          paper_bgcolor: "transparent", plot_bgcolor: "transparent",
          font: { color: C.text, size: 11 }, margin: { l: 65, r: opts.r || 20, t: 25, b: 45 },
          xaxis: { gridcolor: "#1e293b", linecolor: "#334155", tickfont: { size: 10 } },
          yaxis: { title: yTitle, gridcolor: "#1e293b", linecolor: "#334155", tickfont: { size: 10 }, zeroline: true, zerolinecolor: "#334155" },
          ...(opts.yaxis2 ? { yaxis2: opts.yaxis2 } : {}),
          legend: { orientation: "h", x: 0, y: -0.13, font: { size: 10 } }, hovermode: "x unified",
        });
        const cfg = { responsive: true, displayModeBar: false };

        try { Plotly.newPlot(uid+"1", [
          { x: dates, y: mmNet, name: "MM Net", line: { color: C.amber, width: 2.5 } },
          { x: dates, y: pmNet, name: "Producers", line: { color: "#6366f1", width: 1.5 } },
          { x: dates, y: prices, name: "Price", line: { color: "#10b981", width: 2, dash: "dot" }, yaxis: "y2" },
        ], ly("Net Position", { r: 65, yaxis2: { title: "Price", overlaying: "y", side: "right", gridcolor: "transparent", tickfont: { size: 10, color: "#10b981" } } }), cfg); } catch(e) {}

        try {
          const byYear = {};
          data.forEach(r => { if (!r.mm_net) return; const d = new Date(r.date); const y = d.getFullYear(); const doy = Math.floor((d - new Date(y,0,1))/86400000); if (!byYear[y]) byYear[y]={x:[],y:[]}; byYear[y].x.push(doy); byYear[y].y.push(r.mm_net); });
          const yrs = Object.keys(byYear).sort();
          const colors = ["#64748b","#64748b","#64748b","#6366f1","#8b5cf6","#06b6d4","#10b981","#f59e0b","#ef4444","#ec4899","#f97316","#14b8a6","#a855f7","#eab308","#84cc16","#0ea5e9"];
          const traces = yrs.map((y,i) => ({ x: byYear[y].x, y: byYear[y].y, name: y, mode: "lines", line: { color: colors[i%colors.length], width: y===String(new Date().getFullYear())?3:(parseInt(y)>=2022?2:1), dash: parseInt(y)<2020?"dot":"solid" }, opacity: parseInt(y)<2020?0.5:1 }));
          const sLy = ly("MM Net (contracts)");
          sLy.xaxis.title = "Day of Year";
          sLy.xaxis.tickvals = [0,31,59,90,120,151,181,212,243,273,304,334];
          sLy.xaxis.ticktext = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
          Plotly.newPlot(uid+"2", traces, sLy, cfg);
        } catch(e) {}

        try { Plotly.newPlot(uid+"3", [
          { x: dates, y: data.map(r => r.mm_pct_oi), name: "Managed Money", line: { color: C.amber, width: 2.5 } },
          { x: dates, y: data.map(r => r.pm_pct_oi), name: "Producers", line: { color: "#6366f1", width: 2 } },
          { x: dates, y: data.map(r => r.sd_pct_oi), name: "Swap Dealers", line: { color: "#06b6d4", width: 2 } },
        ], ly("Net % of Open Interest"), cfg); } catch(e) {}

        try { Plotly.newPlot(uid+"4", [
          { x: dates, y: mmLong, name: "MM Longs", fill: "tozeroy", line: { color: "#10b981", width: 1.5 }, fillcolor: "rgba(16,185,129,0.15)" },
          { x: dates, y: mmShort.map(v => v ? -v : null), name: "MM Shorts (inv)", fill: "tozeroy", line: { color: "#ef4444", width: 1.5 }, fillcolor: "rgba(239,68,68,0.15)" },
        ], ly("Contracts"), cfg); } catch(e) {}

        try { Plotly.newPlot(uid+"5", [
          { x: dates, y: mmNet, name: "Managed Money", line: { color: C.amber, width: 2.5 } },
          { x: dates, y: pmNet, name: "Producers", line: { color: "#6366f1", width: 2 } },
          { x: dates, y: sdNet, name: "Swap Dealers", line: { color: "#06b6d4", width: 2 } },
          { x: dates, y: orNet, name: "Other Reportables", line: { color: "#a855f7", width: 1.5 } },
        ], ly("Net Position"), cfg); } catch(e) {}

        try {
          const wkChg = mmNet.map((v,i) => i===0 ? 0 : (v||0)-(mmNet[i-1]||0));
          Plotly.newPlot(uid+"6", [{ x: dates, y: wkChg, type: "bar", marker: { color: wkChg.map(v => v>=0?"#10b981":"#ef4444") } }], ly("Weekly Δ (contracts)"), cfg);
        } catch(e) {}

        try { Plotly.newPlot(uid+"7", [
          { x: dates, y: oi, name: "Open Interest", line: { color: "#8b5cf6", width: 2 } },
          { x: dates, y: prices, name: "Price", line: { color: "#10b981", width: 2, dash: "dot" }, yaxis: "y2" },
        ], ly("Open Interest", { r: 65, yaxis2: { title: "Price", overlaying: "y", side: "right", gridcolor: "transparent", tickfont: { size: 10, color: "#10b981" } } }), cfg); } catch(e) {}

        try {
          const bD = allData.brent || [], wD = allData.wti || [], gD = allData.gasoil || [];
          Plotly.newPlot(uid+"8", [
            { x: bD.map(r=>r.date), y: bD.map(r=>r.mm_pct_oi), name: "Brent", line: { color: C.amber, width: 2.5 } },
            { x: wD.map(r=>r.date), y: wD.map(r=>r.mm_pct_oi), name: "WTI", line: { color: "#6366f1", width: 2.5 } },
            { x: gD.map(r=>r.date), y: gD.map(r=>r.mm_pct_oi), name: "Gasoil", line: { color: "#06b6d4", width: 2.5 } },
          ], ly("MM Net as % of OI"), cfg);
        } catch(e) {}
      }));
    }
    renderMulti();
  }

  // ========== CONTRACT ANALYSIS ==========
  async function renderCA(box) {
    box.innerHTML = '<div style="color:#94a3b8;padding:40px;text-align:center;">Loading Contract Analysis...</div>';
    let data;
    try { const r = await fetch("/api/contract_analysis"); if (!r.ok) throw new Error(await r.text()); data = await r.json(); }
    catch (e) { box.innerHTML = `<div style="color:${C.red};padding:20px;">Error: ${e.message}</div>`; return; }

    box.innerHTML = "";
    const s = data.summary || {}, ts = data.timeseries || [];

    box.appendChild(el("div", { style: { fontSize: "15px", fontWeight: "700", color: C.amber, marginBottom: "4px" } }, "CO1/CO2 CONTRACT ROLL ANALYSIS"));
    box.appendChild(el("div", { style: { fontSize: "12px", color: C.red, marginBottom: "14px", fontWeight: "600" } }, "⚠ CO1 EXPIRING — CO2 IS THE NEW PROMPT MONTH. Brent prompts expire end of each month."));

    const sc = s.spread > 0 ? C.green : C.red;
    box.appendChild(card("Contract Summary", statRow([
      ["CO1 (Expiring)", "$" + fmt(s.co1_price), C.muted],
      ["CO2 (New Prompt)", "$" + fmt(s.co2_price), C.green],
      ["Spread", s.spread != null ? "$" + s.spread.toFixed(2) : "N/A", sc],
      ["CO1 Volume", fmt(s.co1_volume), C.muted],
      ["CO2 Volume", fmt(s.co2_volume), C.cyan],
      ["Roll Status", s.oi_shift || "N/A", s.oi_shift === "Roll Active" ? C.green : C.amber],
    ])));

    box.appendChild(card("Open Interest Overview", statRow([
      ["CO1 OI", fmt(s.co1_oi), C.muted],
      ["CO2 OI", fmt(s.co2_oi), C.cyan],
      ["Volume Shift", s.vol_shift || "N/A", s.vol_shift === "CO2 Dominant" ? C.green : C.amber],
    ])));

    const grid = el("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" } });
    const ch1 = el("div", { id: "ca-ch1", style: { width: "100%", height: "280px" } });
    grid.appendChild(card("Prices & Spread (Last 90 Days)", ch1));
    const ch2 = el("div", { id: "ca-ch2", style: { width: "100%", height: "280px" } });
    grid.appendChild(card("Volume (Last 60 Days)", ch2));
    const ch3 = el("div", { id: "ca-ch3", style: { width: "100%", height: "280px" } });
    grid.appendChild(card("Open Interest (Last 60 Days)", ch3));
    const ch4 = el("div", { id: "ca-ch4", style: { width: "100%", height: "280px" } });
    grid.appendChild(card("CO1/CO2 Ratios — Below 1.0 = CO2 Dominant", ch4));
    box.appendChild(grid);

    // Roll dynamics interpretation
    let rollInterp = "ROLL DYNAMICS: ";
    if (s.oi_shift === "Roll Active") rollInterp += "Open interest is actively shifting from CO1 to CO2, confirming the roll is underway. ";
    else rollInterp += "Roll may not be complete — some positions still held in CO1. ";
    if (s.vol_shift === "CO2 Dominant") rollInterp += "Volume has migrated to CO2 — it is the actionable contract. ";
    else rollInterp += "CO1 still has significant volume — late rollers active. Watch for final-day squeeze. ";
    if (s.spread != null) {
      if (s.spread > 0) rollInterp += `Backwardation ($${s.spread.toFixed(2)}) indicates near-term tightness.`;
      else rollInterp += `Contango ($${s.spread.toFixed(2)}) suggests near-term oversupply.`;
    }
    box.appendChild(card("Roll Dynamics", rollInterp));

    loadPlotly(() => {
      const last90 = ts.slice(-90), d90 = last90.map(d => d.date);
      const last60 = ts.slice(-60), d60 = last60.map(d => d.date);

      Plotly.newPlot("ca-ch1", [
        { x: d90, y: last90.map(d => d.co1_price), name: "CO1", line: { color: C.red, width: 1.5, dash: "dash" } },
        { x: d90, y: last90.map(d => d.co2_price), name: "CO2", line: { color: C.green, width: 2 } },
        { x: d90, y: last90.map(d => d.spread), name: "Spread", yaxis: "y2", type: "bar", marker: { color: last90.map(d => d.spread > 0 ? C.green + "50" : C.red + "50") } },
      ], { ...plotLayout, yaxis: { ...plotLayout.yaxis, title: "$/bbl" }, yaxis2: { overlaying: "y", side: "right", title: "Spread", gridcolor: "transparent" } }, { responsive: true });

      Plotly.newPlot("ca-ch2", [
        { x: d60, y: last60.map(d => d.co1_volume), name: "CO1 Vol", type: "bar", marker: { color: C.red + "80" } },
        { x: d60, y: last60.map(d => d.co2_volume), name: "CO2 Vol", type: "bar", marker: { color: C.green + "80" } },
      ], { ...plotLayout, barmode: "group", yaxis: { ...plotLayout.yaxis, title: "Volume" } }, { responsive: true });

      Plotly.newPlot("ca-ch3", [
        { x: d60, y: last60.map(d => d.co1_oi), name: "CO1 OI", line: { color: C.red, width: 2 }, fill: "tozeroy", fillcolor: C.red + "15" },
        { x: d60, y: last60.map(d => d.co2_oi), name: "CO2 OI", line: { color: C.green, width: 2 }, fill: "tozeroy", fillcolor: C.green + "15" },
      ], { ...plotLayout, yaxis: { ...plotLayout.yaxis, title: "Open Interest" } }, { responsive: true });

      Plotly.newPlot("ca-ch4", [
        { x: d60, y: last60.map(d => d.volume_ratio), name: "Vol Ratio", line: { color: C.amber, width: 1.5 } },
        { x: d60, y: last60.map(d => d.oi_ratio), name: "OI Ratio", line: { color: C.purple, width: 1.5 } },
        { x: [d60[0], d60[d60.length - 1]], y: [1, 1], mode: "lines", line: { color: C.muted, dash: "dot", width: 1 }, name: "Parity" },
      ], { ...plotLayout, yaxis: { ...plotLayout.yaxis, title: "Ratio (CO1/CO2)" } }, { responsive: true });
    });
  }

  // ========== TRADING DECISION ==========
  async function renderTD(box) {
    box.innerHTML = '<div style="color:#94a3b8;padding:40px;text-align:center;">Generating trading analysis...</div>';
    let data;
    try { const r = await fetch("/api/trading_analysis"); data = await r.json(); }
    catch (e) { box.innerHTML = `<div style="color:${C.red};padding:20px;">Error: ${e.message}</div>`; return; }

    box.innerHTML = "";
    const v = data.verdict, conf = data.confidence, pts = data.analysis_points || [];
    const vc = v === "BULLISH" ? C.green : v === "BEARISH" ? C.red : C.amber;

    // Verdict
    const vBox = el("div", { style: { background: `linear-gradient(135deg, ${C.card}, ${vc}10)`, border: `2px solid ${vc}`, borderRadius: "12px", padding: "24px", textAlign: "center", marginBottom: "16px" } });
    vBox.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, marginBottom: "4px", letterSpacing: "1px" } }, "COMBINED COT + CONTRACT ANALYSIS"));
    vBox.appendChild(el("div", { style: { fontSize: "32px", fontWeight: "800", color: vc, marginBottom: "4px" } }, v));
    vBox.appendChild(el("div", { style: { fontSize: "14px", color: C.muted } }, `Confidence: ${conf}%`));
    const bar = el("div", { style: { height: "6px", background: "#1e293b", borderRadius: "3px", maxWidth: "200px", margin: "8px auto 0" } });
    bar.appendChild(el("div", { style: { height: "100%", width: conf + "%", background: vc, borderRadius: "3px" } }));
    vBox.appendChild(bar);
    box.appendChild(vBox);

    // Analysis points in 2-col layout
    const grid = el("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" } });
    const leftPts = [], rightPts = [], recPts = [];
    let inRec = false;
    pts.forEach(p => {
      if (p.startsWith("\n**")) { inRec = true; recPts.push(p); }
      else if (inRec) { recPts.push(p); }
      else if (p.includes("CONTRACT ROLL") || p.includes("CO1") || p.includes("CO2") || p.includes("Volume") || p.includes("Open Interest") || p.includes("Spread") || p.includes("roll")) { rightPts.push(p); }
      else { leftPts.push(p); }
    });

    function makePointsList(items) {
      const d = el("div", { style: { lineHeight: "1.7" } });
      items.forEach(p => {
        const isH = p.includes("CONTRACT ROLL");
        d.appendChild(el("div", { style: { fontSize: "12px", color: isH ? C.amber : C.text, fontWeight: isH ? "600" : "400", paddingLeft: "8px", borderLeft: `2px solid ${C.border}`, marginBottom: "6px" } }, (isH ? "⚡ " : "• ") + p));
      });
      return d;
    }

    grid.appendChild(card("COT & Money Positioning", makePointsList(leftPts)));
    grid.appendChild(card("Contract Roll & Volume/OI", makePointsList(rightPts)));
    box.appendChild(grid);

    // Recommendation
    if (recPts.length > 0) {
      const recDiv = el("div", { style: { lineHeight: "1.7" } });
      recPts.forEach(p => {
        if (p.startsWith("\n**")) recDiv.appendChild(el("div", { style: { fontSize: "15px", fontWeight: "700", color: vc, marginBottom: "6px" } }, p.replace(/\*\*/g, "").replace(/\n/g, "")));
        else recDiv.appendChild(el("div", { style: { fontSize: "13px", color: C.text } }, p));
      });
      box.appendChild(card(null, recDiv, { border: `2px solid ${vc}`, background: `linear-gradient(135deg, ${C.card}, ${vc}08)` }));
    }

    box.appendChild(el("div", { style: { fontSize: "10px", color: C.muted, textAlign: "right", marginTop: "8px" } }, `Generated: ${data.generated_at || ""}`));
  }

  // ========== PRICING (flat prices, cracks, OTC swaps) ==========
  async function renderPricing(box) {
    box.innerHTML = '<div style="color:#94a3b8;padding:40px;text-align:center;">Loading pricing…</div>';
    let meta;
    try { const r = await fetch("/api/pricing/groups"); if (!r.ok) throw new Error(await r.text()); meta = await r.json(); }
    catch (e) { box.innerHTML = `<div style="color:${C.red};padding:20px;">Failed to load pricing: ${e.message}</div>`; return; }
    await new Promise(res => loadPlotly(res));
    box.innerHTML = "";

    const groups = meta.groups || [];
    if (!groups.length) { box.innerHTML = `<div style="color:${C.muted};padding:20px;">No pricing data.</div>`; return; }

    // Header
    const prHdr = el("div", { style: { display: "flex", alignItems: "center", gap: "10px", marginBottom: "3px", flexWrap: "wrap" } });
    prHdr.appendChild(el("div", { style: { fontSize: "16px", fontWeight: "800", color: C.amber } }, "🏷️ PRICING — Futures, Cracks & OTC Swaps"));
    prHdr.appendChild(liveBadge());
    box.appendChild(prHdr);
    box.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, marginBottom: "12px" } },
      `Bloomberg settlements + live intraday when the bridge is running · ${groups.reduce((a, g) => a + g.n_series, 0)} series across ${groups.length} books`));

    // Sub-tab selector (portfolio-style)
    const selRow = el("div", { style: { display: "flex", gap: "6px", flexWrap: "wrap", marginBottom: "14px" } });
    box.appendChild(selRow);
    const body = el("div", {});
    box.appendChild(body);

    let current = groups[0].sheet;
    const cache = {};

    // Range control
    let rangeYears = 3;

    async function drawGroup() {
      body.innerHTML = '<div style="color:#94a3b8;padding:30px;text-align:center;">Loading…</div>';
      let gd = cache[current];
      if (!gd) {
        try { const r = await fetch(`/api/pricing/data?group=${encodeURIComponent(current)}`); gd = await r.json(); cache[current] = gd; }
        catch (e) { body.innerHTML = `<div style="color:${C.red};padding:20px;">Error: ${e.message}</div>`; return; }
      }
      body.innerHTML = "";
      body.appendChild(el("div", { style: { fontSize: "13px", fontWeight: "700", color: C.text, marginBottom: "2px" } }, gd.title));

      // Range toggle
      const rc = el("div", { style: { display: "flex", gap: "6px", margin: "8px 0 14px" } });
      [["1Y", 1], ["3Y", 3], ["5Y", 5], ["All", 99]].forEach(([lbl, yr]) => {
        const b = el("button", {
          style: { padding: "4px 12px", border: yr === rangeYears ? `2px solid ${C.amber}` : "1px solid #334155", background: yr === rangeYears ? C.amber + "22" : C.card, color: yr === rangeYears ? C.amber : C.text, borderRadius: "6px", cursor: "pointer", fontSize: "11px", fontWeight: "600" },
          onClick: () => { rangeYears = yr; drawGroup(); }
        });
        b.textContent = lbl; rc.appendChild(b);
      });
      body.appendChild(rc);

      const cutoff = new Date(); cutoff.setFullYear(cutoff.getFullYear() - rangeYears);
      const cutStr = rangeYears >= 99 ? "0000-00-00" : cutoff.toISOString().slice(0, 10);

      const grid = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: "12px" } });
      body.appendChild(grid);

      const plots = [];
      const liveMap = {};
      gd.series.forEach((s, i) => {
        // slice by range
        let xs = s.dates, ys = s.values;
        if (rangeYears < 99) {
          const st = xs.findIndex(d => d >= cutStr);
          if (st > 0) { xs = xs.slice(st); ys = ys.slice(st); }
        }
        if (!xs.length) return;
        const last = ys[ys.length - 1];
        const prev = ys.length > 1 ? ys[ys.length - 2] : last;
        const chg = last - prev;
        const chgC = chg >= 0 ? C.green : C.red;
        const isDiff = /-|crk|spd|arb|hogo|net/i.test(s.label);
        const cardEl = el("div", { style: { background: C.card, border: "1px solid #1e293b", borderRadius: "8px", padding: "10px" } });
        const th = el("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "4px" } });
        th.appendChild(el("div", { style: { fontSize: "12px", fontWeight: "700", color: C.text } }, s.label));
        const valEl = el("div", { style: { fontSize: "11px", fontWeight: "700", color: chgC, borderRadius: "3px", padding: "0 2px", transition: "background .4s" } }, `${last.toFixed(2)} (${chg >= 0 ? "+" : ""}${chg.toFixed(2)})`);
        th.appendChild(valEl);
        cardEl.appendChild(th);
        liveMap[s.label] = { valEl, prev: prev, ref: last };
        cardEl.appendChild(el("div", { style: { fontSize: "9px", color: C.muted, marginBottom: "4px" } }, s.ticker));
        const pd = el("div", { id: `pr-${current.replace(/\s/g, "")}-${i}`, style: { width: "100%", height: "180px" } });
        cardEl.appendChild(pd);
        grid.appendChild(cardEl);
        plots.push({ id: pd.id, xs, ys, isDiff });
      });

      requestAnimationFrame(() => {
        const lay = {
          paper_bgcolor: "transparent", plot_bgcolor: "transparent",
          font: { color: C.text, size: 9 }, margin: { l: 44, r: 8, t: 6, b: 26 },
          xaxis: { gridcolor: "#1e293b", linecolor: "#334155", tickfont: { size: 8 } },
          yaxis: { gridcolor: "#1e293b", linecolor: "#334155", tickfont: { size: 8 }, zeroline: true, zerolinecolor: "#334155" },
          showlegend: false, hovermode: "x unified",
        };
        const cfg = { responsive: true, displayModeBar: false };
        plots.forEach(p => {
          Plotly.newPlot(p.id, [{
            x: p.xs, y: p.ys, type: "scatter", mode: "lines",
            line: { color: p.isDiff ? C.purple : C.cyan, width: 1.3 },
            fill: p.isDiff ? "tozeroy" : "none", fillcolor: C.purple + "14",
          }], lay, cfg);
        });
      });

      // Live intraday updates: patch each series' front value as the bridge
      // pushes fresh Bloomberg ticks (green/red flash on change).
      if (window.__prTimer) clearTimeout(window.__prTimer);
      const drawToken = {};
      window.__prDrawToken = drawToken;
      async function pollLive() {
        if (window.__prDrawToken !== drawToken || !document.body.contains(body)) return;
        try {
          const r = await fetch("/api/pricing/live");
          const ld = await r.json();
          const ticks = ld.ticks || {};
          Object.entries(liveMap).forEach(([label, m]) => {
            const tk = ticks[label];
            if (!tk || tk.value == null) return;
            const v = Number(tk.value);
            const chg = v - m.prev;
            m.valEl.textContent = `${v.toFixed(2)} (${chg >= 0 ? "+" : ""}${chg.toFixed(2)})`;
            m.valEl.style.color = chg >= 0 ? C.green : C.red;
            if (v !== m.ref) {
              m.valEl.style.background = (v > m.ref ? C.green : C.red) + "44";
              setTimeout(() => { m.valEl.style.background = "transparent"; }, 500);
            }
            m.ref = v;
          });
        } catch (e) { /* ignore */ }
        window.__prTimer = setTimeout(pollLive, 5000);
      }
      pollLive();
    }

    groups.forEach(g => {
      const b = el("button", {
        style: { padding: "7px 14px", border: "1px solid #334155", background: C.card, color: C.text, borderRadius: "6px", cursor: "pointer", fontSize: "11px", fontWeight: "600" },
        onClick: () => { current = g.sheet; [...selRow.children].forEach((c, idx) => { const on = groups[idx].sheet === current; c.style.border = on ? `2px solid ${C.amber}` : "1px solid #334155"; c.style.background = on ? C.amber + "22" : C.card; c.style.color = on ? C.amber : C.text; }); drawGroup(); }
      });
      b.textContent = `${g.sheet} (${g.n_series})`;
      selRow.appendChild(b);
    });
    // activate first
    selRow.children[0].style.border = `2px solid ${C.amber}`;
    selRow.children[0].style.background = C.amber + "22";
    selRow.children[0].style.color = C.amber;
    drawGroup();
  }

  // ========== GASOLINE STOCKS EIA ==========
  async function renderGS(box) {
    box.innerHTML = '<div style="color:#94a3b8;padding:40px;text-align:center;">Loading EIA Gasoline Stocks data...</div>';
    let data;
    try { const r = await fetch("/api/eia_gasoline_stocks?start=2020-01-01&end=2026-12-31&length=5000"); if (!r.ok) { const e = await r.json(); throw new Error(e.detail || r.statusText); } data = await r.json(); }
    catch (e) { box.innerHTML = `<div style="color:${C.red};padding:20px;">Error: ${e.message}</div>`; return; }

    box.innerHTML = "";
    const products = data.products || {};
    const summary = data.summary || {};
    const seasonal = data.seasonal || {};
    const prodNames = data.product_names || {};

    // Title
    box.appendChild(el("div", { style: { fontSize: "15px", fontWeight: "700", color: C.amber, marginBottom: "4px" } }, "EIA GASOLINE STOCKS — Weekly Petroleum Stocks"));
    box.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, marginBottom: "14px" } }, `Latest: ${data.latest_date || "N/A"} | Records: ${data.total_records || 0} | Source: EIA API v2`));

    // Key Summary Stats
    const keyProducts = ["EPM0", "EPM0F", "EPOBG", "EPM0R", "EPM0C", "EPOOXE"];
    const availableKey = keyProducts.filter(k => summary[k]);
    if (availableKey.length > 0) {
      const statsGrid = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "8px", marginBottom: "16px" } });
      availableKey.forEach(pid => {
        const s = summary[pid];
        const chgColor = s.change > 0 ? C.green : s.change < 0 ? C.red : C.muted;
        const diffColor = s.diff_from_avg > 0 ? C.green : s.diff_from_avg < 0 ? C.red : C.muted;
        const miniCard = el("div", { style: { background: C.card, border: `1px solid ${C.border}`, borderRadius: "8px", padding: "12px" } });
        miniCard.appendChild(el("div", { style: { fontSize: "10px", color: C.amber, fontWeight: "600", marginBottom: "6px", textTransform: "uppercase" } }, s.product_name));
        miniCard.appendChild(el("div", { style: { fontSize: "18px", fontWeight: "700", color: C.text } }, (s.latest / 1000).toFixed(1) + " M bbl"));
        const detailRow = el("div", { style: { display: "flex", justifyContent: "space-between", marginTop: "6px" } });
        detailRow.appendChild(el("span", { style: { fontSize: "10px", color: chgColor } }, `WoW: ${s.change > 0 ? "+" : ""}${(s.change / 1000).toFixed(1)}M`));
        detailRow.appendChild(el("span", { style: { fontSize: "10px", color: diffColor } }, `vs 5Y Avg: ${s.diff_from_avg > 0 ? "+" : ""}${(s.diff_from_avg / 1000).toFixed(1)}M`));
        miniCard.appendChild(detailRow);
        const rangeRow = el("div", { style: { fontSize: "9px", color: C.muted, marginTop: "4px" } });
        rangeRow.textContent = `52w Range: ${(s.min_52w / 1000).toFixed(1)}M — ${(s.max_52w / 1000).toFixed(1)}M`;
        miniCard.appendChild(rangeRow);
        statsGrid.appendChild(miniCard);
      });
      box.appendChild(card("Key Metrics", statsGrid));
    }

    // Charts section
    const chartGrid = el("div", { style: { display: "grid", gridTemplateColumns: "1fr", gap: "12px" } });

    // Total Motor Gasoline chart
    const ch1 = el("div", { id: "gs-ch1", style: { width: "100%", height: "500px" } });
    chartGrid.appendChild(card("Total Motor Gasoline Stocks (EPM0)", ch1));

    // Finished vs Blending Components
    const ch2 = el("div", { id: "gs-ch2", style: { width: "100%", height: "500px" } });
    chartGrid.appendChild(card("Finished vs Blending Components", ch2));

    // Conventional vs Reformulated
    const ch3 = el("div", { id: "gs-ch3", style: { width: "100%", height: "500px" } });
    chartGrid.appendChild(card("Conventional vs Reformulated", ch3));

    // Week-over-Week changes
    const ch4 = el("div", { id: "gs-ch4", style: { width: "100%", height: "500px" } });
    chartGrid.appendChild(card("Weekly Stock Changes (Total Gasoline)", ch4));

    box.appendChild(chartGrid);

    // Seasonal pattern chart
    if (Object.keys(seasonal).length > 0) {
      const ch5 = el("div", { id: "gs-ch5", style: { width: "100%", height: "500px" } });
      box.appendChild(card("Seasonal Pattern — Total Motor Gasoline (Weekly Average)", ch5));
    }

    // PADD breakdown
    const paddData = data.padd_data || {};
    if (Object.keys(paddData).length > 0) {
      const ch6 = el("div", { id: "gs-ch6", style: { width: "100%", height: "500px" } });
      box.appendChild(card("PADD Regional Breakdown — Total Gasoline Stocks", ch6));

      // PADD summary cards
      const paddGrid = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "6px", marginBottom: "12px" } });
      const paddColors = { "PADD 1": C.blue, "PADD 2": C.green, "PADD 3": C.amber, "PADD 4": C.purple, "PADD 5": C.cyan, "PADD 1A": "#60a5fa", "PADD 1B": "#34d399", "PADD 1C": "#a78bfa" };
      Object.entries(paddData).sort((a, b) => (b[1].latest || 0) - (a[1].latest || 0)).forEach(([area, pd]) => {
        const mc = el("div", { style: { background: C.card, border: `1px solid ${C.border}`, borderRadius: "6px", padding: "8px", textAlign: "center" } });
        mc.appendChild(el("div", { style: { fontSize: "9px", color: paddColors[area] || C.muted, fontWeight: "600" } }, area));
        mc.appendChild(el("div", { style: { fontSize: "14px", fontWeight: "700", color: C.text } }, (pd.latest / 1000).toFixed(1) + "M"));
        if (pd.change != null) {
          const cc = pd.change > 0 ? C.green : pd.change < 0 ? C.red : C.muted;
          mc.appendChild(el("div", { style: { fontSize: "9px", color: cc } }, `${pd.change > 0 ? "+" : ""}${(pd.change / 1000).toFixed(1)}M`));
        }
        paddGrid.appendChild(mc);
      });
      box.appendChild(card("PADD Latest Values", paddGrid));
    }

    // Detailed table
    const tableData = Object.entries(summary).sort((a, b) => (b[1].latest || 0) - (a[1].latest || 0));
    if (tableData.length > 0) {
      const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px" } });
      const thead = el("thead");
      const hRow = el("tr");
      ["Product", "Latest (M bbl)", "WoW Change", "% Change", "5Y Avg", "vs Avg", "52w Low", "52w High"].forEach(h => {
        hRow.appendChild(el("th", { style: { padding: "8px 6px", textAlign: "right", color: C.amber, borderBottom: `1px solid ${C.border}`, fontSize: "10px", fontWeight: "600" } }, h));
      });
      hRow.children[0].style.textAlign = "left";
      thead.appendChild(hRow);
      tbl.appendChild(thead);
      const tbody = el("tbody");
      tableData.forEach(([pid, s]) => {
        const row = el("tr", { style: { borderBottom: `1px solid ${C.border}20` } });
        const chgColor = s.change > 0 ? C.green : s.change < 0 ? C.red : C.muted;
        const cells = [
          { v: s.product_name, align: "left", color: C.text },
          { v: (s.latest / 1000).toFixed(1), align: "right", color: C.text },
          { v: `${s.change > 0 ? "+" : ""}${(s.change / 1000).toFixed(1)}`, align: "right", color: chgColor },
          { v: `${s.pct_change > 0 ? "+" : ""}${s.pct_change.toFixed(2)}%`, align: "right", color: chgColor },
          { v: (s.avg_5y / 1000).toFixed(1), align: "right", color: C.muted },
          { v: `${s.diff_from_avg > 0 ? "+" : ""}${(s.diff_from_avg / 1000).toFixed(1)}`, align: "right", color: s.diff_from_avg > 0 ? C.green : C.red },
          { v: (s.min_52w / 1000).toFixed(1), align: "right", color: C.muted },
          { v: (s.max_52w / 1000).toFixed(1), align: "right", color: C.muted },
        ];
        cells.forEach(c => {
          row.appendChild(el("td", { style: { padding: "6px", textAlign: c.align, color: c.color } }, c.v));
        });
        tbody.appendChild(row);
      });
      tbl.appendChild(tbody);
      box.appendChild(card("Detailed Stock Levels", tbl));
    }

    // Draw charts
    loadPlotly(() => {
      // Chart 1: Total Motor Gasoline
      if (products["EPM0"]) {
        const p = products["EPM0"];
        Plotly.newPlot("gs-ch1", [
          { x: p.dates, y: p.values.map(v => v ? v / 1000 : null), name: "Total Motor Gasoline", line: { color: C.cyan, width: 2.5 } },
        ], { ...plotLayout, height: 500, yaxis: { ...plotLayout.yaxis, title: { text: "Million Barrels", font: { size: 13 } } }, title: { text: "Total Motor Gasoline Stocks", font: { color: C.amber, size: 15 }, x: 0.02, xanchor: 'left' } }, { responsive: true });
      }

      // Chart 2: Finished vs Blending
      const traces2 = [];
      if (products["EPM0F"]) traces2.push({ x: products["EPM0F"].dates, y: products["EPM0F"].values.map(v => v ? v / 1000 : null), name: "Finished Gasoline", line: { color: C.green, width: 2.5 } });
      if (products["EPOBG"]) traces2.push({ x: products["EPOBG"].dates, y: products["EPOBG"].values.map(v => v ? v / 1000 : null), name: "Blending Components", line: { color: C.purple, width: 2.5 } });
      if (traces2.length > 0) Plotly.newPlot("gs-ch2", traces2, { ...plotLayout, height: 500, yaxis: { ...plotLayout.yaxis, title: { text: "Million Barrels", font: { size: 13 } } }, title: { text: "Finished vs Blending Components", font: { color: C.amber, size: 15 }, x: 0.02, xanchor: 'left' } }, { responsive: true });

      // Chart 3: Conventional vs Reformulated
      const traces3 = [];
      if (products["EPM0C"]) traces3.push({ x: products["EPM0C"].dates, y: products["EPM0C"].values.map(v => v ? v / 1000 : null), name: "Conventional", line: { color: C.blue, width: 2.5 } });
      if (products["EPM0R"]) traces3.push({ x: products["EPM0R"].dates, y: products["EPM0R"].values.map(v => v ? v / 1000 : null), name: "Reformulated", line: { color: C.amber, width: 2.5 } });
      if (traces3.length > 0) Plotly.newPlot("gs-ch3", traces3, { ...plotLayout, height: 500, yaxis: { ...plotLayout.yaxis, title: { text: "Million Barrels", font: { size: 13 } } }, title: { text: "Conventional vs Reformulated", font: { color: C.amber, size: 15 }, x: 0.02, xanchor: 'left' } }, { responsive: true });

      // Chart 4: WoW changes
      if (products["EPM0"]) {
        const p = products["EPM0"];
        const changes = [];
        const chDates = [];
        for (let i = 1; i < p.values.length; i++) {
          if (p.values[i] != null && p.values[i - 1] != null) {
            changes.push((p.values[i] - p.values[i - 1]) / 1000);
            chDates.push(p.dates[i]);
          }
        }
        const barColors = changes.map(c => c > 0 ? C.green : C.red);
        Plotly.newPlot("gs-ch4", [
          { x: chDates, y: changes, type: "bar", marker: { color: barColors }, name: "Weekly Change" },
        ], { ...plotLayout, height: 500, yaxis: { ...plotLayout.yaxis, title: { text: "Change (M bbl)", font: { size: 13 } } }, title: { text: "Weekly Stock Changes (Total Gasoline)", font: { color: C.amber, size: 15 }, x: 0.02, xanchor: 'left' } }, { responsive: true });
      }

      // Chart 5: Seasonal
      if (Object.keys(seasonal).length > 0) {
        const weeks = Object.keys(seasonal).map(Number).sort((a, b) => a - b);
        Plotly.newPlot("gs-ch5", [
          { x: weeks, y: weeks.map(w => seasonal[w] / 1000), name: "Avg Stocks by Week", fill: "tozeroy", line: { color: C.cyan, width: 2.5 }, fillcolor: `${C.cyan}20` },
        ], { ...plotLayout, height: 500, xaxis: { ...plotLayout.xaxis, title: { text: "Week of Year", font: { size: 13 } } }, yaxis: { ...plotLayout.yaxis, title: { text: "Avg M bbl", font: { size: 13 } } }, title: { text: "Seasonal Pattern — Total Motor Gasoline", font: { color: C.amber, size: 15 }, x: 0.02, xanchor: 'left' } }, { responsive: true });
      }

      // Chart 6: PADD breakdown stacked area
      const paddData2 = data.padd_data || {};
      if (Object.keys(paddData2).length > 0) {
        const paddColors2 = { "PADD 1": C.blue, "PADD 2": C.green, "PADD 3": C.amber, "PADD 4": C.purple, "PADD 5": C.cyan };
        const paddTraces = [];
        ["PADD 1", "PADD 2", "PADD 3", "PADD 4", "PADD 5"].forEach(area => {
          if (paddData2[area]) {
            paddTraces.push({
              x: paddData2[area].dates,
              y: paddData2[area].values.map(v => v ? v / 1000 : null),
              name: area,
              stackgroup: "one",
              line: { color: paddColors2[area], width: 0.5 },
            });
          }
        });
        if (paddTraces.length > 0) {
          Plotly.newPlot("gs-ch6", paddTraces, { ...plotLayout, height: 500, yaxis: { ...plotLayout.yaxis, title: { text: "Million Barrels", font: { size: 13 } } }, title: { text: "PADD Regional Breakdown — Total Gasoline Stocks", font: { color: C.amber, size: 15 }, x: 0.02, xanchor: 'left' } }, { responsive: true });
        }
      }
    });

    // Weekly balance & forecast table + trend predictions (EA forecast data)
    box.appendChild(el("div", { style: { fontSize: "14px", fontWeight: "700", color: C.amber, margin: "18px 0 10px" } }, "📅 WEEKLY BALANCE & FORECAST — actual + predicted stock path"));
    usWeeklyForecastBlock(box);
  }

  // ========== GASOLINE BALANCES (Monthly S&D + Multi-Year Overlay) ==========
  let gbCurrentArea = "US";
  let gbStartYear = 2015;
  let gbEndYear = 2026;
  let gbData = null;

  async function fetchGB(area, sy, ey) {
    const r = await fetch(`/api/eia_gasoline_balances?area=${area}&start_year=${sy}&end_year=${ey}`);
    if (!r.ok) { const e = await r.json(); throw new Error(e.detail || r.statusText); }
    return await r.json();
  }

  const yearColors = ["#3b82f6","#10b981","#f59e0b","#ef4444","#8b5cf6","#06b6d4","#f472b6","#a3e635","#fb923c","#67e8f9","#e879f9","#fbbf24","#34d399","#f87171","#818cf8","#2dd4bf"];

  function renderGBContent(box, data) {
    box.innerHTML = "";
    const sndTable = data.snd_table || [];
    const overlay = data.seasonal_overlay || {};
    const chartSeries = data.chart_series || {};
    const products = data.products || [];

    // Header
    box.appendChild(el("div", { style: { fontSize: "15px", fontWeight: "700", color: C.amber, marginBottom: "4px" } }, `GASOLINE S&D BALANCE — ${data.area_name || data.area} (${data.start_year}–${data.end_year})`));
    box.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, marginBottom: "14px" } }, "Source: EIA Monthly Supply & Disposition (API v2 /petroleum/sum/snd/) | 8 Products × 7 Processes"));

    // ---- S&D BALANCE TABLE ----
    const procOrder = ["YPR","YIR","YNP","VPP","VUA","SCG","SAE"];
    const procHeaders = { YPR: "Production", YIR: "Net Input", YNP: "Renew. Prod", VPP: "Demand", VUA: "Adj.", SCG: "Stk Change", SAE: "End Stocks" };
    const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px", marginBottom: "8px" } });
    const hd = el("thead");
    const hr = el("tr");
    ["Product", ...procOrder.map(p => procHeaders[p]), "Units"].forEach((h, i) => {
      hr.appendChild(el("th", { style: { padding: "6px 4px", textAlign: i === 0 ? "left" : "right", color: C.amber, borderBottom: `2px solid ${C.border}`, fontSize: "10px", fontWeight: "600", whiteSpace: "nowrap" } }, h));
    });
    hd.appendChild(hr);
    tbl.appendChild(hd);
    const tb = el("tbody");

    sndTable.forEach(row => {
      const procs = row.processes || {};
      const tr = el("tr", { style: { borderBottom: `1px solid ${C.border}20` } });
      tr.appendChild(el("td", { style: { padding: "4px 4px", color: C.cyan, fontWeight: "600", fontSize: "11px", whiteSpace: "nowrap" } }, row.product_name));
      let unitStr = "";
      procOrder.forEach(pc => {
        const p = procs[pc];
        if (p) {
          const v = p.latest;
          const isStk = pc === "SAE";
          const isSC = pc === "SCG";
          let color = C.text;
          let val = "";
          if (isSC) {
            color = v > 0 ? C.green : v < 0 ? C.red : C.muted;
            val = (v > 0 ? "+" : "") + v.toLocaleString();
          } else if (isStk) {
            val = v > 10000 ? (v / 1000).toFixed(1) + "M" : v.toLocaleString();
          } else {
            val = v.toLocaleString();
          }
          if (!unitStr) unitStr = p.units === "MBBL/D" ? "MBBL/D" : p.units === "MBBL" ? "MBBL" : p.units;
          tr.appendChild(el("td", { style: { padding: "4px", textAlign: "right", color, fontSize: "10px", fontWeight: isSC ? "600" : "400" } }, val));
        } else {
          tr.appendChild(el("td", { style: { padding: "4px", textAlign: "right", color: C.muted, fontSize: "10px" } }, "—"));
        }
      });
      tr.appendChild(el("td", { style: { padding: "4px", textAlign: "right", color: C.muted, fontSize: "9px" } }, unitStr));
      tb.appendChild(tr);
    });
    tbl.appendChild(tb);
    box.appendChild(card("Monthly Supply & Demand Balance", tbl));

    // ---- DETAILS EXPANSION: per-product MoM, 5Y avg ----
    const detTbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "10px" } });
    const dh = el("thead");
    const dhr = el("tr");
    ["Product", "Process", "Latest", "MoM", "% Chg", "5Y Avg", "vs Avg", "12m Low", "12m High"].forEach((h, i) => {
      dhr.appendChild(el("th", { style: { padding: "4px 3px", textAlign: i < 2 ? "left" : "right", color: C.amber, borderBottom: `2px solid ${C.border}`, fontSize: "9px", fontWeight: "600" } }, h));
    });
    dh.appendChild(dhr);
    detTbl.appendChild(dh);
    const dtb = el("tbody");
    sndTable.forEach(row => {
      Object.entries(row.processes || {}).forEach(([pc, p]) => {
        const tr = el("tr", { style: { borderBottom: `1px solid ${C.border}10` } });
        tr.appendChild(el("td", { style: { padding: "3px", color: C.text, fontSize: "9px" } }, row.product_name.substring(0, 25)));
        tr.appendChild(el("td", { style: { padding: "3px", color: C.muted, fontSize: "9px" } }, p.name.substring(0, 20)));
        const cc = p.mom_change > 0 ? C.green : p.mom_change < 0 ? C.red : C.muted;
        const ac = p.vs_avg > 0 ? C.green : p.vs_avg < 0 ? C.red : C.muted;
        [
          { v: p.latest.toLocaleString(), c: C.text },
          { v: (p.mom_change > 0 ? "+" : "") + p.mom_change.toLocaleString(), c: cc },
          { v: (p.pct_change > 0 ? "+" : "") + p.pct_change.toFixed(1) + "%", c: cc },
          { v: p.avg_5y.toLocaleString(), c: C.muted },
          { v: (p.vs_avg > 0 ? "+" : "") + p.vs_avg.toLocaleString(), c: ac },
          { v: p.min_12m.toLocaleString(), c: C.muted },
          { v: p.max_12m.toLocaleString(), c: C.muted },
        ].forEach(cell => {
          tr.appendChild(el("td", { style: { padding: "3px", textAlign: "right", color: cell.c, fontSize: "9px" } }, cell.v));
        });
        dtb.appendChild(tr);
      });
    });
    detTbl.appendChild(dtb);
    box.appendChild(card("Detailed Process Statistics (MoM, 5Y Avg, 12m Range)", detTbl));

    // ---- TIME SERIES CHARTS (full history) ----
    let chIdx = 0;
    const nextId = () => `gb-c-${chIdx++}`;
    const traceColors = [C.cyan, C.green, C.amber, C.purple, C.blue, C.red, "#f472b6", "#a3e635", "#67e8f9", "#fbbf24"];

    const tsGrid = el("div", { style: { display: "grid", gridTemplateColumns: "1fr", gap: "12px", marginBottom: "12px" } });
    const tsCharts = [];

    // Key time-series charts: Production, Demand, Stock Change, Ending Stocks for key products
    const keyProducts = ["EPM0F", "EPM0C", "EPOBG", "EPP2"];
    const keyProcs = [["YPR", "Production"], ["VPP", "Demand"], ["SCG", "Stock Change"], ["SAE", "Ending Stocks"]];
    keyProcs.forEach(([proc, procLabel]) => {
      const cid = nextId();
      const traces = [];
      let ci = 0;
      keyProducts.forEach(prod => {
        const k = `${prod}_${proc}`;
        const s = chartSeries[k];
        if (s) {
          traces.push({ dates: s.dates, values: s.values, name: s.product_name, color: traceColors[ci % 10] });
          ci++;
        }
      });
      if (traces.length > 0) {
        tsCharts.push({ id: cid, traces, yTitle: proc === "SAE" ? "MBBL" : "MBBL/D", proc });
        tsGrid.appendChild(card(`${procLabel} — Key Products`, el("div", { id: cid, style: { width: "100%", height: "500px" } })));
      }
    });
    box.appendChild(tsGrid);

    // ---- SEASONAL MULTI-YEAR OVERLAY CHARTS ----
    box.appendChild(el("div", { style: { fontSize: "14px", fontWeight: "700", color: C.amber, marginTop: "18px", marginBottom: "10px", borderBottom: `1px solid ${C.border}`, paddingBottom: "6px" } }, "SEASONAL PATTERNS — Multi-Year Overlay (each line = one year)"));

    const seasonalGrid = el("div", { style: { display: "grid", gridTemplateColumns: "1fr", gap: "12px" } });
    const seasonalCharts = [];

    // Create overlay charts for important product+process combinations
    const overlayKeys = Object.keys(overlay).sort();
    overlayKeys.forEach(ok => {
      const ov = overlay[ok];
      const years = Object.keys(ov.years).sort();
      if (years.length < 2) return;
      const cid = nextId();
      seasonalCharts.push({ id: cid, data: ov, key: ok });
      const title = `${ov.product_name} — ${ov.process_name}`;
      seasonalGrid.appendChild(card(title, el("div", { id: cid, style: { width: "100%", height: "500px" } })));
    });
    box.appendChild(seasonalGrid);

    // ---- DRAW ALL CHARTS ----
    loadPlotly(() => {
      // Time-series charts
      tsCharts.forEach(({ id, traces, yTitle, proc }) => {
        const pTraces = traces.map(t => ({
          x: t.dates, y: t.values, name: t.name, type: "scatter",
          line: { color: t.color, width: 2.5 },
        }));
        const layout = { ...plotLayout, height: 500, yaxis: { ...plotLayout.yaxis, title: { text: yTitle, font: { size: 13 } } }, title: { text: `${proc === 'YPR' ? 'Production' : proc === 'VPP' ? 'Demand' : proc === 'SCG' ? 'Stock Change' : 'Ending Stocks'} — Key Products`, font: { color: C.amber, size: 15 }, x: 0.02, xanchor: 'left' } };
        if (proc === "SCG") layout.shapes = [{ type: "line", x0: 0, x1: 1, xref: "paper", y0: 0, y1: 0, line: { color: C.muted, width: 1, dash: "dot" } }];
        Plotly.newPlot(id, pTraces, layout, { responsive: true });
      });

      // Multi-year overlay seasonal charts
      seasonalCharts.forEach(({ id, data: ov }) => {
        const years = Object.keys(ov.years).sort();
        const months = ov.months;
        const traces = years.map((yr, i) => ({
          x: months,
          y: ov.years[yr],
          name: yr,
          type: "scatter",
          mode: "lines+markers",
          line: { color: yearColors[i % yearColors.length], width: yr === years[years.length - 1] ? 3.5 : 2 },
          marker: { size: yr === years[years.length - 1] ? 7 : 4 },
          opacity: yr === years[years.length - 1] ? 1 : 0.7,
        }));
        Plotly.newPlot(id, traces, {
          ...plotLayout,
          height: 500,
          xaxis: { ...plotLayout.xaxis, type: "category", categoryorder: "array", categoryarray: months, title: "Month" },
          yaxis: { ...plotLayout.yaxis, title: ov.units },
          legend: { font: { size: 11, color: C.text }, orientation: "h", y: -0.12 },
          showlegend: true,
        }, { responsive: true });
      });
    });
  }

  async function renderGBal(box) {
    box.innerHTML = "";

    // Controls: PADD Dropdown + Year Range
    const controls = el("div", { style: { display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px", flexWrap: "wrap" } });
    controls.appendChild(el("span", { style: { fontSize: "12px", color: C.muted, fontWeight: "600" } }, "REGION:"));
    const select = el("select", { style: { background: C.card, color: C.text, border: `1px solid ${C.border}`, borderRadius: "6px", padding: "8px 12px", fontSize: "12px", cursor: "pointer", minWidth: "200px" } });
    const areas = { US: "U.S. Total", PADD1: "East Coast (PADD 1)", PADD2: "Midwest (PADD 2)", PADD3: "Gulf Coast (PADD 3)", PADD4: "Rocky Mountain (PADD 4)", PADD5: "West Coast (PADD 5)" };
    Object.entries(areas).forEach(([k, v]) => {
      const opt = el("option", { value: k }, v);
      if (k === gbCurrentArea) opt.selected = true;
      select.appendChild(opt);
    });
    controls.appendChild(select);

    // Year range selectors
    controls.appendChild(el("span", { style: { fontSize: "12px", color: C.muted, fontWeight: "600", marginLeft: "12px" } }, "FROM:"));
    const startYrSel = el("select", { style: { background: C.card, color: C.text, border: `1px solid ${C.border}`, borderRadius: "6px", padding: "8px 10px", fontSize: "12px", cursor: "pointer" } });
    for (let y = 2000; y <= 2026; y++) {
      const opt = el("option", { value: String(y) }, String(y));
      if (y === gbStartYear) opt.selected = true;
      startYrSel.appendChild(opt);
    }
    controls.appendChild(startYrSel);

    controls.appendChild(el("span", { style: { fontSize: "12px", color: C.muted, fontWeight: "600" } }, "TO:"));
    const endYrSel = el("select", { style: { background: C.card, color: C.text, border: `1px solid ${C.border}`, borderRadius: "6px", padding: "8px 10px", fontSize: "12px", cursor: "pointer" } });
    for (let y = 2000; y <= 2026; y++) {
      const opt = el("option", { value: String(y) }, String(y));
      if (y === gbEndYear) opt.selected = true;
      endYrSel.appendChild(opt);
    }
    controls.appendChild(endYrSel);

    const loadBtn = el("button", { style: { background: C.amber, color: "#000", border: "none", borderRadius: "6px", padding: "8px 20px", fontWeight: "700", fontSize: "12px", cursor: "pointer" }, onClick: async () => {
      gbCurrentArea = select.value;
      gbStartYear = parseInt(startYrSel.value);
      gbEndYear = parseInt(endYrSel.value);
      contentBox.innerHTML = '<div style="color:#94a3b8;padding:40px;text-align:center;">Loading gasoline balances for ' + areas[gbCurrentArea] + ' (' + gbStartYear + '–' + gbEndYear + ')...</div>';
      try {
        gbData = await fetchGB(gbCurrentArea, gbStartYear, gbEndYear);
        renderGBContent(contentBox, gbData);
      } catch (e) { contentBox.innerHTML = `<div style="color:${C.red};padding:20px;">Error: ${e.message}</div>`; }
      // Also reload monthly table
      monthlyBox.innerHTML = '<div style="color:#94a3b8;padding:20px;text-align:center;font-size:12px;">Loading monthly balance table...</div>';
      try {
        const md = await fetchGBMonthly(gbStartYear, gbEndYear);
        renderGBMonthlyTable(monthlyBox, md);
      } catch (e) { monthlyBox.innerHTML = `<div style="color:${C.red};padding:20px;font-size:12px;">Monthly table: ${e.message}</div>`; }
    } }, "Load Data");
    controls.appendChild(loadBtn);
    box.appendChild(controls);

    const contentBox = el("div");
    box.appendChild(contentBox);

    // Monthly balance table container
    const monthlyBox = el("div");
    box.appendChild(monthlyBox);

    // Auto-load US data + monthly table
    contentBox.innerHTML = '<div style="color:#94a3b8;padding:40px;text-align:center;">Loading gasoline balances for U.S. Total (' + gbStartYear + '–' + gbEndYear + ')...</div>';
    try {
      gbData = await fetchGB(gbCurrentArea, gbStartYear, gbEndYear);
      renderGBContent(contentBox, gbData);
    } catch (e) { contentBox.innerHTML = `<div style="color:${C.red};padding:20px;">Error: ${e.message}</div>`; }
    // Also load monthly balance table
    monthlyBox.innerHTML = '<div style="color:#94a3b8;padding:20px;text-align:center;font-size:12px;">Loading monthly balance table...</div>';
    try {
      const monthlyData = await fetchGBMonthly(gbStartYear, gbEndYear);
      renderGBMonthlyTable(monthlyBox, monthlyData);
    } catch (e) { monthlyBox.innerHTML = `<div style="color:${C.red};padding:20px;font-size:12px;">Monthly table: ${e.message}</div>`; }
  }

  // ========== GASOLINE MONTHLY BALANCE TABLE (Spreadsheet-style) ==========
  async function fetchGBMonthly(sy, ey) {
    const r = await fetch(`/api/eia_gasoline_monthly?start_year=${sy}&end_year=${ey}`);
    if (!r.ok) { const e = await r.json(); throw new Error(e.detail || r.statusText); }
    return await r.json();
  }

  function _buildBalanceTable(periods, pLabels, rows, isSupp, projPeriods) {
    projPeriods = projPeriods || new Set();
    const tableWrap = el("div", { style: { overflowX: "auto", marginBottom: "12px" } });
    const tbl = el("table", { style: { borderCollapse: "collapse", fontSize: "10px", whiteSpace: "nowrap", width: "100%" } });
    const thead = el("thead");
    const hdr = el("tr");
    hdr.appendChild(el("th", { style: { position: "sticky", left: 0, background: C.bg, padding: "6px 8px", textAlign: "left", color: C.amber, borderBottom: `2px solid ${C.border}`, minWidth: "220px", zIndex: 2, fontSize: "10px" } }, ""));
    pLabels.forEach(lbl => {
      hdr.appendChild(el("th", { style: { padding: "5px 6px", textAlign: "right", color: C.amber, borderBottom: `2px solid ${C.border}`, fontSize: "9px", minWidth: "58px" } }, lbl));
    });
    thead.appendChild(hdr);
    tbl.appendChild(thead);
    const tbody = el("tbody");
    rows.forEach(row => {
      const tr = el("tr", { style: { borderBottom: `1px solid ${C.border}20` } });
      const isTotal = row.is_total || false;
      const isBalance = row.is_balance || false;
      const isS = row.is_supplementary || false;
      const labelColor = isTotal ? C.amber : isBalance ? C.green : isS ? C.muted : C.cyan;
      const labelStyle = {
        position: "sticky", left: 0, background: C.bg, padding: "4px 8px",
        color: labelColor, fontWeight: isTotal || isBalance ? "700" : "600",
        fontSize: isS ? "9px" : "10px", zIndex: 1,
        borderTop: isTotal || isBalance ? `1px solid ${C.border}` : "none",
      };
      tr.appendChild(el("td", { style: labelStyle }, row.label));
      periods.forEach(p => {
        const v = row.values[p];
        let vStr = "\u2014";
        let color = C.muted;
        const isProj = projPeriods.has(p);
        if (v !== null && v !== undefined) {
          vStr = Math.abs(v) >= 10000 ? (v / 1000).toFixed(1) + "K" : v.toLocaleString(undefined, { maximumFractionDigits: 0 });
          color = isProj ? C.purple : isBalance ? (v > 0 ? C.green : v < 0 ? C.red : C.muted) : isS ? C.muted : C.text;
        }
        tr.appendChild(el("td", { style: { padding: "3px 6px", textAlign: "right", color, fontSize: isS ? "9px" : "10px",
          borderTop: isTotal || isBalance ? `1px solid ${C.border}` : "none",
          fontWeight: isTotal || isBalance ? "700" : "400",
          fontStyle: isProj ? "italic" : "normal" } }, vStr));
      });
      tbody.appendChild(tr);
    });
    tbl.appendChild(tbody);
    tableWrap.appendChild(tbl);
    return tableWrap;
  }

  function renderGBMonthlyTable(box, data) {
    box.innerHTML = "";
    const sections = data.sections || [];
    if (sections.length === 0) {
      box.appendChild(el("div", { style: { color: C.muted, padding: "30px", textAlign: "center" } }, "No data available."));
      return;
    }

    const monthAbbr = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    let gbmChIdx = 0;
    const gbmNextId = () => `gbm-c-${gbmChIdx++}`;
    const chartsToPlot = [];

    sections.forEach(sec => {
      if (sec.error) {
        box.appendChild(el("div", { style: { color: C.red, padding: "8px", fontSize: "11px" } }, `${sec.area_name}: ${sec.error}`));
        return;
      }
      const periods = sec.periods || [];
      const projPeriods = new Set(sec.projected_periods || []);
      if (periods.length === 0) return;
      const pLabels = periods.map(p => {
        const [y, m] = p.split("-");
        const lbl = monthAbbr[parseInt(m) - 1] + "-" + y.slice(2);
        return projPeriods.has(p) ? lbl + "*" : lbl;
      });

      // Balance table (projected values shown in italic/different color)
      const allRows = [...(sec.balance_rows || []), ...(sec.supplementary_rows || [])];
      const balTbl = _buildBalanceTable(periods, pLabels, allRows, false, projPeriods);
      box.appendChild(card(`${sec.area_name} — Gasoline Balance (kb/d)`, balTbl));

      // Stock levels table
      const sRows = sec.stock_rows || [];
      if (sRows.length > 0) {
        const stWrap = el("div", { style: { overflowX: "auto", marginBottom: "12px" } });
        const stTbl = el("table", { style: { borderCollapse: "collapse", fontSize: "10px", whiteSpace: "nowrap", width: "100%" } });
        const stHead = el("thead");
        const stHr = el("tr");
        stHr.appendChild(el("th", { style: { position: "sticky", left: 0, background: C.bg, padding: "6px 8px", textAlign: "left", color: C.amber, borderBottom: `2px solid ${C.border}`, minWidth: "220px", zIndex: 2, fontSize: "10px" } }, ""));
        pLabels.forEach(lbl => {
          stHr.appendChild(el("th", { style: { padding: "5px 6px", textAlign: "right", color: C.amber, borderBottom: `2px solid ${C.border}`, fontSize: "9px", minWidth: "58px" } }, lbl));
        });
        stHead.appendChild(stHr);
        stTbl.appendChild(stHead);
        const stBody = el("tbody");
        sRows.forEach(row => {
          const tr = el("tr", { style: { borderBottom: `1px solid ${C.border}20` } });
          tr.appendChild(el("td", { style: { position: "sticky", left: 0, background: C.bg, padding: "4px 8px", color: C.cyan, fontWeight: "600", fontSize: "10px", zIndex: 1 } }, row.label));
          periods.forEach(p => {
            const v = row.values[p];
            let vStr = "\u2014";
            const isProj = projPeriods.has(p);
            if (v !== null && v !== undefined) vStr = (v / 1000).toFixed(1);
            tr.appendChild(el("td", { style: { padding: "3px 6px", textAlign: "right", color: isProj ? C.purple : C.text, fontSize: "10px", fontStyle: isProj ? "italic" : "normal" } }, vStr));
          });
          stBody.appendChild(tr);
        });
        stTbl.appendChild(stBody);
        stWrap.appendChild(stTbl);
        box.appendChild(card(`${sec.area_name} — Gasoline Stocks (mmb)`, stWrap));
      }

      // Stock Change bar chart for EVERY area
      const rows = sec.balance_rows || [];
      const scgRow = rows.find(r => r.key === "stock_change");
      if (scgRow) {
        const actX = [], actY = [], actCol = [];
        const projX = [], projY = [], projCol = [];
        periods.forEach(p => {
          const v = scgRow.values[p];
          if (v === null || v === undefined) return;
          if (projPeriods.has(p)) {
            projX.push(p); projY.push(v); projCol.push(v >= 0 ? "#a78bfa" : "#c084fc");
          } else {
            actX.push(p); actY.push(v); actCol.push(v >= 0 ? C.green : C.red);
          }
        });
        const cid = gbmNextId();
        chartsToPlot.push({ id: cid, type: "bar", traces: [
          { x: actX, y: actY, name: "Actual", marker: { color: actCol }, type: "bar" },
          ...(projX.length > 0 ? [{ x: projX, y: projY, name: "Projected (avg)", marker: { color: projCol }, type: "bar", opacity: 0.6 }] : [])
        ], yTitle: "kb/d" });
        box.appendChild(card(`${sec.area_name} — Stock Change (kb/d)`, el("div", { id: cid, style: { width: "100%", height: "300px" } })));
      }

      // Additional charts for US: Production/Demand, Imports/Exports, Stocks
      if (sec.area === "US") {
        const chartConfigs = [
          { title: "US Production vs Demand (kb/d)", keys: ["production", "demand"], colors: [C.cyan, C.red] },
          { title: "US Imports vs Exports (kb/d)", keys: ["imports_finished", "exports_finished"], colors: [C.green, C.red] },
        ];
        const chartsGrid = el("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginBottom: "12px" } });
        chartConfigs.forEach(cfg => {
          const traces = [];
          cfg.keys.forEach((k, i) => {
            const row = rows.find(r => r.key === k);
            if (!row) return;
            // Split actual vs projected
            const actPeriods = periods.filter(p => !projPeriods.has(p));
            const projPeriodsArr = periods.filter(p => projPeriods.has(p));
            const actVals = actPeriods.map(p => row.values[p]);
            const projVals = projPeriodsArr.map(p => row.values[p]);
            if (!actVals.every(v => v === null || v === undefined))
              traces.push({ x: actPeriods, y: actVals, name: row.label, color: cfg.colors[i] || C.text });
            if (projPeriodsArr.length > 0 && !projVals.every(v => v === null || v === undefined))
              traces.push({ x: projPeriodsArr, y: projVals, name: row.label + " (proj)", color: cfg.colors[i] || C.text, dash: "dash" });
          });
          if (traces.length > 0) {
            const cid = gbmNextId();
            chartsToPlot.push({ id: cid, traces });
            chartsGrid.appendChild(card(cfg.title, el("div", { id: cid, style: { width: "100%", height: "350px" } })));
          }
        });
        if (sRows.length > 0) {
          const stockTraces = [];
          const stockColors = [C.cyan, C.green, C.amber];
          const actPeriods = periods.filter(p => !projPeriods.has(p));
          const projPeriodsArr = periods.filter(p => projPeriods.has(p));
          sRows.forEach((row, i) => {
            const actVals = actPeriods.map(p => row.values[p] != null ? row.values[p] / 1000 : null);
            const projVals = projPeriodsArr.map(p => row.values[p] != null ? row.values[p] / 1000 : null);
            if (!actVals.every(v => v === null)) stockTraces.push({ x: actPeriods, y: actVals, name: row.label, color: stockColors[i] || C.text });
            if (projPeriodsArr.length > 0 && !projVals.every(v => v === null))
              stockTraces.push({ x: projPeriodsArr, y: projVals, name: row.label + " (proj)", color: stockColors[i] || C.text, dash: "dash" });
          });
          if (stockTraces.length > 0) {
            const cid = gbmNextId();
            chartsToPlot.push({ id: cid, traces: stockTraces, yTitle: "million barrels" });
            chartsGrid.appendChild(card("US Gasoline Stocks (mmb)", el("div", { id: cid, style: { width: "100%", height: "350px" } })));
          }
        }
        box.appendChild(chartsGrid);
      }
    });

    // Add projection legend
    box.appendChild(el("div", { style: { fontSize: "10px", color: C.muted, padding: "8px 0", textAlign: "center" } },
      "* Projected months — based on seasonal average of same calendar month across available historical years. Purple/italic = projected values."));

    loadPlotly(() => {
      chartsToPlot.forEach(({ id, traces, yTitle, type }) => {
        if (type === "bar") {
          const layout = { ...plotLayout, height: 300, barmode: "group",
            yaxis: { ...plotLayout.yaxis, title: yTitle || "kb/d", zeroline: true, zerolinecolor: C.border },
            showlegend: true, legend: { font: { size: 10, color: C.text }, orientation: "h", y: -0.2 } };
          Plotly.newPlot(id, traces, layout, { responsive: true });
        } else {
          const pTraces = traces.map(t => ({
            x: t.x, y: t.y, name: t.name, type: "scatter",
            line: { color: t.color, width: 2.5, dash: t.dash || "solid" },
          }));
          const layout = { ...plotLayout, height: 350, yaxis: { ...plotLayout.yaxis, title: yTitle || "kb/d" }, showlegend: true, legend: { font: { size: 10, color: C.text }, orientation: "h", y: -0.15 } };
          Plotly.newPlot(id, pTraces, layout, { responsive: true });
        }
      });
    });
  }

  // ========== JODI GASOLINE (Global S&D + Multi-Year Overlay) ==========
  let jodiCountry = "US";
  let jodiStartYear = 2015;
  let jodiEndYear = 2026;
  let jodiData = null;
  let jodiCountries = null;

  async function fetchJODI(country, sy, ey) {
    const r = await fetch(`/api/jodi_gasoline?country=${country}&start_year=${sy}&end_year=${ey}`);
    if (!r.ok) { const e = await r.json(); throw new Error(e.detail || r.statusText); }
    return await r.json();
  }

  function renderJODIContent(box, data) {
    box.innerHTML = "";
    const sndTable = data.snd_table || [];
    const overlay = data.seasonal_overlay || {};
    const chartSeries = data.chart_series || {};

    // Header
    box.appendChild(el("div", { style: { fontSize: "15px", fontWeight: "700", color: C.amber, marginBottom: "4px" } }, `JODI GASOLINE BALANCE — ${data.country_name || data.country} (${data.start_year}–${data.end_year})`));
    box.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, marginBottom: "14px" } }, "Source: JODI World Database (Joint Organizations Data Initiative) | Monthly | 118 Countries"));

    if (sndTable.length === 0) {
      box.appendChild(el("div", { style: { color: C.muted, padding: "30px", textAlign: "center", fontSize: "13px" } }, "No gasoline data available for this country. Try another country."));
      return;
    }

    // ---- S&D BALANCE TABLE ----
    const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px", marginBottom: "8px" } });
    const hd = el("thead");
    const hr = el("tr");
    ["Flow", "Latest", "Period", "Previous", "MoM Chg", "% Chg", "5Y Avg", "vs Avg", "12m Low", "12m High", "Units"].forEach((h, i) => {
      hr.appendChild(el("th", { style: { padding: "6px 4px", textAlign: i === 0 ? "left" : "right", color: C.amber, borderBottom: `2px solid ${C.border}`, fontSize: "10px", fontWeight: "600", whiteSpace: "nowrap" } }, h));
    });
    hd.appendChild(hr);
    tbl.appendChild(hd);
    const tb = el("tbody");

    sndTable.forEach(row => {
      const tr = el("tr", { style: { borderBottom: `1px solid ${C.border}20` } });
      tr.appendChild(el("td", { style: { padding: "5px 4px", color: C.cyan, fontWeight: "600", fontSize: "11px", whiteSpace: "nowrap" } }, row.flow_name));

      const chgColor = row.mom_change > 0 ? C.green : row.mom_change < 0 ? C.red : C.muted;
      const avgColor = row.vs_avg > 0 ? C.green : row.vs_avg < 0 ? C.red : C.muted;
      const latestStr = Math.abs(row.latest) >= 100000 ? (row.latest / 1000).toFixed(1) + "K" : row.latest.toLocaleString();
      const prevStr = Math.abs(row.previous) >= 100000 ? (row.previous / 1000).toFixed(1) + "K" : row.previous.toLocaleString();

      [
        { v: latestStr, c: C.text },
        { v: row.latest_period, c: C.muted },
        { v: prevStr, c: C.muted },
        { v: (row.mom_change > 0 ? "+" : "") + row.mom_change.toLocaleString(), c: chgColor },
        { v: (row.pct_change > 0 ? "+" : "") + row.pct_change.toFixed(1) + "%", c: chgColor },
        { v: row.avg_5y.toLocaleString(), c: C.muted },
        { v: (row.vs_avg > 0 ? "+" : "") + row.vs_avg.toLocaleString(), c: avgColor },
        { v: row.min_12m.toLocaleString(), c: C.muted },
        { v: row.max_12m.toLocaleString(), c: C.muted },
        { v: row.units, c: C.muted },
      ].forEach(cell => {
        tr.appendChild(el("td", { style: { padding: "4px", textAlign: "right", color: cell.c, fontSize: "10px" } }, cell.v));
      });
      tb.appendChild(tr);
    });
    tbl.appendChild(tb);
    box.appendChild(card("Gasoline Supply & Demand Balance", tbl));

    // ---- REGIONAL COUNTRY BREAKDOWN TABLE (when viewing a region) ----
    if (data.is_region && data.region_countries && data.region_countries.length > 0) {
      const rcTbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px", marginBottom: "8px" } });
      const rcHd = el("thead");
      const rcHr = el("tr");
      const flowCols = sndTable.map(r => r.flow);
      const flowNames = sndTable.map(r => r.flow_name);
      ["Country", ...flowNames, "Period"].forEach((h, i) => {
        rcHr.appendChild(el("th", { style: { padding: "6px 4px", textAlign: i === 0 ? "left" : "right", color: C.amber, borderBottom: `2px solid ${C.border}`, fontSize: "10px", fontWeight: "600", whiteSpace: "nowrap" } }, h));
      });
      rcHd.appendChild(rcHr);
      rcTbl.appendChild(rcHd);
      const rcTb = el("tbody");
      data.region_countries.forEach(c => {
        const tr = el("tr", { style: { borderBottom: `1px solid ${C.border}20` } });
        tr.appendChild(el("td", { style: { padding: "5px 4px", color: C.cyan, fontWeight: "600", fontSize: "11px", whiteSpace: "nowrap" } }, `${c.name} (${c.code})`));
        let lastPeriod = "";
        flowCols.forEach(f => {
          const fd = c.flows[f];
          if (fd) {
            const v = fd.latest;
            const vStr = Math.abs(v) >= 100000 ? (v / 1000).toFixed(1) + "K" : v.toLocaleString();
            tr.appendChild(el("td", { style: { padding: "4px", textAlign: "right", color: C.text, fontSize: "10px" } }, vStr));
            if (fd.latest_period) lastPeriod = fd.latest_period;
          } else {
            tr.appendChild(el("td", { style: { padding: "4px", textAlign: "right", color: C.muted, fontSize: "10px" } }, "—"));
          }
        });
        tr.appendChild(el("td", { style: { padding: "4px", textAlign: "right", color: C.muted, fontSize: "10px" } }, lastPeriod));
        rcTb.appendChild(tr);
      });
      rcTbl.appendChild(rcTb);
      box.appendChild(card("Country Breakdown — " + (data.country_name || "Region"), rcTbl));
    }

    // ---- TIME SERIES CHARTS ----
    let jChIdx = 0;
    const jNextId = () => `jodi-c-${jChIdx++}`;
    const flowColors = { REFGROUT: C.cyan, TOTIMPSB: C.blue, TOTEXPSB: C.red, TOTDEMO: C.amber, STOCKCH: C.green, CLOSTLV: C.purple, RECEIPTS: "#f472b6", PTRANSF: "#a3e635", IPTRANSF: "#67e8f9", STATDIFF: C.muted };

    const tsGrid = el("div", { style: { display: "grid", gridTemplateColumns: "1fr", gap: "12px", marginBottom: "12px" } });
    const tsCharts = [];

    // Chart groups: Supply side, Trade, Demand/Stocks
    const chartGroups = [
      { title: "Refinery Output", flows: ["REFGROUT"] },
      { title: "Imports vs Exports", flows: ["TOTIMPSB", "TOTEXPSB"] },
      { title: "Demand vs Stock Change", flows: ["TOTDEMO", "STOCKCH"] },
      { title: "Closing Stocks", flows: ["CLOSTLV"] },
    ];
    chartGroups.forEach(g => {
      const traces = [];
      g.flows.forEach(f => {
        const s = chartSeries[f];
        if (s) traces.push({ x: s.dates, y: s.values, name: s.flow_name, color: flowColors[f] || C.text });
      });
      if (traces.length > 0) {
        const cid = jNextId();
        tsCharts.push({ id: cid, traces, isSC: g.flows.includes("STOCKCH") });
        tsGrid.appendChild(card(g.title, el("div", { id: cid, style: { width: "100%", height: "500px" } })));
      }
    });
    box.appendChild(tsGrid);

    // ---- SEASONAL MULTI-YEAR OVERLAY CHARTS ----
    box.appendChild(el("div", { style: { fontSize: "14px", fontWeight: "700", color: C.amber, marginTop: "18px", marginBottom: "10px", borderBottom: `1px solid ${C.border}`, paddingBottom: "6px" } }, "SEASONAL PATTERNS — Multi-Year Overlay (each line = one year)"));

    const seasonalGrid = el("div", { style: { display: "grid", gridTemplateColumns: "1fr", gap: "12px" } });
    const seasonalCharts = [];

    // Priority order for overlay charts
    const overlayOrder = ["REFGROUT", "TOTIMPSB", "TOTEXPSB", "TOTDEMO", "STOCKCH", "CLOSTLV", "RECEIPTS", "IPTRANSF", "PTRANSF", "STATDIFF"];
    overlayOrder.forEach(flow => {
      const ov = overlay[flow];
      if (!ov) return;
      const years = Object.keys(ov.years).sort();
      if (years.length < 2) return;
      const cid = jNextId();
      seasonalCharts.push({ id: cid, data: ov });
      seasonalGrid.appendChild(card(`${ov.flow_name} (${ov.units})`, el("div", { id: cid, style: { width: "100%", height: "500px" } })));
    });
    box.appendChild(seasonalGrid);

    // ---- DRAW ALL CHARTS ----
    loadPlotly(() => {
      tsCharts.forEach(({ id, traces, isSC }) => {
        const pTraces = traces.map(t => ({
          x: t.x, y: t.y, name: t.name, type: "scatter",
          line: { color: t.color, width: 2.5 },
        }));
        const layout = { ...plotLayout, height: 500, yaxis: { ...plotLayout.yaxis } };
        if (isSC) layout.shapes = [{ type: "line", x0: 0, x1: 1, xref: "paper", y0: 0, y1: 0, line: { color: C.muted, width: 1, dash: "dot" } }];
        Plotly.newPlot(id, pTraces, layout, { responsive: true });
      });

      seasonalCharts.forEach(({ id, data: ov }) => {
        const years = Object.keys(ov.years).sort();
        const months = ov.months;
        const traces = years.map((yr, i) => ({
          x: months,
          y: ov.years[yr],
          name: yr,
          type: "scatter",
          mode: "lines+markers",
          line: { color: yearColors[i % yearColors.length], width: yr === years[years.length - 1] ? 3.5 : 2 },
          marker: { size: yr === years[years.length - 1] ? 7 : 4 },
          opacity: yr === years[years.length - 1] ? 1 : 0.7,
        }));
        Plotly.newPlot(id, traces, {
          ...plotLayout,
          height: 500,
          xaxis: { ...plotLayout.xaxis, type: "category", categoryorder: "array", categoryarray: months, title: "Month" },
          yaxis: { ...plotLayout.yaxis, title: ov.units },
          legend: { font: { size: 11, color: C.text }, orientation: "h", y: -0.12 },
          showlegend: true,
        }, { responsive: true });
      });
    });
  }

  async function renderJODI(box) {
    box.innerHTML = "";

    // Controls: Country Dropdown + Year Range
    const controls = el("div", { style: { display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px", flexWrap: "wrap" } });
    controls.appendChild(el("span", { style: { fontSize: "12px", color: C.muted, fontWeight: "600" } }, "COUNTRY:"));
    const select = el("select", { style: { background: C.card, color: C.text, border: `1px solid ${C.border}`, borderRadius: "6px", padding: "8px 12px", fontSize: "12px", cursor: "pointer", minWidth: "220px" } });

    // Add a loading message while we fetch country list
    select.appendChild(el("option", { value: "US" }, "United States"));

    controls.appendChild(select);

    // Year range selectors
    controls.appendChild(el("span", { style: { fontSize: "12px", color: C.muted, fontWeight: "600", marginLeft: "12px" } }, "FROM:"));
    const startYrSel = el("select", { style: { background: C.card, color: C.text, border: `1px solid ${C.border}`, borderRadius: "6px", padding: "8px 10px", fontSize: "12px", cursor: "pointer" } });
    for (let y = 2002; y <= 2026; y++) {
      const opt = el("option", { value: String(y) }, String(y));
      if (y === jodiStartYear) opt.selected = true;
      startYrSel.appendChild(opt);
    }
    controls.appendChild(startYrSel);

    controls.appendChild(el("span", { style: { fontSize: "12px", color: C.muted, fontWeight: "600" } }, "TO:"));
    const endYrSel = el("select", { style: { background: C.card, color: C.text, border: `1px solid ${C.border}`, borderRadius: "6px", padding: "8px 10px", fontSize: "12px", cursor: "pointer" } });
    for (let y = 2002; y <= 2026; y++) {
      const opt = el("option", { value: String(y) }, String(y));
      if (y === jodiEndYear) opt.selected = true;
      endYrSel.appendChild(opt);
    }
    controls.appendChild(endYrSel);

    const loadBtn = el("button", { style: { background: C.amber, color: "#000", border: "none", borderRadius: "6px", padding: "8px 20px", fontWeight: "700", fontSize: "12px", cursor: "pointer" }, onClick: async () => {
      jodiCountry = select.value;
      jodiStartYear = parseInt(startYrSel.value);
      jodiEndYear = parseInt(endYrSel.value);
      const cName = select.options[select.selectedIndex].text;
      contentBox.innerHTML = '<div style="color:#94a3b8;padding:40px;text-align:center;">Loading JODI gasoline data for ' + cName + ' (' + jodiStartYear + '–' + jodiEndYear + ')...<br><small>First load downloads ~55 MB from JODI — may take 15-30 seconds</small></div>';
      try {
        jodiData = await fetchJODI(jodiCountry, jodiStartYear, jodiEndYear);
        if (jodiData.available_countries && !jodiCountries) {
          jodiCountries = jodiData.available_countries;
          populateCountrySelect(select, jodiCountries, jodiCountry);
        }
        renderJODIContent(contentBox, jodiData);
      } catch (e) { contentBox.innerHTML = `<div style="color:${C.red};padding:20px;">Error: ${e.message}</div>`; }
    } }, "Load Data");
    controls.appendChild(loadBtn);

    // Refresh button (re-downloads from JODI website)
    const refreshBtn = el("button", { style: { background: "transparent", color: C.muted, border: `1px solid ${C.border}`, borderRadius: "6px", padding: "8px 14px", fontSize: "11px", cursor: "pointer", marginLeft: "8px" }, onClick: async () => {
      refreshBtn.textContent = "⏳ Downloading (~60s)...";
      refreshBtn.disabled = true;
      try {
        const r = await fetch("/api/jodi_refresh", { method: "POST" });
        if (!r.ok) throw new Error(await r.text());
        refreshBtn.textContent = "✓ Refreshed!";
        refreshBtn.style.color = C.green;
        // Invalidate cache and reload
        jodiCountries = null;
        loadBtn.click();
      } catch (e) { refreshBtn.textContent = "⚠ " + e.message; refreshBtn.style.color = C.red; }
      setTimeout(() => { refreshBtn.textContent = "🔄 Refresh from JODI"; refreshBtn.style.color = C.muted; refreshBtn.disabled = false; }, 5000);
    } }, "🔄 Refresh from JODI");
    controls.appendChild(refreshBtn);

    // Source info
    controls.appendChild(el("span", { style: { fontSize: "10px", color: C.muted, marginLeft: "auto" } }, "Source: JODI World Database · Updated ~20th monthly"));
    box.appendChild(controls);

    const contentBox = el("div");
    box.appendChild(contentBox);

    // Auto-load US data
    contentBox.innerHTML = '<div style="color:#94a3b8;padding:40px;text-align:center;">Loading JODI gasoline data for United States (' + jodiStartYear + '–' + jodiEndYear + ')...<br><small>First load downloads ~55 MB from JODI — may take 15-30 seconds</small></div>';
    try {
      jodiData = await fetchJODI(jodiCountry, jodiStartYear, jodiEndYear);
      if (jodiData.available_countries) {
        jodiCountries = jodiData.available_countries;
        populateCountrySelect(select, jodiCountries, jodiCountry);
      }
      renderJODIContent(contentBox, jodiData);
    } catch (e) { contentBox.innerHTML = `<div style="color:${C.red};padding:20px;">Error: ${e.message}</div>`; }
  }

  function populateCountrySelect(sel, countries, current) {
    sel.innerHTML = "";
    const regionEntries = [];
    const countryEntries = [];
    Object.entries(countries).forEach(([code, name]) => {
      if (code.startsWith("R_")) regionEntries.push([code, name]);
      else countryEntries.push([code, name]);
    });
    if (regionEntries.length > 0) {
      const grp = document.createElement("optgroup");
      grp.label = "── Regions (Aggregated) ──";
      regionEntries.forEach(([code, name]) => {
        const opt = el("option", { value: code }, name);
        if (code === current) opt.selected = true;
        grp.appendChild(opt);
      });
      sel.appendChild(grp);
    }
    if (countryEntries.length > 0) {
      const grp = document.createElement("optgroup");
      grp.label = "── Individual Countries ──";
      countryEntries.forEach(([code, name]) => {
        const opt = el("option", { value: code }, `${name} (${code})`);
        if (code === current) opt.selected = true;
        grp.appendChild(opt);
      });
      sel.appendChild(grp);
    }
  }

  // ========== FGE GLOBAL GASOLINE BALANCES ==========
  let fgeRegion = "Global";
  let fgeData = null;

  async function fetchFGE(region) {
    const r = await fetch(`/api/fge_gasoline?region=${encodeURIComponent(region)}`);
    if (!r.ok) { const e = await r.json(); throw new Error(e.detail || r.statusText); }
    return await r.json();
  }

  function renderFGEContent(box, data) {
    box.innerHTML = "";
    const reg = data.region;

    // Header
    box.appendChild(el("div", { style: { fontSize: "15px", fontWeight: "700", color: C.amber, marginBottom: "4px" } },
      `GASOLINE SUPPLY/DEMAND OUTLOOK — ${reg.toUpperCase()}`));
    box.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, marginBottom: "14px" } },
      "Source: FGE Nexant ECA — World Oil Market Report | Monthly | kb/d"));

    // Region color map matching FGE style
    const regColors = { NA: "#1a5276", EU: "#c0392b", LA: "#85c1e9", ME: "#b7950b", FSU: "#e8a838", AP: "#196f3d", AF: "#e59866" };

    // Collect chart divs, render after Plotly loads
    const chartDivs = [];

    // --- 1) S/D Balance seasonal multi-year overlay chart ---
    const seasonal = data.seasonal || {};
    const years = Object.keys(seasonal).sort();
    const monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    const yColors = ["#196f3d","#85c1e9","#1a3a5c","#c0392b","#e8a838","#7d3c98","#e59866","#2e86c1"];

    if (years.length >= 2) {
      const cDiv = el("div", { style: { width: "100%", height: "380px", marginBottom: "20px" } });
      box.appendChild(cDiv);
      chartDivs.push(() => {
        const traces = years.map((yr, i) => ({
          x: monthNames, y: seasonal[yr],
          type: "scatter", mode: "lines", name: yr,
          line: { color: yColors[i % yColors.length], width: yr === years[years.length - 1] ? 3 : 2, dash: yr === years[years.length - 1] ? "dash" : "solid" },
          connectgaps: false,
        }));
        Plotly.newPlot(cDiv, traces, {
          title: { text: `${reg} Gasoline S/D Balance, kb/d`, font: { size: 13, color: "#5dade2" } },
          xaxis: { color: C.muted, gridcolor: C.border },
          yaxis: { title: "kb/d", color: C.muted, gridcolor: C.border, zeroline: true, zerolinecolor: C.muted },
          paper_bgcolor: "transparent", plot_bgcolor: "transparent",
          legend: { font: { color: C.text, size: 10 }, orientation: "h", y: -0.15 },
          margin: { t: 40, b: 60, l: 60, r: 20 }, showlegend: true,
        }, { responsive: true });
      });
    }

    // --- 2) YoY Quarterly Change by Region (stacked bar) ---
    const qyoy = data.quarterly_yoy || {};
    if (qyoy.labels && qyoy.regions) {
      const cDiv = el("div", { style: { width: "100%", height: "380px", marginBottom: "20px" } });
      box.appendChild(cDiv);
      chartDivs.push(() => {
        const barTraces = Object.keys(qyoy.regions).map(rShort => ({
          x: qyoy.labels, y: qyoy.regions[rShort],
          type: "bar", name: rShort,
          marker: { color: regColors[rShort] || "#999" },
        }));
        barTraces.push({
          x: qyoy.labels, y: qyoy.total,
          type: "scatter", mode: "lines+markers", name: "Total",
          line: { color: "#e5e7eb", width: 2 }, marker: { color: "#fff", size: 6, line: { color: "#e5e7eb", width: 1.5 } },
        });
        Plotly.newPlot(cDiv, barTraces, {
          title: { text: "Y-o-Y Quarterly Change in S/D Balances by Region, kb/d", font: { size: 13, color: "#5dade2" } },
          barmode: "relative",
          xaxis: { color: C.muted, gridcolor: C.border },
          yaxis: { title: "kb/d", color: C.muted, gridcolor: C.border, zeroline: true, zerolinecolor: C.muted },
          paper_bgcolor: "transparent", plot_bgcolor: "transparent",
          legend: { font: { color: C.text, size: 10 }, orientation: "h", y: -0.2 },
          margin: { t: 40, b: 70, l: 60, r: 20 },
        }, { responsive: true });
      });
    }

    // --- 3) Supply vs Demand chart ---
    if (data.supply && data.demand && data.dates_snd) {
      const cDiv = el("div", { style: { width: "100%", height: "340px", marginBottom: "20px" } });
      box.appendChild(cDiv);
      chartDivs.push(() => {
        Plotly.newPlot(cDiv, [
          { x: data.dates_snd, y: data.supply, type: "scatter", mode: "lines", name: "Supply", line: { color: "#27ae60", width: 2 } },
          { x: data.dates_snd, y: data.demand, type: "scatter", mode: "lines", name: "Demand", line: { color: "#e74c3c", width: 2 } },
        ], {
          title: { text: `${reg} Gasoline Supply vs Demand, kb/d`, font: { size: 13, color: "#5dade2" } },
          xaxis: { color: C.muted, gridcolor: C.border },
          yaxis: { title: "kb/d", color: C.muted, gridcolor: C.border },
          paper_bgcolor: "transparent", plot_bgcolor: "transparent",
          legend: { font: { color: C.text, size: 10 }, orientation: "h", y: -0.15 },
          margin: { t: 40, b: 50, l: 60, r: 20 },
        }, { responsive: true });
      });
    }

    // --- 4) Balance timeseries chart ---
    if (data.snd_balance && data.dates_snd) {
      const cDiv = el("div", { style: { width: "100%", height: "340px", marginBottom: "20px" } });
      box.appendChild(cDiv);
      chartDivs.push(() => {
        const colors = data.snd_balance.map(v => v >= 0 ? "#27ae60" : "#e74c3c");
        Plotly.newPlot(cDiv, [
          { x: data.dates_snd, y: data.snd_balance, type: "bar", name: "S/D Balance", marker: { color: colors } },
        ], {
          title: { text: `${reg} Gasoline S/D Balance (Supply − Demand), kb/d`, font: { size: 13, color: "#5dade2" } },
          xaxis: { color: C.muted, gridcolor: C.border },
          yaxis: { title: "kb/d", color: C.muted, gridcolor: C.border, zeroline: true, zerolinecolor: C.muted },
          paper_bgcolor: "transparent", plot_bgcolor: "transparent",
          margin: { t: 40, b: 50, l: 60, r: 20 }, showlegend: false,
        }, { responsive: true });
      });
    }

    // --- 5) YoY Change bar chart (monthly) ---
    if (data.yoy_change && data.dates_outlook) {
      const cDiv = el("div", { style: { width: "100%", height: "300px", marginBottom: "20px" } });
      box.appendChild(cDiv);
      chartDivs.push(() => {
        const yoyColors = data.yoy_change.map(v => v >= 0 ? "#27ae60" : "#e74c3c");
        Plotly.newPlot(cDiv, [
          { x: data.dates_outlook, y: data.yoy_change, type: "bar", name: "YoY Change", marker: { color: yoyColors } },
        ], {
          title: { text: `${reg} Gasoline S/D Balance — Year-on-Year Change, kb/d`, font: { size: 13, color: "#5dade2" } },
          xaxis: { color: C.muted, gridcolor: C.border },
          yaxis: { title: "kb/d", color: C.muted, gridcolor: C.border, zeroline: true, zerolinecolor: C.muted },
          paper_bgcolor: "transparent", plot_bgcolor: "transparent",
          margin: { t: 40, b: 50, l: 60, r: 20 }, showlegend: false,
        }, { responsive: true });
      });
    }

    // --- 6) Regional Comparison Table ---
    const comp = data.region_comparison || [];
    if (comp.length > 0) {
      box.appendChild(el("div", { style: { fontSize: "13px", fontWeight: "700", color: C.amber, margin: "18px 0 8px" } }, "REGIONAL COMPARISON — LATEST MONTH (kb/d)"));
      const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px", marginBottom: "16px" } });
      const hdr = el("tr");
      ["Region", "Balance", "Supply", "Demand", "YoY Chg"].forEach(h => {
        const th = el("th", { style: { textAlign: h === "Region" ? "left" : "right", padding: "6px 10px", borderBottom: `1px solid ${C.border}`, color: C.muted, fontWeight: "600" } }, h);
        hdr.appendChild(th);
      });
      tbl.appendChild(hdr);
      comp.forEach(r => {
        const tr = el("tr");
        const vals = [r.short, r.latest_balance, r.latest_supply, r.latest_demand, r.latest_yoy];
        vals.forEach((v, i) => {
          let txt = v;
          let clr = C.text;
          if (i > 0 && v !== null) {
            txt = v.toFixed(1);
            if (i === 1 || i === 4) clr = v >= 0 ? C.green : C.red;
          }
          const td = el("td", { style: { textAlign: i === 0 ? "left" : "right", padding: "5px 10px", borderBottom: `1px solid ${C.border}`, color: clr } }, txt ?? "—");
          tr.appendChild(td);
        });
        tbl.appendChild(tr);
      });
      // Global total row
      const totBal = comp.reduce((s, r) => s + (r.latest_balance || 0), 0);
      const totSup = comp.reduce((s, r) => s + (r.latest_supply || 0), 0);
      const totDem = comp.reduce((s, r) => s + (r.latest_demand || 0), 0);
      const totYoy = comp.reduce((s, r) => s + (r.latest_yoy || 0), 0);
      const totR = el("tr", { style: { fontWeight: "700" } });
      [{ v: "GLOBAL", a: "left" }, { v: totBal, a: "right" }, { v: totSup, a: "right" }, { v: totDem, a: "right" }, { v: totYoy, a: "right" }].forEach((x, i) => {
        let clr = C.amber;
        if (i > 0) clr = (i === 1 || i === 4) ? (x.v >= 0 ? C.green : C.red) : C.amber;
        const td = el("td", { style: { textAlign: x.a, padding: "5px 10px", borderTop: `2px solid ${C.border}`, color: clr } }, typeof x.v === "number" ? x.v.toFixed(1) : x.v);
        totR.appendChild(td);
      });
      tbl.appendChild(totR);
      box.appendChild(tbl);
    }

    // --- 7) Regional Balance Comparison Bar Chart ---
    if (comp.length > 0) {
      const cDiv = el("div", { style: { width: "100%", height: "300px", marginBottom: "20px" } });
      box.appendChild(cDiv);
      chartDivs.push(() => {
        const shorts = comp.map(r => r.short);
        const bals = comp.map(r => r.latest_balance || 0);
        const barCols = bals.map(v => v >= 0 ? "#27ae60" : "#e74c3c");
        Plotly.newPlot(cDiv, [
          { x: shorts, y: bals, type: "bar", marker: { color: barCols } },
        ], {
          title: { text: "Regional Gasoline S/D Balance — Latest Month, kb/d", font: { size: 13, color: "#5dade2" } },
          xaxis: { color: C.muted }, yaxis: { title: "kb/d", color: C.muted, gridcolor: C.border, zeroline: true, zerolinecolor: C.muted },
          paper_bgcolor: "transparent", plot_bgcolor: "transparent",
          margin: { t: 40, b: 40, l: 60, r: 20 }, showlegend: false,
        }, { responsive: true });
      });
    }

    // Render all charts once Plotly is loaded
    loadPlotly(() => { chartDivs.forEach(fn => fn()); });
  }

  // ========== KPLER GASOLINE FLOWS (Ship-tracking based) ==========
  let kplerProduct = "Gasoline";
  let kplerDirection = "export";
  let kplerSplit = "OriginCountries";
  let kplerGranularity = "monthly";
  let kplerStartYear = 2020;
  let kplerEndYear = 2026;
  let kplerZone = "";
  let kplerData = null;

  async function fetchKpler() {
    const sd = `${kplerStartYear}-01-01`;
    const ed = `${kplerEndYear}-12-31`;
    let url = `/api/kpler/flows?product=${encodeURIComponent(kplerProduct)}&direction=${kplerDirection}&split=${kplerSplit}&granularity=${kplerGranularity}&start_date=${sd}&end_date=${ed}&unit=kbd&with_forecast=true`;
    if (kplerZone && kplerDirection === "export") url += `&from_zone=${encodeURIComponent(kplerZone)}`;
    else if (kplerZone && kplerDirection === "import") url += `&to_zone=${encodeURIComponent(kplerZone)}`;
    const r = await fetch(url);
    if (!r.ok) { const e = await r.json(); throw new Error(e.detail || r.statusText); }
    return await r.json();
  }

  function renderKplerContent(box, data) {
    box.innerHTML = "";
    const locs = data.locations || [];
    const series = data.series || {};
    const summary = data.summary || [];
    const seasonal = data.seasonal || {};

    // Header
    const dirLabel = data.direction === "export" ? "Exports" : "Imports";
    const splitLabel = data.split.replace("Countries", " Countries").replace("Padds", " PADDs").replace("Continents", " Continents").replace("TradingRegions", " Regions");
    box.appendChild(el("div", { style: { fontSize: "15px", fontWeight: "700", color: C.amber, marginBottom: "4px" } }, `KPLER ${data.product.toUpperCase()} ${dirLabel.toUpperCase()} — by ${splitLabel}`));
    box.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, marginBottom: "14px" } }, `Source: Kpler Ship-Tracking (Satellite AIS) | ${data.granularity} | ${data.total_locations} ${splitLabel} | ${data.date_range.start} to ${data.date_range.end} | KBD`));

    if (locs.length === 0) {
      box.appendChild(el("div", { style: { color: C.muted, padding: "30px", textAlign: "center", fontSize: "13px" } }, "No data returned. Try different parameters."));
      return;
    }

    // ---- SUMMARY TABLE ----
    const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px", marginBottom: "12px" } });
    const hd = el("thead");
    const hr = el("tr");
    ["Location", "Latest (KBD)", "Average", "Max", "Min", "Total"].forEach(h => hr.appendChild(el("th", { style: { padding: "6px 4px", textAlign: h === "Location" ? "left" : "right", color: C.muted, borderBottom: `1px solid ${C.border}`, fontSize: "10px", fontWeight: "600" } }, h)));
    hd.appendChild(hr);
    tbl.appendChild(hd);
    const tb = el("tbody");
    summary.slice(0, 25).forEach(row => {
      const tr = el("tr", { style: { borderBottom: `1px solid ${C.border}20` } });
      tr.appendChild(el("td", { style: { padding: "5px 4px", color: C.cyan, fontWeight: "600", fontSize: "11px" } }, row.location));
      tr.appendChild(el("td", { style: { padding: "5px 4px", textAlign: "right", color: C.text } }, fmt(row.latest)));
      tr.appendChild(el("td", { style: { padding: "5px 4px", textAlign: "right", color: C.muted } }, fmt(row.avg)));
      tr.appendChild(el("td", { style: { padding: "5px 4px", textAlign: "right", color: C.green } }, fmt(row.max)));
      tr.appendChild(el("td", { style: { padding: "5px 4px", textAlign: "right", color: C.red } }, fmt(row.min)));
      tr.appendChild(el("td", { style: { padding: "5px 4px", textAlign: "right", color: C.blue } }, fmt(row.total)));
      tb.appendChild(tr);
    });
    tbl.appendChild(tb);
    box.appendChild(card("Flows Summary (Top 25)", tbl));

    // ---- TIME SERIES CHART: Top 10 ----
    let kChIdx = 0;
    const kNextId = () => `kpler-c-${kChIdx++}`;
    const chartDivs = [];
    const lineColors = [C.blue, C.amber, C.green, C.red, C.cyan, C.purple, "#f472b6", "#a3e635", "#67e8f9", "#fb923c", "#c084fc", "#22d3ee"];

    {
      const cId = kNextId();
      const cDiv = el("div", { id: cId, style: { width: "100%", height: "550px" } });
      box.appendChild(card(`${dirLabel} by ${splitLabel} (Top 10)`, cDiv));
      chartDivs.push(() => {
        const top10 = locs.slice(0, 10);
        const traces = top10.map((loc, i) => {
          const s = series[loc] || {};
          return { x: s.dates || [], y: s.values || [], type: "scatter", mode: "lines", name: loc, line: { color: lineColors[i % lineColors.length], width: 2.5 } };
        });
        Plotly.newPlot(cId, traces, { ...plotLayout, title: { text: `${data.product} ${dirLabel} (KBD)`, font: { color: C.amber, size: 16 }, x: 0.02, xanchor: 'left' }, xaxis: { color: C.muted, gridcolor: C.border + "40", tickfont: { size: 12 } }, yaxis: { color: C.muted, gridcolor: C.border + "40", title: { text: "KBD", font: { size: 13 } }, tickfont: { size: 12 } }, legend: { font: { color: C.text, size: 11 }, itemclick: 'toggle', itemdoubleclick: 'toggleothers' }, height: 550, hovermode: 'x unified' }, { responsive: true });
      });
    }

    // ---- STACKED AREA CHART: All top locations ----
    {
      const cId = kNextId();
      const cDiv = el("div", { id: cId, style: { width: "100%", height: "550px" } });
      box.appendChild(card(`${dirLabel} Stacked Area (Top 10)`, cDiv));
      chartDivs.push(() => {
        const top10 = locs.slice(0, 10);
        const traces = top10.map((loc, i) => {
          const s = series[loc] || {};
          return { x: s.dates || [], y: s.values || [], type: "scatter", mode: "lines", name: loc, stackgroup: "one", line: { color: lineColors[i % lineColors.length], width: 0.5 } };
        });
        Plotly.newPlot(cId, traces, { ...plotLayout, title: { text: `${data.product} ${dirLabel} Stacked (KBD)`, font: { color: C.amber, size: 16 }, x: 0.02, xanchor: 'left' }, xaxis: { color: C.muted, gridcolor: C.border + "40", tickfont: { size: 12 } }, yaxis: { color: C.muted, gridcolor: C.border + "40", title: { text: "KBD", font: { size: 13 } }, tickfont: { size: 12 } }, legend: { font: { color: C.text, size: 11 }, itemclick: 'toggle', itemdoubleclick: 'toggleothers' }, height: 550, hovermode: 'x unified' }, { responsive: true });
      });
    }

    // ---- MULTI-YEAR OVERLAY SEASONAL CHARTS ----
    if (Object.keys(seasonal).length > 0) {
      box.appendChild(el("div", { style: { fontSize: "13px", fontWeight: "700", color: C.amber, marginTop: "16px", marginBottom: "8px" } }, "MULTI-YEAR SEASONAL OVERLAY (Total Flows)"));
      const monthLabels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      const cId = kNextId();
      const cDiv = el("div", { id: cId, style: { width: "100%", height: "550px" } });
      box.appendChild(card("Seasonal Overlay (each year as a line)", cDiv));
      chartDivs.push(() => {
        const years = Object.keys(seasonal).sort();
        const traces = years.map((yr, i) => {
          const s = seasonal[yr];
          return { x: s.months.map(m => monthLabels[m - 1]), y: s.values, type: "scatter", mode: "lines+markers", name: yr, line: { color: lineColors[i % lineColors.length], width: yr === years[years.length - 1] ? 3.5 : 2 }, marker: { size: yr === years[years.length - 1] ? 7 : 4 } };
        });
        Plotly.newPlot(cId, traces, { ...plotLayout, title: { text: `${data.product} ${dirLabel} Seasonal (KBD)`, font: { color: C.amber, size: 16 }, x: 0.02, xanchor: 'left' }, xaxis: { color: C.muted, gridcolor: C.border + "40", tickfont: { size: 12 } }, yaxis: { color: C.muted, gridcolor: C.border + "40", title: { text: "KBD", font: { size: 13 } }, tickfont: { size: 12 } }, legend: { font: { color: C.text, size: 11 }, itemclick: 'toggle', itemdoubleclick: 'toggleothers' }, height: 550, hovermode: 'x unified' }, { responsive: true });
      });
    }

    // ---- PER-LOCATION SEASONAL (top 5) ----
    const top5 = locs.slice(0, 5);
    if (top5.length > 0 && Object.keys(series).length > 0) {
      box.appendChild(el("div", { style: { fontSize: "13px", fontWeight: "700", color: C.amber, marginTop: "16px", marginBottom: "8px" } }, "PER-COUNTRY SEASONAL OVERLAY (Top 5)"));
      top5.forEach(loc => {
        const s = series[loc];
        if (!s || !s.dates || s.dates.length === 0) return;
        // Group by year
        const byYear = {};
        s.dates.forEach((d, i) => {
          const dt = new Date(d);
          const yr = dt.getFullYear();
          const mo = dt.getMonth() + 1;
          if (!byYear[yr]) byYear[yr] = {};
          byYear[yr][mo] = s.values[i];
        });
        const monthLabels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        const cId = kNextId();
        const cDiv = el("div", { id: cId, style: { width: "100%", height: "450px" } });
        box.appendChild(card(`${loc} — Seasonal`, cDiv));
        chartDivs.push(() => {
          const yrs = Object.keys(byYear).sort();
          const traces = yrs.map((yr, i) => {
            const ms = [], vs = [];
            for (let m = 1; m <= 12; m++) {
              if (byYear[yr][m] !== undefined) { ms.push(monthLabels[m - 1]); vs.push(byYear[yr][m]); }
            }
            return { x: ms, y: vs, type: "scatter", mode: "lines+markers", name: yr, line: { color: lineColors[i % lineColors.length], width: yr === yrs[yrs.length - 1] ? 3.5 : 2 }, marker: { size: yr === yrs[yrs.length - 1] ? 7 : 4 } };
          });
          Plotly.newPlot(cId, traces, { ...plotLayout, title: { text: `${loc} ${dirLabel} (KBD)`, font: { color: C.amber, size: 15 }, x: 0.02, xanchor: 'left' }, xaxis: { color: C.muted, gridcolor: C.border + "40", tickfont: { size: 12 } }, yaxis: { color: C.muted, gridcolor: C.border + "40", title: { text: "KBD", font: { size: 13 } }, tickfont: { size: 12 } }, legend: { font: { color: C.text, size: 11 }, itemclick: 'toggle', itemdoubleclick: 'toggleothers' }, height: 450, hovermode: 'x unified' }, { responsive: true });
        });
      });
    }

    loadPlotly(() => { chartDivs.forEach(fn => fn()); });
  }

  async function renderKpler(box) {
    box.innerHTML = "";

    // Controls row
    const controls = el("div", { style: { display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px", flexWrap: "wrap" } });
    const lblStyle = { fontSize: "11px", color: C.muted, marginRight: "4px" };

    // Product selector
    controls.appendChild(el("span", { style: lblStyle }, "Product:"));
    const prodSel = el("select", { style: { background: C.card, color: C.text, border: `1px solid ${C.border}`, borderRadius: "4px", padding: "4px 8px", fontSize: "12px" } });
    ["Gasoline", "Gasoline/Naphtha", "Naphtha", "RBOB", "CBOB", "Crude/Co"].forEach(p => {
      const opt = el("option", { value: p }, p);
      if (p === kplerProduct) opt.selected = true;
      prodSel.appendChild(opt);
    });
    controls.appendChild(prodSel);

    // Direction
    controls.appendChild(el("span", { style: { ...lblStyle, marginLeft: "8px" } }, "Direction:"));
    const dirSel = el("select", { style: { background: C.card, color: C.text, border: `1px solid ${C.border}`, borderRadius: "4px", padding: "4px 8px", fontSize: "12px" } });
    [["export", "Exports"], ["import", "Imports"]].forEach(([v, l]) => {
      const opt = el("option", { value: v }, l);
      if (v === kplerDirection) opt.selected = true;
      dirSel.appendChild(opt);
    });
    controls.appendChild(dirSel);

    // Split
    controls.appendChild(el("span", { style: { ...lblStyle, marginLeft: "8px" } }, "Split:"));
    const splitSel = el("select", { style: { background: C.card, color: C.text, border: `1px solid ${C.border}`, borderRadius: "4px", padding: "4px 8px", fontSize: "12px" } });
    [
      ["OriginCountries", "Origin Countries"],
      ["DestinationCountries", "Dest. Countries"],
      ["OriginPadds", "Origin PADDs"],
      ["DestinationPadds", "Dest. PADDs"],
      ["OriginContinents", "Origin Continents"],
      ["DestinationContinents", "Dest. Continents"],
      ["OriginTradingRegions", "Origin Trading Regions"],
      ["DestinationTradingRegions", "Dest. Trading Regions"],
      ["VesselTypeOil", "Vessel Type"],
    ].forEach(([v, l]) => {
      const opt = el("option", { value: v }, l);
      if (v === kplerSplit) opt.selected = true;
      splitSel.appendChild(opt);
    });
    controls.appendChild(splitSel);

    // Granularity
    controls.appendChild(el("span", { style: { ...lblStyle, marginLeft: "8px" } }, "Period:"));
    const granSel = el("select", { style: { background: C.card, color: C.text, border: `1px solid ${C.border}`, borderRadius: "4px", padding: "4px 8px", fontSize: "12px" } });
    [["monthly", "Monthly"], ["weekly", "Weekly (EIA)"], ["daily", "Daily"]].forEach(([v, l]) => {
      const opt = el("option", { value: v }, l);
      if (v === kplerGranularity) opt.selected = true;
      granSel.appendChild(opt);
    });
    controls.appendChild(granSel);

    // Zone filter
    controls.appendChild(el("span", { style: { ...lblStyle, marginLeft: "8px" } }, "Zone:"));
    const zoneInput = el("input", { type: "text", placeholder: "e.g. United States, PADD 3", value: kplerZone, style: { background: C.card, color: C.text, border: `1px solid ${C.border}`, borderRadius: "4px", padding: "4px 8px", fontSize: "12px", width: "160px" } });
    controls.appendChild(zoneInput);

    // Year range
    controls.appendChild(el("span", { style: { ...lblStyle, marginLeft: "8px" } }, "From:"));
    const fromSel = el("select", { style: { background: C.card, color: C.text, border: `1px solid ${C.border}`, borderRadius: "4px", padding: "4px 8px", fontSize: "12px" } });
    for (let y = 2015; y <= 2026; y++) {
      const opt = el("option", { value: String(y) }, String(y));
      if (y === kplerStartYear) opt.selected = true;
      fromSel.appendChild(opt);
    }
    controls.appendChild(fromSel);
    controls.appendChild(el("span", { style: lblStyle }, "To:"));
    const toSel = el("select", { style: { background: C.card, color: C.text, border: `1px solid ${C.border}`, borderRadius: "4px", padding: "4px 8px", fontSize: "12px" } });
    for (let y = 2015; y <= 2026; y++) {
      const opt = el("option", { value: String(y) }, String(y));
      if (y === kplerEndYear) opt.selected = true;
      toSel.appendChild(opt);
    }
    controls.appendChild(toSel);

    // Load button
    const loadBtn = el("button", { style: { background: C.amber, color: "#000", border: "none", borderRadius: "4px", padding: "6px 16px", cursor: "pointer", fontWeight: "700", fontSize: "12px", marginLeft: "8px" } }, "Load Data");
    controls.appendChild(loadBtn);

    box.appendChild(controls);

    // Content area
    const contentBox = el("div");
    box.appendChild(contentBox);

    async function load() {
      kplerProduct = prodSel.value;
      kplerDirection = dirSel.value;
      kplerSplit = splitSel.value;
      kplerGranularity = granSel.value;
      kplerZone = zoneInput.value.trim();
      kplerStartYear = parseInt(fromSel.value);
      kplerEndYear = parseInt(toSel.value);
      contentBox.innerHTML = '<div style="color:#94a3b8;padding:40px;text-align:center;">Loading Kpler data... (may take 10-15s on first load)</div>';
      try {
        kplerData = await fetchKpler();
        renderKplerContent(contentBox, kplerData);
      } catch (e) {
        contentBox.innerHTML = `<div style="color:${C.red};padding:20px;">Error: ${e.message}</div>`;
      }
    }

    loadBtn.addEventListener("click", load);
    load();
  }

  // ========== MARKET COMMENTARY (AI-style briefings) ==========
  async function renderMarketCommentary(box) {
    box.innerHTML = "";
    const PRODUCTS = [["crude", "Crude"], ["distillate", "Distillate"], ["gasoline", "Gasoline"], ["freight", "Freight"]];
    const REGIONS = [["US", "US"], ["UK", "UK / Europe"], ["DUBAI", "Dubai"], ["SING", "Singapore"]];
    let product = "crude", region = "US", useLLM = true;

    box.appendChild(el("div", { style: { fontSize: "16px", fontWeight: "800", color: C.amber, marginBottom: "3px" } }, "🧭 MARKET COMMENTARY — Daily Product Briefings"));
    box.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, marginBottom: "14px" } },
      "AI-style cross-barrel briefings generated from live positioning, pricing, cracks, swaps & refinery margins. Not investment advice."));

    // Selectors
    const bar = el("div", { style: { display: "flex", gap: "18px", flexWrap: "wrap", alignItems: "flex-end", marginBottom: "14px" } });
    box.appendChild(bar);

    function pillGroup(labelTxt, opts, getVal, setVal) {
      const wrap = el("div", {});
      wrap.appendChild(el("div", { style: { fontSize: "10px", color: C.muted, marginBottom: "4px", textTransform: "uppercase", letterSpacing: "0.5px" } }, labelTxt));
      const row = el("div", { style: { display: "flex", gap: "6px", flexWrap: "wrap" } });
      const bs = [];
      opts.forEach(([v, lbl]) => {
        const b = el("button", { style: pillStyle(getVal() === v), onClick: () => { setVal(v); bs.forEach((bb, i) => Object.assign(bb.style, pillStyle(getVal() === opts[i][0]))); draw(); } });
        b.textContent = lbl; bs.push(b); row.appendChild(b);
      });
      wrap.appendChild(row); return wrap;
    }
    function pillStyle(on) {
      return { padding: "6px 13px", border: on ? `2px solid ${C.amber}` : "1px solid #334155", background: on ? C.amber + "22" : C.card, color: on ? C.amber : C.text, borderRadius: "6px", cursor: "pointer", fontSize: "11px", fontWeight: "600" };
    }
    bar.appendChild(pillGroup("Product", PRODUCTS, () => product, v => product = v));
    bar.appendChild(pillGroup("Region", REGIONS, () => region, v => region = v));

    const out = el("div", {});
    box.appendChild(out);

    async function draw() {
      out.innerHTML = '<div style="color:#94a3b8;padding:30px;text-align:center;">Generating briefing…</div>';
      let d;
      try { const r = await fetch(`/api/market/briefing?product=${product}&region=${region}&use_llm=${useLLM}`); d = await r.json(); }
      catch (e) { out.innerHTML = `<div style="color:${C.red};padding:20px;">Error: ${e.message}</div>`; return; }
      out.innerHTML = "";
      if (!d.available) { out.innerHTML = `<div style="color:${C.muted};padding:20px;">${d.message || "No data for this combination."}</div>`; return; }

      const card = el("div", { style: { background: C.card, border: "1px solid #1e293b", borderRadius: "10px", padding: "18px 20px" } });
      card.appendChild(el("div", { style: { fontSize: "15px", fontWeight: "800", color: C.text } }, d.title));
      const badge = el("span", { style: { fontSize: "9px", fontWeight: "700", color: d.llm ? "#000" : C.muted, background: d.llm ? C.green : "transparent", border: d.llm ? "none" : `1px solid ${C.border}`, borderRadius: "4px", padding: "2px 7px", marginLeft: "8px" } }, d.llm ? "AI-WRITTEN" : "RULE-BASED");
      card.lastChild.appendChild(badge);
      card.appendChild(el("div", { style: { fontSize: "10px", color: C.muted, margin: "3px 0 14px", fontStyle: "italic" } }, d.disclaimer));

      // Headline metric chips
      if (d.headline_metrics && d.headline_metrics.length) {
        const chips = el("div", { style: { display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "16px" } });
        d.headline_metrics.forEach(m => {
          const c = el("div", { style: { background: C.bg, border: "1px solid #1e293b", borderRadius: "8px", padding: "8px 12px", minWidth: "110px" } });
          c.appendChild(el("div", { style: { fontSize: "9px", color: C.muted, textTransform: "uppercase" } }, m.label));
          c.appendChild(el("div", { style: { fontSize: "16px", fontWeight: "800", color: C.text } }, m.value));
          c.appendChild(el("div", { style: { fontSize: "10px", color: C.cyan } }, m.chg));
          chips.appendChild(c);
        });
        card.appendChild(chips);
      }

      // LLM prose (if present) shown first — render minimal markdown (**bold**)
      if (d.prose) {
        const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        const html = esc(d.prose)
          .replace(/^#{1,4}\s*(.+)$/gm, '<span style="display:block;color:#38bdf8;font-weight:800;font-size:11.5px;letter-spacing:1.4px;text-transform:uppercase;margin:14px 0 4px;border-bottom:1px solid #1a2338;padding-bottom:4px;">$1</span>')
          .replace(/\*\*(.+?)\*\*/g, '<strong style="color:#7dd3fc">$1</strong>')
          .replace(/\n/g, "<br>");
        const pb = el("div", { style: { fontSize: "12.5px", lineHeight: "1.65", color: C.text, background: C.bg, border: `1px solid ${C.border}`, borderRadius: "8px", padding: "14px 16px", marginBottom: "16px" } });
        pb.innerHTML = html; card.appendChild(pb);
      }

      function section(title, color) {
        card.appendChild(el("div", { style: { fontSize: "12px", fontWeight: "800", color: color, textTransform: "uppercase", letterSpacing: "0.5px", margin: "16px 0 8px", borderBottom: `1px solid ${C.border}`, paddingBottom: "4px" } }, title));
      }

      // When AI prose is present it already contains TL;DR / Market State / Physical / Watch,
      // so only render the structured rule-based sections in the fallback case.
      if (!d.prose) {
        section("TL;DR", C.amber);
        (d.tldr || []).forEach(t => {
          card.appendChild(el("div", { style: { fontSize: "12.5px", lineHeight: "1.55", color: C.text, marginBottom: "7px" } }, "• " + t));
        });

        section("Market State", C.cyan);
        card.appendChild(el("div", { style: { fontSize: "12.5px", lineHeight: "1.6", color: C.text, marginBottom: "6px" } }, d.market_state || ""));

        section("Physical Update", C.purple);
        (d.physical || []).forEach((t, i) => {
          card.appendChild(el("div", { style: { fontSize: "12.5px", lineHeight: "1.55", color: C.text, marginBottom: "7px" } },
            [el("span", { style: { color: C.purple, fontWeight: "700" } }, `Theme ${i + 1}: `), document.createTextNode(t)]));
        });

        section("What to Watch", C.green);
        (d.watch || []).forEach((t, i) => {
          card.appendChild(el("div", { style: { fontSize: "12.5px", lineHeight: "1.55", color: C.text, marginBottom: "7px" } },
            [el("span", { style: { color: C.green, fontWeight: "700" } }, `(${i + 1}) `), document.createTextNode(t)]));
        });
      }

      out.appendChild(card);
    }
    draw();
  }

  // ========== CROSS-MARKET INTELLIGENCE ==========
  async function renderCrossMarket(box) {
    box.innerHTML = '<div style="color:#94a3b8;padding:40px;text-align:center;">Loading cross-market intelligence…</div>';
    let d;
    try { const r = await fetch("/api/market/crossmarket"); d = await r.json(); }
    catch (e) { box.innerHTML = `<div style="color:${C.red};padding:20px;">Error: ${e.message}</div>`; return; }
    box.innerHTML = "";

    const cmHdr = el("div", { style: { display: "flex", alignItems: "center", gap: "10px", marginBottom: "3px", flexWrap: "wrap" } });
    cmHdr.appendChild(el("div", { style: { fontSize: "16px", fontWeight: "800", color: C.amber } }, "🧠 CROSS-MARKET INTELLIGENCE"));
    cmHdr.appendChild(liveBadge());
    box.appendChild(cmHdr);
    box.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, marginBottom: "16px" } },
      `Fuses positioning · pricing · term structure · cracks · margins into a directional read per product. Generated ${(d.generated || "").slice(0, 16).replace("T", " ")} UTC.${d.live && d.live.count ? " · Prices live from Bloomberg bridge." : ""}`));

    // Auto-refresh the whole read while the tab stays open (live feed cadence).
    if (window.__cmTimer) clearTimeout(window.__cmTimer);
    window.__cmTimer = setTimeout(() => { if (document.body.contains(box)) renderCrossMarket(box); }, 45000);

    // Trajectory cards
    const traj = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "12px", marginBottom: "20px" } });
    const biasColor = b => b === "BULLISH" ? C.green : b === "BEARISH" ? C.red : C.muted;
    (d.trajectory || []).forEach(t => {
      const c = el("div", { style: { background: C.card, border: `1px solid #1e293b`, borderLeft: `4px solid ${biasColor(t.bias)}`, borderRadius: "8px", padding: "14px 16px" } });
      const hr = el("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" } });
      hr.appendChild(el("div", { style: { fontSize: "14px", fontWeight: "800", color: C.text, textTransform: "capitalize" } }, t.product));
      hr.appendChild(el("div", { style: { fontSize: "12px", fontWeight: "800", color: biasColor(t.bias) } }, t.bias));
      c.appendChild(hr);
      // score bar centred at 0
      const track = el("div", { style: { position: "relative", height: "8px", background: "#1e293b", borderRadius: "4px", margin: "6px 0 10px" } });
      const pct = Math.max(-100, Math.min(100, t.score));
      const half = Math.abs(pct) / 2;
      const fill = el("div", { style: { position: "absolute", top: "0", height: "8px", borderRadius: "4px", background: biasColor(t.bias), left: pct >= 0 ? "50%" : (50 - half) + "%", width: half + "%" } });
      track.appendChild(fill);
      track.appendChild(el("div", { style: { position: "absolute", left: "50%", top: "-2px", width: "1px", height: "12px", background: C.muted } }));
      c.appendChild(track);
      c.appendChild(el("div", { style: { fontSize: "10px", color: C.muted, marginBottom: "6px" } }, `Score ${t.score >= 0 ? "+" : ""}${t.score}`));
      (t.drivers || []).forEach(dr => c.appendChild(el("div", { style: { fontSize: "11px", color: C.text, marginBottom: "3px" } }, "› " + dr)));
      traj.appendChild(c);
    });
    box.appendChild(traj);

    const sgn = (x, dp = 2) => (x >= 0 ? "+" : "") + Number(x).toFixed(dp);
    const chgC = x => x > 0 ? C.green : x < 0 ? C.red : C.muted;
    const biasCol = b => b === "BULLISH" ? C.green : b === "BEARISH" ? C.red : C.muted;
    const mdBold = s => (s || "").replace(/\*\*(.+?)\*\*/g, "<b style='color:#e2e8f0'>$1</b>");

    // ===== DESK TRADE RECOMMENDATIONS =====
    box.appendChild(el("div", { style: { fontSize: "14px", fontWeight: "800", color: C.amber, margin: "8px 0 4px" } }, "🎯 DESK TRADE RECOMMENDATIONS"));
    box.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, marginBottom: "12px" } },
      "Per-market actionable ideas fusing term structure (M1/M2), crack curves, positioning, margins & market intel. Conviction ★1–5. Not investment advice."));

    const deskGrid = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: "14px", marginBottom: "22px" } });
    (d.desk || []).forEach(r => {
      const card = el("div", { style: { background: C.card, border: "1px solid #1e293b", borderLeft: `4px solid ${biasCol(r.bias)}`, borderRadius: "10px", padding: "14px 16px" } });
      // header
      const hd = el("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "8px", marginBottom: "6px" } });
      hd.appendChild(el("div", { style: { fontSize: "13.5px", fontWeight: "800", color: C.text } }, r.market));
      hd.appendChild(el("div", { style: { fontSize: "13px", color: "#fbbf24", letterSpacing: "1px", whiteSpace: "nowrap" } }, r.stars));
      card.appendChild(hd);
      // bias + direction pills
      const pills = el("div", { style: { display: "flex", gap: "8px", marginBottom: "8px", flexWrap: "wrap" } });
      pills.appendChild(el("span", { style: { fontSize: "10.5px", fontWeight: "800", color: "#000", background: biasCol(r.bias), borderRadius: "4px", padding: "2px 8px" } }, r.bias));
      pills.appendChild(el("span", { style: { fontSize: "10.5px", fontWeight: "700", color: C.cyan, border: `1px solid ${C.cyan}`, borderRadius: "4px", padding: "2px 8px" } }, r.direction));
      card.appendChild(pills);
      // the trade
      const trade = el("div", { style: { fontSize: "12.5px", fontWeight: "700", color: "#e2e8f0", background: "#0b1220", border: "1px solid #1e293b", borderRadius: "6px", padding: "8px 10px", marginBottom: "8px" } });
      trade.innerHTML = "▶ " + (r.trade || "");
      card.appendChild(trade);
      // metrics chips
      if (r.metrics) {
        const chips = el("div", { style: { display: "flex", gap: "6px", flexWrap: "wrap", marginBottom: "8px" } });
        Object.entries(r.metrics).forEach(([k, v]) => {
          chips.appendChild(el("span", { style: { fontSize: "10px", color: C.muted, background: "#0f1826", borderRadius: "4px", padding: "2px 7px" } },
            [document.createTextNode(`${k.replace(/_/g, " ")}: `), el("b", { style: { color: C.text } }, String(v))]));
        });
        card.appendChild(chips);
      }
      // rationale
      (r.rationale || []).forEach(rz => {
        const li = el("div", { style: { fontSize: "11.5px", color: C.text, lineHeight: "1.5", marginBottom: "4px" } });
        li.innerHTML = "• " + mdBold(rz);
        card.appendChild(li);
      });
      // risk + invalidation
      if (r.risk) { const rk = el("div", { style: { fontSize: "11px", color: "#fca5a5", marginTop: "6px", lineHeight: "1.45" } }); rk.innerHTML = "<b>Risk:</b> " + r.risk; card.appendChild(rk); }
      if (r.invalidation) { const iv = el("div", { style: { fontSize: "11px", color: C.muted, marginTop: "3px", lineHeight: "1.45" } }); iv.innerHTML = "<b>Invalidation:</b> " + r.invalidation; card.appendChild(iv); }
      deskGrid.appendChild(card);
    });
    if ((d.desk || []).length) box.appendChild(deskGrid);

    // ===== TERM STRUCTURE & CRACK CURVES (charts) =====
    const curves = d.curves || {};
    function curveSection(title, group, colorMap) {
      const keys = Object.keys(group || {});
      if (!keys.length) return;
      box.appendChild(el("div", { style: { fontSize: "13px", fontWeight: "800", color: C.cyan, margin: "6px 0 10px", textTransform: "uppercase", letterSpacing: "0.5px" } }, title));
      const grid = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))", gap: "14px", marginBottom: "20px" } });
      keys.forEach((k, gi) => {
        const cv = group[k];
        const cell = el("div", { style: { background: C.card, border: "1px solid #1e293b", borderRadius: "8px", padding: "10px 12px" } });
        const shp = cv.shape;
        const shpC = shp === "backwardation" ? C.green : shp === "contango" ? C.red : C.muted;
        const hh = el("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "2px" } });
        hh.appendChild(el("div", { style: { fontSize: "12px", fontWeight: "700", color: C.text } }, cv.display || k));
        hh.appendChild(el("div", { style: { fontSize: "11px", fontWeight: "800", color: shpC } }, shp));
        cell.appendChild(hh);
        cell.appendChild(el("div", { style: { fontSize: "10.5px", color: C.muted, marginBottom: "6px" } },
          [document.createTextNode(`M1 ${cv.m1} · M1–M2 `),
           el("b", { style: { color: shpC } }, sgn(cv.m1_m2)),
           document.createTextNode(` · front→back ${sgn(cv.front_back)} · ${cv.units || ""}`)]));
        const chartDiv = el("div", { style: { height: "180px" } });
        cell.appendChild(chartDiv);
        grid.appendChild(cell);
        loadPlotly(() => {
          const xs = cv.tenors.map(t => t.tenor);
          const ys = cv.tenors.map(t => t.last);
          Plotly.newPlot(chartDiv, [{
            x: xs, y: ys, type: "scatter", mode: "lines+markers",
            line: { color: colorMap[gi % colorMap.length], width: 2.5 }, marker: { size: 6 },
            hovertemplate: "%{x}: %{y}<extra></extra>",
          }], {
            ...plotLayout, height: 180, margin: { l: 44, r: 10, t: 8, b: 24 },
            xaxis: { ...plotLayout.xaxis, type: "category" },
            yaxis: { ...plotLayout.yaxis },
            showlegend: false,
          }, { responsive: true, displayModeBar: false });
        });
      });
      box.appendChild(grid);
    }
    const curveColors = ["#06b6d4", "#f59e0b", "#8b5cf6", "#10b981", "#ef4444", "#f472b6"];
    curveSection("Crude Term Structure (flat, M1–M6)", curves.flat, curveColors);
    curveSection("Crack Curves (M1–M5)", curves.cracks, ["#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#06b6d4", "#f472b6"]);
    curveSection("OTC Swap Crack Curves (M0–M4)", curves.swaps, ["#8b5cf6", "#06b6d4", "#10b981", "#f59e0b", "#ef4444", "#f472b6", "#a3e635"]);

    // Snapshot tables: flat + curve + positioning
    function tableCard(title, headers, rows) {
      const c = el("div", { style: { background: C.card, border: "1px solid #1e293b", borderRadius: "8px", padding: "12px 14px", marginBottom: "14px" } });
      c.appendChild(el("div", { style: { fontSize: "12px", fontWeight: "800", color: C.cyan, marginBottom: "8px", textTransform: "uppercase", letterSpacing: "0.5px" } }, title));
      const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11.5px" } });
      const thr = el("tr", {});
      headers.forEach((h, i) => thr.appendChild(el("th", { style: { textAlign: i === 0 ? "left" : "right", color: C.muted, padding: "4px 8px", borderBottom: `1px solid ${C.border}`, fontWeight: "600" } }, h)));
      tbl.appendChild(thr);
      rows.forEach(r => {
        const tr = el("tr", {});
        r.forEach((cell, i) => {
          const isNum = i > 0;
          const val = typeof cell === "object" ? cell.v : cell;
          const col = typeof cell === "object" ? cell.c : C.text;
          tr.appendChild(el("td", { style: { textAlign: isNum ? "right" : "left", color: col, padding: "4px 8px", borderBottom: "1px solid #131c2b", fontWeight: i === 0 ? "600" : "500" } }, val));
        });
        tbl.appendChild(tr);
      });
      c.appendChild(tbl); return c;
    }

    // Flat + curve merged
    const flatRows = Object.entries(d.flat || {}).map(([k, v]) => {
      const cv = (d.curve || {})[k];
      return [k, `$${v.last.toFixed(2)}`, { v: sgn(v.wow), c: chgC(v.wow) }, `${v.pctile}th`,
        cv ? { v: cv.shape, c: cv.shape === "backwardation" ? C.green : cv.shape === "contango" ? C.red : C.muted } : "—",
        cv ? { v: sgn(cv.m1_m2), c: chgC(cv.m1_m2) } : "—"];
    });
    box.appendChild(tableCard("Flat Price & Term Structure", ["Benchmark", "Last", "Δ w/w", "Hist %ile", "Curve", "M1-M2"], flatRows));

    // Positioning
    const cotRows = Object.entries(d.cot || {}).map(([k, v]) => [k.toUpperCase(), v.mm_net.toLocaleString(), { v: sgn(v.wow, 0), c: chgC(v.wow) }, `${v.pctile}th`, { v: sgn(v.z), c: chgC(v.z) }, v.stance]);
    if (cotRows.length) box.appendChild(tableCard("Managed-Money Positioning (COT)", ["Contract", "Net", "Δ w/w", "%ile", "z", "Stance"], cotRows));

    // Cracks + swaps
    const crackRows = Object.entries(d.cracks || {}).map(([k, v]) => [k, v.last.toFixed(2), { v: sgn(v.wow), c: chgC(v.wow) }, `${v.pctile}th`, v.trend]);
    if (crackRows.length) box.appendChild(tableCard("Crack Spreads", ["Crack", "Last", "Δ w/w", "%ile", "Trend"], crackRows));
    const swapRows = Object.entries(d.swaps || {}).map(([k, v]) => [k, v.last.toFixed(2), { v: sgn(v.wow), c: chgC(v.wow) }, `${v.pos_in_range}%`, v.trend]);
    if (swapRows.length) box.appendChild(tableCard("OTC Swaps (balmo / M0)", ["Swap", "Last", "Δ w/w", "Range pos", "Trend"], swapRows));

    // Margins
    const mgRows = (d.margins || []).map(m => [`${m.name} (${m.region})`, `$${m.last.toFixed(2)}`, { v: sgn(m.wow), c: chgC(m.wow) }, `${m.seasonal_pctile}th`, m.season]);
    if (mgRows.length) box.appendChild(tableCard("Refinery Margins", ["Margin", "Last", "Δ w/w", "Seasonal %ile", "Season"], mgRows));

    // Linkage
    const lc = el("div", { style: { background: C.card, border: "1px solid #1e293b", borderRadius: "8px", padding: "12px 14px" } });
    lc.appendChild(el("div", { style: { fontSize: "12px", fontWeight: "800", color: C.purple, marginBottom: "8px", textTransform: "uppercase", letterSpacing: "0.5px" } }, "Flows / Outages → Product Impact"));
    (d.linkage || []).forEach(l => {
      const row = el("div", { style: { marginBottom: "8px" } });
      row.appendChild(el("div", { style: { fontSize: "12px", fontWeight: "700", color: C.amber } }, l.signal));
      row.appendChild(el("div", { style: { fontSize: "11.5px", color: C.text, lineHeight: "1.5" } }, l.impact));
      lc.appendChild(row);
    });
    box.appendChild(lc);
  }

  async function renderFGE(box) {
    box.innerHTML = "";

    // Controls row
    const controls = el("div", { style: { display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px", flexWrap: "wrap" } });

    // Region selector
    controls.appendChild(el("span", { style: { fontSize: "12px", color: C.muted } }, "Region:"));
    const regSel = el("select", { style: { background: C.card, color: C.text, border: `1px solid ${C.border}`, borderRadius: "6px", padding: "8px 12px", fontSize: "12px" } });
    const allRegs = ["Global", "North America", "Europe", "Latin America", "Middle East", "FSU", "Asia Pacific", "Africa"];
    allRegs.forEach(r => {
      const o = el("option", { value: r }, r);
      if (r === fgeRegion) o.selected = true;
      regSel.appendChild(o);
    });
    regSel.onchange = () => { fgeRegion = regSel.value; };
    controls.appendChild(regSel);

    // Load button
    const contentBox = el("div");
    const loadBtn = el("button", { style: { background: `linear-gradient(135deg, ${C.amber}, #d97706)`, color: "#000", border: "none", borderRadius: "6px", padding: "8px 18px", fontSize: "12px", fontWeight: "700", cursor: "pointer" }, onClick: async () => {
      loadBtn.textContent = "Loading..."; loadBtn.disabled = true;
      try {
        fgeData = await fetchFGE(fgeRegion);
        renderFGEContent(contentBox, fgeData);
      } catch (e) { contentBox.innerHTML = `<div style="color:${C.red};padding:20px;">Error: ${e.message}</div>`; }
      loadBtn.textContent = "Load Data"; loadBtn.disabled = false;
    } }, "Load Data");
    controls.appendChild(loadBtn);

    controls.appendChild(el("span", { style: { fontSize: "10px", color: C.muted, marginLeft: "auto" } }, "Source: FGE Nexant ECA · World Oil Market Report"));
    box.appendChild(controls);
    box.appendChild(contentBox);

    // Auto-load Global
    loadBtn.click();
  }

  // ========== GENSCAPE REFINERY RUNS (OFFLINE CAPACITY) ==========
  let gspeRegion = "US Total";
  let gspeCategory = "All";
  let gspeStartYear = 2020;
  let gspeEndYear = 2026;

  async function fetchGspeData(region, category, startYear, endYear) {
    const params = new URLSearchParams();
    if (region) params.append("region", region);
    if (category) params.append("category", category);
    params.append("start_year", startYear);
    params.append("end_year", endYear);
    const r = await fetch(`/api/genscape/offline_capacity?${params}`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }

  async function fetchGspeFacilities(region, category) {
    const params = new URLSearchParams();
    if (region) params.append("region", region);
    if (category) params.append("category", category);
    const r = await fetch(`/api/genscape/facilities?${params}`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }

  async function fetchGspePipeline() {
    const r = await fetch("/api/genscape/pipeline_flows?frequency=daily&limit=5000");
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }

  async function fetchGspeOfflineTable(days = 14, region = "US") {
    const r = await fetch(`/api/genscape/offline_table?days=${days}&region=${encodeURIComponent(region)}`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }

  async function fetchGspeRefAnalytics() {
    const r = await fetch("/api/genscape/refinery_analytics");
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }

  async function fetchGspeCushingAnalytics() {
    const r = await fetch("/api/genscape/cushing_analytics");
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }

  async function fetchGspeLastPulled() {
    try { const r = await fetch("/api/genscape/last_pulled"); if (r.ok) { const d = await r.json(); return d.last_pulled; } } catch(e) {}
    return null;
  }

  async function refreshGspeData(lookbackDays = 3) {
    const r = await fetch(`/api/genscape/refresh?lookback_days=${lookbackDays}`, { method: "POST" });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }

  function renderOfflineTable(container, tblData) {
    container.innerHTML = "";
    if (!tblData || !tblData.dates || tblData.dates.length === 0) {
      container.innerHTML = `<div style="color:${C.muted};padding:10px;">No offline data available for this region/period</div>`;
      return;
    }
    const dates = tblData.dates;
    const paddTotals = tblData.padd_totals || {};
    const weeklyAvgs = tblData.weekly_avgs || {};
    const mtdStats = tblData.mtd_stats || {};
    const majorCats = tblData.major_cats || ["CDU","FCC","HCU","COK","RFM","VDU"];
    const padds = tblData.padds || [];
    const isUS = tblData.is_us !== false;
    const totalLabel = tblData.total_label || "US";

    const cellS = "padding:4px 5px;text-align:right;font-size:10px;border-bottom:1px solid " + C.border + "20;white-space:nowrap;";
    const hdrS = "padding:5px 5px;text-align:right;font-size:9px;font-weight:600;color:" + C.muted + ";border-bottom:1px solid " + C.border + ";white-space:nowrap;";
    const catS = "padding:5px 5px;font-size:11px;font-weight:700;color:" + C.amber + ";border-bottom:1px solid " + C.border + ";background:#1e293b;";
    const regionS = "padding:4px 5px;font-size:10px;color:" + C.cyan + ";font-weight:600;border-bottom:1px solid " + C.border + "20;";

    // Build main totals table
    const tbl = document.createElement("table");
    tbl.style.cssText = "width:100%;border-collapse:collapse;font-family:monospace;margin-bottom:16px;";

    // Header row
    const thead = document.createElement("thead");
    const hr = document.createElement("tr");
    hr.innerHTML = `<th style="${hdrS}text-align:left;">Unit</th><th style="${hdrS}text-align:left;">Region</th>`;
    dates.forEach(d => { hr.innerHTML += `<th style="${hdrS}">${d}</th>`; });
    hr.innerHTML += `<th style="${hdrS}background:#1a2332;">Wk 1</th><th style="${hdrS}background:#1a2332;">Wk 2</th><th style="${hdrS}background:#1a2332;">Δ</th><th style="${hdrS}background:#1a2332;">MTD</th><th style="${hdrS}background:#1a2332;">M/M</th>`;
    thead.appendChild(hr);
    tbl.appendChild(thead);

    const tbody = document.createElement("tbody");
    majorCats.forEach(cat => {
      const catData = paddTotals[cat] || {};
      const catWk = weeklyAvgs[cat] || {};
      const catMtd = mtdStats[cat] || {};
      // Category header row (total for selected region)
      const totVals = catData[totalLabel] || [];
      const totWk = catWk[totalLabel] || {};
      const cr = document.createElement("tr");
      cr.style.background = "#111827";
      let crHtml = `<td style="${catS}">${cat}</td><td style="${catS}color:${C.text};">${totalLabel}</td>`;
      totVals.forEach(v => {
        const color = v > 0 ? C.text : C.muted + "40";
        crHtml += `<td style="${cellS}color:${color};font-weight:600;background:#111827;">${v > 0 ? Math.round(v).toLocaleString() : ""}</td>`;
      });
      const deltaColor = totWk.delta > 0 ? C.red : totWk.delta < 0 ? C.green : C.muted;
      crHtml += `<td style="${cellS}background:#1a2332;font-weight:700;">${Math.round(totWk.wk1 || 0).toLocaleString()}</td>`;
      crHtml += `<td style="${cellS}background:#1a2332;font-weight:700;">${Math.round(totWk.wk2 || 0).toLocaleString()}</td>`;
      crHtml += `<td style="${cellS}background:#1a2332;color:${deltaColor};font-weight:700;">${totWk.delta > 0 ? "+" : ""}${Math.round(totWk.delta || 0)}</td>`;
      crHtml += `<td style="${cellS}background:#1a2332;font-weight:600;">${Math.round(catMtd.mtd || 0).toLocaleString()}</td>`;
      const momColor = catMtd.mom > 0 ? C.red : catMtd.mom < 0 ? C.green : C.muted;
      crHtml += `<td style="${cellS}background:#1a2332;color:${momColor};font-weight:600;">${catMtd.mom > 0 ? "+" : ""}${Math.round(catMtd.mom || 0)}</td>`;
      cr.innerHTML = crHtml;
      tbody.appendChild(cr);

      // Sub-region rows (PADDs for US, empty for non-US)
      padds.forEach(p => {
        const pVals = catData[p] || [];
        const pWk = catWk[p] || {};
        const allZero = pVals.every(v => v === 0) && (pWk.wk1 || 0) === 0 && (pWk.wk2 || 0) === 0;
        if (allZero) return;
        const pr = document.createElement("tr");
        let prHtml = `<td style="${cellS}"></td><td style="${regionS}">${p.replace("PADD","P")}</td>`;
        pVals.forEach(v => {
          const color = v > 0 ? C.text : C.muted + "20";
          prHtml += `<td style="${cellS}color:${color};">${v > 0 ? Math.round(v).toLocaleString() : ""}</td>`;
        });
        const pdColor = pWk.delta > 0 ? "#fca5a5" : pWk.delta < 0 ? "#86efac" : C.muted;
        prHtml += `<td style="${cellS}background:#1a2332;">${pWk.wk1 > 0 ? Math.round(pWk.wk1).toLocaleString() : ""}</td>`;
        prHtml += `<td style="${cellS}background:#1a2332;">${pWk.wk2 > 0 ? Math.round(pWk.wk2).toLocaleString() : ""}</td>`;
        prHtml += `<td style="${cellS}background:#1a2332;color:${pdColor};">${pWk.delta !== 0 ? (pWk.delta > 0 ? "+" : "") + Math.round(pWk.delta) : ""}</td>`;
        prHtml += `<td style="${cellS}background:#1a2332;"></td><td style="${cellS}background:#1a2332;"></td>`;
        pr.innerHTML = prHtml;
        tbody.appendChild(pr);
      });
    });
    tbl.appendChild(tbody);
    container.appendChild(tbl);

    // Facility-level detail tables for ALL categories
    const facDetails = tblData.facility_details || {};
    const catColors = { CDU: "#f59e0b", FCC: "#3b82f6", HCU: "#10b981", COK: "#ef4444", RFM: "#a855f7", VDU: "#06b6d4", HT: "#84cc16", ALK: "#a855f7", ISO: "#67e8f9" };
    majorCats.forEach(cat => {
      const catInfo = facDetails[cat];
      if (!catInfo || !catInfo.facilities || catInfo.facilities.length === 0) return;

      container.appendChild(el("div", { style: { fontSize: "12px", fontWeight: "700", color: catColors[cat] || C.cyan, marginTop: "20px", marginBottom: "8px", borderTop: "1px solid " + C.border, paddingTop: "12px" } },
        `${cat}  (${catInfo.label})`));

      const ftbl = document.createElement("table");
      ftbl.style.cssText = "width:100%;border-collapse:collapse;font-family:monospace;";
      const fhd = document.createElement("thead");
      const fhr = document.createElement("tr");
      fhr.innerHTML = `<th style="${hdrS}text-align:left;">${isUS ? "PADD" : "Region"}</th><th style="${hdrS}text-align:left;">Refinery</th><th style="${hdrS}text-align:left;">Unit</th>`;
      dates.forEach(d => { fhr.innerHTML += `<th style="${hdrS}">${d}</th>`; });
      fhr.innerHTML += `<th style="${hdrS}background:#1a2332;">Wk 1</th><th style="${hdrS}background:#1a2332;">Δ</th><th style="${hdrS}background:#1a2332;">MTD</th><th style="${hdrS}background:#1a2332;">M/M</th>`;
      fhd.appendChild(fhr);
      ftbl.appendChild(fhd);

      const ftb = document.createElement("tbody");
      catInfo.facilities.forEach(f => {
        const fr = document.createElement("tr");
        let fHtml = `<td style="${regionS}">${isUS ? f.region.replace("PADD","P") : f.region}</td>`;
        fHtml += `<td style="${cellS}text-align:left;color:${C.text};font-weight:600;">${f.facility}</td>`;
        fHtml += `<td style="${cellS}text-align:left;color:${C.muted};">${f.unit}</td>`;
        f.daily.forEach(v => {
          const color = v > 0 ? C.text : C.muted + "20";
          fHtml += `<td style="${cellS}color:${color};">${v > 0 ? Math.round(v) : ""}</td>`;
        });
        fHtml += `<td style="${cellS}background:#1a2332;font-weight:600;">${f.wk1 > 0 ? Math.round(f.wk1) : ""}</td>`;
        const dColor = f.delta > 0 ? "#fca5a5" : f.delta < 0 ? "#86efac" : C.muted;
        fHtml += `<td style="${cellS}background:#1a2332;color:${dColor};">${f.delta !== 0 ? (f.delta > 0 ? "+" : "") + Math.round(f.delta) : ""}</td>`;
        fHtml += `<td style="${cellS}background:#1a2332;">${f.mtd > 0 ? Math.round(f.mtd) : ""}</td>`;
        const mColor = f.mom > 0 ? "#fca5a5" : f.mom < 0 ? "#86efac" : C.muted;
        fHtml += `<td style="${cellS}background:#1a2332;color:${mColor};">${f.mom !== 0 ? (f.mom > 0 ? "+" : "") + Math.round(f.mom) : ""}</td>`;
        fr.innerHTML = fHtml;
        ftb.appendChild(fr);
      });
      ftbl.appendChild(ftb);
      container.appendChild(ftbl);
    });

    const exclNote = isUS ? "Excl: Lyondell-Houston, Valero-Benicia, Phillips66-Carson/Wilmington, Shell-Sarnia" : "";
    container.appendChild(el("div", { style: { fontSize: "9px", color: C.muted, marginTop: "12px" } },
      `Latest: ${tblData.latest_date || "N/A"} | ${dates.length} days shown | Region: ${totalLabel}${exclNote ? " | " + exclNote : ""}`));
  }

  // --- Professional Plotly layout for Genscape ---
  const gsPlotLayout = {
    paper_bgcolor: "transparent", plot_bgcolor: "transparent",
    font: { color: C.text, family: "'Inter', 'Segoe UI', system-ui, sans-serif", size: 11 },
    margin: { l: 60, r: 30, t: 50, b: 50 },
    legend: { orientation: "h", yanchor: "bottom", y: 1.02, xanchor: "right", x: 1, font: { size: 10 } },
    xaxis: { gridcolor: "#1e293b", linecolor: "#334155", zerolinecolor: "#334155" },
    yaxis: { gridcolor: "#1e293b", linecolor: "#334155", zerolinecolor: "#334155" },
    hoverlabel: { bgcolor: "#1e293b", bordercolor: "#475569", font: { color: "#f1f5f9", size: 11 } },
  };
  const gsTitle = (text, sub) => ({ text: `<b>${text}</b>${sub ? "<br><span style='font-size:10px;color:#94a3b8'>" + sub + "</span>" : ""}`, font: { color: "#f8fafc", size: 14 }, x: 0, xanchor: "left", xref: "paper" });
  const gsCatColors = { CDU: "#ef4444", FCC: "#f59e0b", HCU: "#10b981", COK: "#8b5cf6", RFM: "#ec4899", VDU: "#06b6d4", HT: "#84cc16", ALK: "#a855f7", ISO: "#67e8f9", GAS: "#78716c", SUL: "#fbbf24", HGP: "#6366f1" };
  const gsPaddColors = { PADD1: "#3b82f6", PADD2: "#10b981", PADD3: "#ef4444", PADD4: "#8b5cf6", PADD5: "#f59e0b" };
  const gsYearColors = { 2020: "#6b7280", 2021: "#9ca3af", 2022: "#a78bfa", 2023: "#c084fc", 2024: "#22c55e", 2025: "#3b82f6", 2026: "#f59e0b" };

  function gsSection(title, subtitle) {
    const wrap = el("div", { style: { marginTop: "28px", marginBottom: "10px" } });
    wrap.appendChild(el("div", { style: { fontSize: "16px", fontWeight: "800", color: "#f8fafc", letterSpacing: "-0.02em" } }, title));
    if (subtitle) wrap.appendChild(el("div", { style: { fontSize: "11px", color: "#94a3b8", marginTop: "2px" } }, subtitle));
    wrap.appendChild(el("div", { style: { height: "2px", background: "linear-gradient(90deg, #f59e0b, transparent)", marginTop: "6px" } }));
    return wrap;
  }

  function gsCard(title, content, opts) {
    const c = el("div", { style: { background: "#0f172a", borderRadius: "10px", border: "1px solid #1e293b", padding: "16px", marginBottom: "14px", ...(opts?.style || {}) } });
    if (title) {
      c.appendChild(el("div", { style: { fontSize: "12px", fontWeight: "700", color: "#e2e8f0", marginBottom: "10px", textTransform: "uppercase", letterSpacing: "0.05em" } }, title));
    }
    if (typeof content === "string") { c.innerHTML += content; }
    else if (content) { c.appendChild(content); }
    return c;
  }

  function gsStatCard(label, value, color, sub) {
    const c = el("div", { style: { background: "#0f172a", borderRadius: "10px", border: "1px solid #1e293b", padding: "14px 16px", flex: "1", minWidth: "140px" } });
    c.appendChild(el("div", { style: { fontSize: "10px", color: "#94a3b8", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "4px" } }, label));
    c.appendChild(el("div", { style: { fontSize: "22px", fontWeight: "800", color: color || "#f8fafc", letterSpacing: "-0.02em" } }, String(value)));
    if (sub) c.appendChild(el("div", { style: { fontSize: "10px", color: "#64748b", marginTop: "2px" } }, sub));
    return c;
  }

  function renderGspeContent(box, data, facData, pipeData) {
    box.innerHTML = "";
    const lineColors = [C.blue, C.amber, C.green, C.red, C.cyan, C.purple, "#f472b6", "#a3e635", "#67e8f9", "#fb923c", "#c084fc", "#22d3ee"];
    let gIdx = 0;
    const gId = () => `gspe-c-${gIdx++}`;
    const deferred = [];
    const regLabel = data.selected_region || "All";
    const catLabel = data.selected_category || "All";

    // Header
    box.appendChild(el("div", { style: { fontSize: "18px", fontWeight: "800", color: "#f8fafc", letterSpacing: "-0.03em", marginBottom: "2px" } },
      `Genscape Refinery Intelligence — ${regLabel}${catLabel !== "All" ? " / " + catLabel : ""}`));
    box.appendChild(el("div", { style: { fontSize: "11px", color: "#64748b", marginBottom: "16px" } },
      `Wood Mackenzie | 163 Refineries, 1,121 Units | Latest: ${data.latest_month || "N/A"} | All values in KBD`));

    // Summary Stats Row
    const sumCat = data.summary_by_category || [];
    const sumReg = data.summary_by_region || [];
    const totalOff = sumCat.reduce((a, c) => a + (c.offline || 0), 0);
    const totalCap = sumCat.reduce((a, c) => a + (c.capacity || 0), 0);
    const pctOff = totalCap > 0 ? (totalOff / totalCap * 100).toFixed(1) : "0";
    const statsRow = el("div", { style: { display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "16px" } });
    statsRow.appendChild(gsStatCard("Total Offline", Math.round(totalOff).toLocaleString() + " KBD", "#ef4444"));
    statsRow.appendChild(gsStatCard("Total Capacity", Math.round(totalCap).toLocaleString() + " KBD", "#3b82f6"));
    statsRow.appendChild(gsStatCard("% Offline", pctOff + "%", "#f59e0b", totalOff > 0 ? Math.round(totalOff / (totalCap / sumReg.length || 1)).toLocaleString() + " avg per region" : ""));
    statsRow.appendChild(gsStatCard("Regions", sumReg.length, "#06b6d4"));
    statsRow.appendChild(gsStatCard("Categories", sumCat.length, "#10b981"));
    box.appendChild(statsRow);

    // ===================== SECTION 1: 2-WEEK OFFLINE TABLE =====================
    const tblRegion = gspeRegion === "All" || gspeRegion === "US Total" ? "US" : gspeRegion;
    const tblTitle = tblRegion === "US" ? "PADD Offline Capacity — 2-Week Daily View" : `${tblRegion} Offline Capacity — 2-Week Daily View`;
    const tblSubtitle = tblRegion === "US" ? "Excludes permanently shut refineries (Lyondell-Houston, Valero-Benicia, Phillips 66-Carson/Wilmington) and Shell-Sarnia (Canada)" : `Showing all offline units for ${tblRegion} — facility-level detail below`;
    box.appendChild(gsSection(tblTitle, tblSubtitle));
    {
      const tblBox = el("div", { id: "gspe-offline-tbl-container" });
      const tblLoadBtn = el("button", { style: { background: "linear-gradient(135deg, #dc2626, #991b1b)", color: "#fff", border: "none", borderRadius: "8px", padding: "10px 20px", fontSize: "11px", fontWeight: "700", cursor: "pointer", marginBottom: "10px", letterSpacing: "0.03em" }, onClick: async () => {
        tblLoadBtn.textContent = "Loading..."; tblLoadBtn.disabled = true;
        try {
          const curRegion = gspeRegion === "All" || gspeRegion === "US Total" ? "US" : gspeRegion;
          const tblData = await fetchGspeOfflineTable(14, curRegion);
          renderOfflineTable(tblBox, tblData);
        } catch(e) { tblBox.innerHTML = `<div style="color:${C.red}">Error: ${e.message}</div>`; }
        tblLoadBtn.textContent = "REFRESH TABLE"; tblLoadBtn.disabled = false;
      } }, "LOAD 2-WEEK TABLE");
      const tblCard = gsCard(null, null);
      tblCard.appendChild(el("div", { style: { fontSize: "10px", color: "#94a3b8", marginBottom: "10px" } }, "Wk = 7-day average | \u0394 = week-over-week change | MTD = month-to-date | M/M = month-over-month | Blank = fully online"));
      tblCard.appendChild(tblLoadBtn);
      tblCard.appendChild(tblBox);
      box.appendChild(tblCard);
      setTimeout(() => tblLoadBtn.click(), 100);
    }

    // ===================== SECTION 2: CHARTS =====================
    box.appendChild(gsSection("Offline Capacity Analytics", "Historical trends, seasonal patterns, and unit category breakdown"));

    // 2a. Total Offline Time Series
    {
      const cid = gId();
      const cDiv = el("div", { id: cid, style: { width: "100%", height: "400px" } });
      box.appendChild(gsCard(null, cDiv));
      deferred.push(() => {
        const ts = data.total_series || {};
        const cap = data.capacity_series || {};
        const traces = [
          { x: ts.dates || [], y: ts.values || [], type: "scatter", mode: "lines", name: "Offline Capacity (KBD)", line: { color: "#ef4444", width: 2.5 }, fill: "tozeroy", fillcolor: "rgba(239,68,68,0.1)" },
        ];
        if (cap.dates && cap.dates.length > 0) {
          traces.push({ x: cap.dates, y: cap.values, type: "scatter", mode: "lines", name: "Total Nameplate Capacity", line: { color: "#3b82f6", width: 1.5, dash: "dot" }, yaxis: "y2" });
        }
        Plotly.newPlot(cid, traces, { ...gsPlotLayout, title: gsTitle("US Refinery Offline Capacity", "Daily offline vs total nameplate capacity"), height: 400, yaxis: { ...gsPlotLayout.yaxis, title: { text: "Offline (KBD)", font: { size: 11, color: "#94a3b8" } } }, yaxis2: { overlaying: "y", side: "right", gridcolor: "transparent", title: { text: "Total Capacity (KBD)", font: { size: 11, color: "#94a3b8" } } } }, { responsive: true });
      });
    }

    // 2b. Seasonal Overlay
    {
      const cid = gId();
      const cDiv = el("div", { id: cid, style: { width: "100%", height: "420px" } });
      box.appendChild(gsCard(null, cDiv));
      deferred.push(() => {
        const seas = data.seasonal || {};
        const avg5y = data.avg_5y;
        const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
        const traces = [];
        const yrs = Object.keys(seas).map(Number).sort();
        const recentYrs = yrs.filter(y => y >= 2020);
        recentYrs.forEach(yr => {
          const d = seas[yr];
          traces.push({ x: d.months.map(m => months[m-1]), y: d.values, type: "scatter", mode: "lines+markers", name: String(yr), line: { color: gsYearColors[yr] || lineColors[yr % lineColors.length], width: yr === 2026 ? 3 : yr === 2025 ? 2.5 : 1.5, dash: yr === 2026 ? "dash" : "solid" }, marker: { size: yr >= 2025 ? 6 : 3 } });
        });
        if (avg5y) {
          traces.push({ x: avg5y.months.map(m => months[m-1]).concat(avg5y.months.map(m => months[m-1]).reverse()), y: avg5y.max.concat(avg5y.min.slice().reverse()), type: "scatter", fill: "toself", fillcolor: "rgba(120,113,108,0.12)", line: { color: "transparent" }, name: "2015-19 Range", showlegend: true, hoverinfo: "skip" });
          traces.push({ x: avg5y.months.map(m => months[m-1]), y: avg5y.avg, type: "scatter", mode: "lines", name: "2015-19 Average", line: { color: "#a8a29e", width: 2, dash: "dot" } });
        }
        Plotly.newPlot(cid, traces, { ...gsPlotLayout, title: gsTitle("Seasonal Turnaround Pattern", "Monthly offline capacity by year — spring turnaround season typically peaks Mar-Apr"), height: 420, yaxis: { ...gsPlotLayout.yaxis, title: { text: "Offline Capacity (KBD)", font: { size: 11, color: "#94a3b8" } } } }, { responsive: true });
      });
    }

    // 2c. Offline by Category (Stacked Area)
    {
      const cid = gId();
      const cDiv = el("div", { id: cid, style: { width: "100%", height: "400px" } });
      box.appendChild(gsCard(null, cDiv));
      deferred.push(() => {
        const byCat = data.by_category || {};
        const cats = Object.keys(byCat).sort((a,b) => {
          const aSum = (byCat[a].values || []).reduce((s,v)=>s+v,0);
          const bSum = (byCat[b].values || []).reduce((s,v)=>s+v,0);
          return bSum - aSum;
        });
        const traces = cats.slice(0, 10).map((cat, i) => ({
          x: byCat[cat].dates, y: byCat[cat].values, type: "scatter", mode: "lines", name: cat,
          stackgroup: "one", line: { color: gsCatColors[cat] || lineColors[i], width: 0.5 },
          fillcolor: (gsCatColors[cat] || lineColors[i]) + "40",
        }));
        Plotly.newPlot(cid, traces, { ...gsPlotLayout, title: gsTitle("Offline Capacity by Unit Type", "Stacked area — CDU dominates during heavy turnaround periods"), height: 400, yaxis: { ...gsPlotLayout.yaxis, title: { text: "KBD", font: { size: 11, color: "#94a3b8" } } } }, { responsive: true });
      });
    }

    // 2d. Offline by Region (Stacked Area)
    {
      const cid = gId();
      const cDiv = el("div", { id: cid, style: { width: "100%", height: "400px" } });
      box.appendChild(gsCard(null, cDiv));
      deferred.push(() => {
        const byReg = data.by_region || {};
        const regs = Object.keys(byReg).sort();
        const regColors = { PADD1: "#3b82f6", PADD2: "#10b981", PADD3: "#ef4444", PADD4: "#8b5cf6", PADD5: "#f59e0b", Canada: "#06b6d4", Europe: "#f472b6", "United Kingdom": "#a3e635" };
        const traces = regs.map((r, i) => ({
          x: byReg[r].dates, y: byReg[r].values, type: "scatter", mode: "lines", name: r,
          stackgroup: "one", line: { color: regColors[r] || lineColors[i], width: 0.5 },
          fillcolor: (regColors[r] || lineColors[i]) + "40",
        }));
        Plotly.newPlot(cid, traces, { ...gsPlotLayout, title: gsTitle("Offline Capacity by Region", "PADD breakdown — Gulf Coast (PADD 3) has highest refining concentration"), height: 400, yaxis: { ...gsPlotLayout.yaxis, title: { text: "KBD", font: { size: 11, color: "#94a3b8" } } } }, { responsive: true });
      });
    }

    // ===================== SECTION 3: SUMMARY TABLES =====================
    box.appendChild(gsSection("Summary Tables", "Latest month offline capacity breakdown by category, region, and facility"));

    // Category Table
    {
      const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px" } });
      const hd = el("thead");
      const hr = el("tr");
      ["Unit Type", "Offline (KBD)", "Total Capacity (KBD)", "% Offline", "Units Offline"].forEach(h =>
        hr.appendChild(el("th", { style: { padding: "8px 6px", textAlign: h === "Unit Type" ? "left" : "right", color: "#94a3b8", borderBottom: "2px solid #334155", fontSize: "10px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.05em" } }, h)));
      hd.appendChild(hr); tbl.appendChild(hd);
      const tb = el("tbody");
      sumCat.forEach((row, i) => {
        const tr = el("tr", { style: { borderBottom: "1px solid #1e293b", background: i % 2 === 0 ? "transparent" : "#0f172a30" } });
        const catColor = gsCatColors[row.alternativeCategory] || "#94a3b8";
        tr.appendChild(el("td", { style: { padding: "7px 6px", fontWeight: "700", fontSize: "11px" } }, el("span", { style: { color: catColor, borderLeft: `3px solid ${catColor}`, paddingLeft: "8px" } }, row.alternativeCategory)));
        tr.appendChild(el("td", { style: { padding: "7px 6px", textAlign: "right", color: "#ef4444", fontWeight: "600" } }, fmt(Math.round(row.offline))));
        tr.appendChild(el("td", { style: { padding: "7px 6px", textAlign: "right", color: "#94a3b8" } }, fmt(Math.round(row.capacity))));
        tr.appendChild(el("td", { style: { padding: "7px 6px", textAlign: "right", color: "#f59e0b", fontWeight: "600" } }, (row.pct_offline || 0).toFixed(1) + "%"));
        tr.appendChild(el("td", { style: { padding: "7px 6px", textAlign: "right", color: "#64748b" } }, fmt(row.units)));
        tb.appendChild(tr);
      });
      tbl.appendChild(tb);
      box.appendChild(gsCard("OFFLINE BY UNIT TYPE", tbl));
    }

    // Region Table
    {
      const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px" } });
      const hd = el("thead");
      const hr = el("tr");
      ["Region", "Offline (KBD)", "Total Capacity (KBD)", "% Offline", "Units Offline"].forEach(h =>
        hr.appendChild(el("th", { style: { padding: "8px 6px", textAlign: h === "Region" ? "left" : "right", color: "#94a3b8", borderBottom: "2px solid #334155", fontSize: "10px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.05em" } }, h)));
      hd.appendChild(hr); tbl.appendChild(hd);
      const tb = el("tbody");
      sumReg.forEach((row, i) => {
        const tr = el("tr", { style: { borderBottom: "1px solid #1e293b", background: i % 2 === 0 ? "transparent" : "#0f172a30" } });
        const regColor = gsPaddColors[row.region] || "#94a3b8";
        tr.appendChild(el("td", { style: { padding: "7px 6px", fontWeight: "700", fontSize: "11px" } }, el("span", { style: { color: regColor, borderLeft: `3px solid ${regColor}`, paddingLeft: "8px" } }, row.region)));
        tr.appendChild(el("td", { style: { padding: "7px 6px", textAlign: "right", color: "#ef4444", fontWeight: "600" } }, fmt(Math.round(row.offline))));
        tr.appendChild(el("td", { style: { padding: "7px 6px", textAlign: "right", color: "#94a3b8" } }, fmt(Math.round(row.capacity))));
        tr.appendChild(el("td", { style: { padding: "7px 6px", textAlign: "right", color: "#f59e0b", fontWeight: "600" } }, (row.pct_offline || 0).toFixed(1) + "%"));
        tr.appendChild(el("td", { style: { padding: "7px 6px", textAlign: "right", color: "#64748b" } }, fmt(row.units)));
        tb.appendChild(tr);
      });
      tbl.appendChild(tb);
      box.appendChild(gsCard("OFFLINE BY REGION", tbl));
    }

    // Facility Table
    if (facData && facData.facilities && facData.facilities.length > 0) {
      const facs = facData.facilities;
      const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px" } });
      const hd = el("thead");
      const hr = el("tr");
      ["Refinery", "Region", "Offline (KBD)", "Capacity (KBD)", "% Offline", "Units Down", "Total Units"].forEach(h =>
        hr.appendChild(el("th", { style: { padding: "8px 6px", textAlign: h === "Refinery" || h === "Region" ? "left" : "right", color: "#94a3b8", borderBottom: "2px solid #334155", fontSize: "10px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.05em" } }, h)));
      hd.appendChild(hr); tbl.appendChild(hd);
      const tb = el("tbody");
      facs.forEach((row, i) => {
        const tr = el("tr", { style: { borderBottom: "1px solid #1e293b", background: i % 2 === 0 ? "transparent" : "#0f172a30" } });
        tr.appendChild(el("td", { style: { padding: "6px 6px", color: "#e2e8f0", fontWeight: "600", fontSize: "11px" } }, row.facilityName));
        tr.appendChild(el("td", { style: { padding: "6px 6px", color: gsPaddColors[row.region] || "#94a3b8", fontSize: "10px", fontWeight: "600" } }, row.region));
        tr.appendChild(el("td", { style: { padding: "6px 6px", textAlign: "right", color: "#ef4444", fontWeight: "600" } }, fmt(Math.round(row.offline))));
        tr.appendChild(el("td", { style: { padding: "6px 6px", textAlign: "right", color: "#94a3b8" } }, fmt(Math.round(row.capacity))));
        const pct = row.pct_offline || 0;
        const pctColor = pct >= 50 ? "#ef4444" : pct >= 20 ? "#f59e0b" : "#10b981";
        tr.appendChild(el("td", { style: { padding: "6px 6px", textAlign: "right", color: pctColor, fontWeight: "600" } }, pct.toFixed(1) + "%"));
        tr.appendChild(el("td", { style: { padding: "6px 6px", textAlign: "right", color: "#ef4444" } }, fmt(row.units_offline)));
        tr.appendChild(el("td", { style: { padding: "6px 6px", textAlign: "right", color: "#64748b" } }, fmt(row.total_units)));
        tb.appendChild(tr);
      });
      tbl.appendChild(tb);
      box.appendChild(gsCard("TOP REFINERIES — OFFLINE CAPACITY (LATEST MONTH)", tbl));
    }

    // ===================== SECTION 4: PIPELINE FLOWS =====================
    if (pipeData && pipeData.daily_flows) {
      box.appendChild(gsSection("Cushing & Patoka Pipeline Flows", "Satellite/sensor-measured daily crude oil flows — Mid-Continent hub | Latest: " + (pipeData.latest_date || "N/A")));

      // Pipeline Stats
      const pipeStats = el("div", { style: { display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "14px" } });
      pipeStats.appendChild(gsStatCard("Cushing Incoming", Math.round(pipeData.cushing_incoming || 0).toLocaleString() + " BPD", "#10b981"));
      pipeStats.appendChild(gsStatCard("Cushing Outgoing", Math.round(pipeData.cushing_outgoing || 0).toLocaleString() + " BPD", "#ef4444"));
      const netVal = pipeData.cushing_net || 0;
      pipeStats.appendChild(gsStatCard("Net Flow", (netVal > 0 ? "+" : "") + Math.round(netVal).toLocaleString() + " BPD", netVal >= 0 ? "#10b981" : "#ef4444", netVal >= 0 ? "Implied Build" : "Implied Draw"));
      box.appendChild(pipeStats);

      // Pipeline Flows Chart
      {
        const cid = gId();
        const cDiv = el("div", { id: cid, style: { width: "100%", height: "380px" } });
        box.appendChild(gsCard(null, cDiv));
        deferred.push(() => {
          const df = pipeData.daily_flows;
          Plotly.newPlot(cid, [
            { x: df.dates, y: df.incoming, type: "scatter", mode: "lines", name: "Cushing Incoming", line: { color: "#10b981", width: 2 } },
            { x: df.dates, y: df.outgoing, type: "scatter", mode: "lines", name: "Cushing Outgoing", line: { color: "#ef4444", width: 2 } },
            { x: df.dates, y: df.net, type: "bar", name: "Net Flow", marker: { color: df.net.map(v => v >= 0 ? "rgba(16,185,129,0.3)" : "rgba(239,68,68,0.3)") }, yaxis: "y2" },
          ], { ...gsPlotLayout, title: gsTitle("Cushing Hub — Daily Pipeline Flows", "Green bars = implied build, Red bars = implied draw"), height: 380, yaxis: { ...gsPlotLayout.yaxis, title: { text: "Flow (BPD)", font: { size: 11, color: "#94a3b8" } } }, yaxis2: { overlaying: "y", side: "right", gridcolor: "transparent", title: { text: "Net (BPD)", font: { size: 11, color: "#94a3b8" } } }, barmode: "overlay" }, { responsive: true });
        });
      }

      // Pipeline Utilization Table
      if (pipeData.top_pipelines && pipeData.top_pipelines.length > 0) {
        const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px" } });
        const hd = el("thead");
        const hr = el("tr");
        ["Pipeline", "Direction", "Flow (BPD)", "Capacity (BPD)", "Utilization", "Route"].forEach(h =>
          hr.appendChild(el("th", { style: { padding: "8px 6px", textAlign: h === "Pipeline" || h === "Direction" || h === "Route" ? "left" : "right", color: "#94a3b8", borderBottom: "2px solid #334155", fontSize: "10px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "0.05em" } }, h)));
        hd.appendChild(hr); tbl.appendChild(hd);
        const tb = el("tbody");
        pipeData.top_pipelines.forEach((row, i) => {
          const util = row.pipelineCapacity > 0 ? (row.flowBpd / row.pipelineCapacity * 100) : 0;
          const utilStr = util > 0 ? util.toFixed(0) + "%" : "N/A";
          const utilColor = util > 100 ? "#ef4444" : util > 80 ? "#f59e0b" : util > 50 ? "#10b981" : "#64748b";
          const tr = el("tr", { style: { borderBottom: "1px solid #1e293b", background: i % 2 === 0 ? "transparent" : "#0f172a30" } });
          tr.appendChild(el("td", { style: { padding: "6px 6px", color: "#e2e8f0", fontWeight: "600", fontSize: "11px" } }, row.pipelineName));
          tr.appendChild(el("td", { style: { padding: "6px 6px", color: "#94a3b8", fontSize: "10px" } }, row.direction));
          tr.appendChild(el("td", { style: { padding: "6px 6px", textAlign: "right", color: "#f8fafc", fontWeight: "600" } }, Math.round(row.flowBpd).toLocaleString()));
          tr.appendChild(el("td", { style: { padding: "6px 6px", textAlign: "right", color: "#94a3b8" } }, row.pipelineCapacity ? Math.round(row.pipelineCapacity).toLocaleString() : "N/A"));
          // Utilization bar
          const utilCell = el("td", { style: { padding: "6px 6px", textAlign: "right" } });
          const barWrap = el("div", { style: { display: "flex", alignItems: "center", justifyContent: "flex-end", gap: "6px" } });
          const barBg = el("div", { style: { width: "50px", height: "6px", background: "#1e293b", borderRadius: "3px", overflow: "hidden" } });
          barBg.appendChild(el("div", { style: { width: Math.min(util, 120) / 120 * 100 + "%", height: "100%", background: utilColor, borderRadius: "3px" } }));
          barWrap.appendChild(barBg);
          barWrap.appendChild(el("span", { style: { color: utilColor, fontWeight: "700", fontSize: "11px", minWidth: "36px" } }, utilStr));
          utilCell.appendChild(barWrap);
          tr.appendChild(utilCell);
          tr.appendChild(el("td", { style: { padding: "6px 6px", color: "#64748b", fontSize: "10px" } }, `${row.startPumpStation || ""} \u2192 ${row.finishPumpStation || ""}`));
          tb.appendChild(tr);
        });
        tbl.appendChild(tb);
        box.appendChild(gsCard("PIPELINE UTILIZATION — LATEST DAY", tbl));
      }
    }

    loadPlotly(() => requestAnimationFrame(() => deferred.forEach(fn => fn())));
  }

  function renderGspeAnalytics(box, refData, cushData) {
    let gIdx = 100;
    const gId = () => `gspe-an-${gIdx++}`;
    const deferred = [];

    // ===================== SECTION: REFINERY ANALYTICS =====================
    box.appendChild(gsSection("Refinery Turnaround & Outage Analytics", "Real-time tracking of US refinery offline capacity — CDU focus | Data through " + (refData.latest_date || "N/A")));

    // WoW Change Summary
    const wow = refData.wow_changes || {};
    const wowRow = el("div", { style: { display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "14px" } });
    Object.keys(wow).forEach(cat => {
      const w = wow[cat];
      const chg = w.change;
      const color = chg > 0 ? "#ef4444" : chg < 0 ? "#10b981" : "#94a3b8";
      const arrow = chg > 0 ? "\u25B2" : chg < 0 ? "\u25BC" : "\u2014";
      wowRow.appendChild(gsStatCard(cat + " (This Wk)", Math.round(w.this_week).toLocaleString() + " KBD", color,
        `${arrow} ${Math.abs(chg)} vs prev (${Math.round(w.prev_week)})`));
    });
    box.appendChild(gsCard("WEEK-OVER-WEEK OFFLINE CAPACITY CHANGE", wowRow));

    // WoW Bar Chart
    {
      const cid = gId();
      const cDiv = el("div", { id: cid, style: { width: "100%", height: "340px" } });
      box.appendChild(gsCard(null, cDiv));
      deferred.push(() => {
        const cats = Object.keys(wow);
        const changes = cats.map(c => wow[c].change);
        const colors = changes.map(v => v > 0 ? "#ef4444" : v < 0 ? "#10b981" : "#64748b");
        Plotly.newPlot(cid, [{
          x: cats, y: changes, type: "bar", marker: { color: colors, line: { color: colors.map(c => c + "80"), width: 1 } },
          text: changes.map(v => (v > 0 ? "+" : "") + v + " KBD"), textposition: "outside", textfont: { size: 11, color: "#e2e8f0" },
        }], { ...gsPlotLayout, title: gsTitle("Week-over-Week Change in Offline Capacity", "Red = more offline (bearish for supply) | Green = returning online (bullish)"), height: 340, yaxis: { ...gsPlotLayout.yaxis, title: { text: "Change (KBD)", font: { size: 11, color: "#94a3b8" } } }, xaxis: { ...gsPlotLayout.xaxis, tickfont: { size: 12, color: "#e2e8f0" } } }, { responsive: true });
      });
    }

    // Outage Type Breakdown
    {
      const outages = refData.outage_breakdown || [];
      const cid = gId();
      const cDiv = el("div", { id: cid, style: { width: "100%", height: "300px" } });
      const outCard = gsCard(null, cDiv);
      box.appendChild(outCard);
      deferred.push(() => {
        const typeColors = { "Planned Maintenance": "#3b82f6", "Unknown": "#f59e0b", "Unplanned": "#ef4444", "Idled": "#64748b" };
        Plotly.newPlot(cid, [{
          labels: outages.map(o => o.type), values: outages.map(o => o.kbd),
          type: "pie", hole: 0.45, textinfo: "label+value+percent", textposition: "outside",
          textfont: { size: 10, color: "#e2e8f0" },
          marker: { colors: outages.map(o => typeColors[o.type] || "#94a3b8"), line: { color: "#0f172a", width: 2 } },
        }], { ...gsPlotLayout, title: gsTitle("Outage Type Breakdown — Latest Day", "Offline capacity by cause: planned maintenance, unplanned events, idled units"), height: 300, showlegend: false }, { responsive: true });
      });
    }

    // CDU Turnaround Tracker (90-day)
    {
      const tt = refData.turnaround_tracker || {};
      const cid = gId();
      const cDiv = el("div", { id: cid, style: { width: "100%", height: "380px" } });
      box.appendChild(gsCard(null, cDiv));
      deferred.push(() => {
        const last90idx = Math.max(0, tt.dates.length - 90);
        Plotly.newPlot(cid, [
          { x: tt.dates.slice(last90idx), y: tt.offline_kbd.slice(last90idx), type: "scatter", mode: "lines", name: "CDU Offline (KBD)", line: { color: "#ef4444", width: 2.5 }, fill: "tozeroy", fillcolor: "rgba(239,68,68,0.1)" },
          { x: tt.dates.slice(last90idx), y: tt.pct_offline.slice(last90idx), type: "scatter", mode: "lines", name: "% of US CDU Capacity", line: { color: "#f59e0b", width: 2, dash: "dot" }, yaxis: "y2" },
        ], { ...gsPlotLayout, title: gsTitle("CDU Turnaround Tracker — Last 90 Days", `US CDU nameplate capacity: ${Math.round(tt.total_cdu_capacity || 0).toLocaleString()} KBD`), height: 380, yaxis: { ...gsPlotLayout.yaxis, title: { text: "Offline (KBD)", font: { size: 11, color: "#94a3b8" } } }, yaxis2: { overlaying: "y", side: "right", gridcolor: "transparent", title: { text: "% Offline", font: { size: 11, color: "#94a3b8" } }, ticksuffix: "%" } }, { responsive: true });
      });
    }

    // PADD CDU Trends (90-day)
    {
      const pt = refData.padd_trends || {};
      const cid = gId();
      const cDiv = el("div", { id: cid, style: { width: "100%", height: "400px" } });
      box.appendChild(gsCard(null, cDiv));
      deferred.push(() => {
        const traces = Object.keys(pt).sort().map(p => ({
          x: pt[p].dates, y: pt[p].values, type: "scatter", mode: "lines",
          name: p.replace("PADD", "PADD "), line: { color: gsPaddColors[p] || "#94a3b8", width: 2 },
        }));
        Plotly.newPlot(cid, traces, { ...gsPlotLayout, title: gsTitle("CDU Offline by PADD — Last 90 Days", "Regional breakdown showing where turnaround activity is concentrated"), height: 400, yaxis: { ...gsPlotLayout.yaxis, title: { text: "Offline (KBD)", font: { size: 11, color: "#94a3b8" } } } }, { responsive: true });
      });
    }

    // Category 90-day Trends
    {
      const cts = refData.category_timeseries || {};
      const cid = gId();
      const cDiv = el("div", { id: cid, style: { width: "100%", height: "400px" } });
      box.appendChild(gsCard(null, cDiv));
      deferred.push(() => {
        const traces = Object.keys(cts).map(cat => ({
          x: cts[cat].dates, y: cts[cat].values, type: "scatter", mode: "lines",
          name: cat, line: { color: gsCatColors[cat] || "#94a3b8", width: 2 },
        }));
        Plotly.newPlot(cid, traces, { ...gsPlotLayout, title: gsTitle("All Unit Categories — 90-Day Offline Trend", "Compare CDU, FCC, HCU, COK, RFM, VDU offline capacity trends"), height: 400, yaxis: { ...gsPlotLayout.yaxis, title: { text: "Offline (KBD)", font: { size: 11, color: "#94a3b8" } } } }, { responsive: true });
      });
    }

    // Seasonal CDU Overlay (from monthly data)
    {
      const sc = refData.seasonal_cdu || {};
      if (Object.keys(sc).length > 0) {
        const cid = gId();
        const cDiv = el("div", { id: cid, style: { width: "100%", height: "420px" } });
        box.appendChild(gsCard(null, cDiv));
        deferred.push(() => {
          const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
          const traces = [];
          const avg5y = sc["avg_5y"];
          if (avg5y) {
            traces.push({ x: avg5y.months.map(m => months[m-1]).concat(avg5y.months.map(m => months[m-1]).reverse()), y: avg5y.max.concat(avg5y.min.slice().reverse()), type: "scatter", fill: "toself", fillcolor: "rgba(168,162,158,0.1)", line: { color: "transparent" }, name: "2016-20 Range", showlegend: true, hoverinfo: "skip" });
            traces.push({ x: avg5y.months.map(m => months[m-1]), y: avg5y.avg, type: "scatter", mode: "lines", name: "2016-20 Average", line: { color: "#a8a29e", width: 2, dash: "dot" } });
          }
          Object.keys(sc).filter(k => k !== "avg_5y").sort().forEach(yr => {
            const d = sc[yr];
            traces.push({ x: d.months.map(m => months[m-1]), y: d.values, type: "scatter", mode: "lines+markers",
              name: String(yr), line: { color: gsYearColors[yr] || "#94a3b8", width: yr >= 2025 ? 2.5 : 1.5, dash: yr >= 2026 ? "dash" : "solid" },
              marker: { size: yr >= 2025 ? 6 : 3 } });
          });
          Plotly.newPlot(cid, traces, { ...gsPlotLayout, title: gsTitle("CDU Offline — Seasonal Comparison (Monthly)", "Spring turnaround season: Feb-May | Fall: Sep-Nov | Current year vs historical range"), height: 420, yaxis: { ...gsPlotLayout.yaxis, title: { text: "CDU Offline (KBD)", font: { size: 11, color: "#94a3b8" } } } }, { responsive: true });
        });
      }
    }

    // Top Offline Facilities Table
    {
      const facs = refData.top_facilities || [];
      if (facs.length > 0) {
        const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px" } });
        const hd = el("thead");
        const hr = el("tr");
        ["#", "Refinery", "Region", "Offline (KBD)", "Units Down"].forEach(h =>
          hr.appendChild(el("th", { style: { padding: "8px 6px", textAlign: h === "#" || h === "Refinery" || h === "Region" ? "left" : "right", color: "#94a3b8", borderBottom: "2px solid #334155", fontSize: "10px", fontWeight: "700", textTransform: "uppercase" } }, h)));
        hd.appendChild(hr); tbl.appendChild(hd);
        const tb = el("tbody");
        facs.forEach((row, i) => {
          const tr = el("tr", { style: { borderBottom: "1px solid #1e293b", background: i % 2 === 0 ? "transparent" : "#0f172a30" } });
          tr.appendChild(el("td", { style: { padding: "6px 6px", color: "#64748b", fontWeight: "700", fontSize: "10px" } }, String(i + 1)));
          tr.appendChild(el("td", { style: { padding: "6px 6px", color: "#e2e8f0", fontWeight: "600" } }, row.facility));
          tr.appendChild(el("td", { style: { padding: "6px 6px", color: gsPaddColors[row.region] || "#94a3b8", fontWeight: "600", fontSize: "10px" } }, row.region));
          tr.appendChild(el("td", { style: { padding: "6px 6px", textAlign: "right", color: "#ef4444", fontWeight: "700" } }, Math.round(row.offline_kbd).toLocaleString()));
          tr.appendChild(el("td", { style: { padding: "6px 6px", textAlign: "right", color: "#64748b" } }, String(row.units)));
          tb.appendChild(tr);
        });
        tbl.appendChild(tb);
        box.appendChild(gsCard("TOP 20 OFFLINE REFINERIES — LATEST DAY", tbl));
      }
    }

    // ===================== SECTION: CUSHING ANALYTICS =====================
    if (cushData) {
      box.appendChild(gsSection("Cushing Hub — Implied Storage Analytics", "Pipeline flow data used to estimate weekly Cushing stock builds/draws before EIA report | Latest: " + (cushData.latest_date || "N/A")));

      // Summary stats
      const cs = cushData.cushing_summary || {};
      const cushStats = el("div", { style: { display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "14px" } });
      cushStats.appendChild(gsStatCard("Cushing In", Math.round(cs.incoming_bpd || 0).toLocaleString() + " BPD", "#10b981"));
      cushStats.appendChild(gsStatCard("Cushing Out", Math.round(cs.outgoing_bpd || 0).toLocaleString() + " BPD", "#ef4444"));
      const cushNet = cs.net_bpd || 0;
      cushStats.appendChild(gsStatCard("Cushing Net", (cushNet > 0 ? "+" : "") + Math.round(cushNet).toLocaleString() + " BPD", cushNet >= 0 ? "#10b981" : "#ef4444", cushNet >= 0 ? "Implied Build" : "Implied Draw"));
      cushStats.appendChild(gsStatCard("Patoka In", Math.round(cs.patoka_incoming || 0).toLocaleString() + " BPD", "#06b6d4"));
      cushStats.appendChild(gsStatCard("Patoka Out", Math.round(cs.patoka_outgoing || 0).toLocaleString() + " BPD", "#8b5cf6"));
      box.appendChild(cushStats);

      // Cushing Implied Stock Change
      {
        const df = cushData.daily_flows || {};
        if (df.cumulative && df.cumulative.length > 0) {
          const cid = gId();
          const cDiv = el("div", { id: cid, style: { width: "100%", height: "380px" } });
          box.appendChild(gsCard(null, cDiv));
          deferred.push(() => {
            Plotly.newPlot(cid, [
              { x: df.dates, y: df.cumulative.map(v => v / 1e6), type: "scatter", mode: "lines", name: "Cumulative Net Flow", line: { color: "#f59e0b", width: 2.5 }, fill: "tozeroy", fillcolor: "rgba(245,158,11,0.1)" },
            ], { ...gsPlotLayout, title: gsTitle("Cushing Implied Stock Change — Cumulative", "Running total of daily net pipeline flows (incoming minus outgoing) — approximates EIA Cushing stock changes"), height: 380, yaxis: { ...gsPlotLayout.yaxis, title: { text: "Cumulative Net (MMbbl)", font: { size: 11, color: "#94a3b8" } } } }, { responsive: true });
          });
        }
      }

      // Cushing Daily Net Flow Bar Chart
      {
        const df = cushData.daily_flows || {};
        if (df.net && df.net.length > 0) {
          const cid = gId();
          const cDiv = el("div", { id: cid, style: { width: "100%", height: "350px" } });
          box.appendChild(gsCard(null, cDiv));
          deferred.push(() => {
            Plotly.newPlot(cid, [{
              x: df.dates, y: df.net, type: "bar", name: "Net Flow",
              marker: { color: df.net.map(v => v >= 0 ? "rgba(16,185,129,0.6)" : "rgba(239,68,68,0.6)"), line: { color: df.net.map(v => v >= 0 ? "#10b981" : "#ef4444"), width: 0.5 } },
            }], { ...gsPlotLayout, title: gsTitle("Cushing Daily Net Flow", "Green = build (inflow > outflow) | Red = draw (outflow > inflow) — useful for predicting Wednesday EIA reports"), height: 350, yaxis: { ...gsPlotLayout.yaxis, title: { text: "Net Flow (BPD)", font: { size: 11, color: "#94a3b8" } } } }, { responsive: true });
          });
        }
      }

      // Patoka Flows
      {
        const pf = cushData.patoka_flows || {};
        if (pf.dates && pf.dates.length > 0) {
          const cid = gId();
          const cDiv = el("div", { id: cid, style: { width: "100%", height: "350px" } });
          box.appendChild(gsCard(null, cDiv));
          deferred.push(() => {
            Plotly.newPlot(cid, [
              { x: pf.dates, y: pf.incoming, type: "scatter", mode: "lines", name: "Patoka Incoming", line: { color: "#06b6d4", width: 2 } },
              { x: pf.dates, y: pf.outgoing, type: "scatter", mode: "lines", name: "Patoka Outgoing", line: { color: "#8b5cf6", width: 2 } },
              { x: pf.dates, y: pf.net, type: "bar", name: "Patoka Net", marker: { color: pf.net.map(v => v >= 0 ? "rgba(6,182,212,0.3)" : "rgba(139,92,246,0.3)") } },
            ], { ...gsPlotLayout, title: gsTitle("Patoka Hub — Daily Pipeline Flows", "Secondary Mid-Continent hub — receives Canadian crude via Dakota Access & Keystone"), height: 350, yaxis: { ...gsPlotLayout.yaxis, title: { text: "BPD", font: { size: 11, color: "#94a3b8" } } }, barmode: "overlay" }, { responsive: true });
          });
        }
      }

      // Weekly Implied Stock Change Table
      {
        const ws = cushData.weekly_implied_stock || [];
        if (ws.length > 0) {
          const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px" } });
          const hd = el("thead");
          const hr = el("tr");
          ["Week", "Avg Net Flow (BPD)", "Implied \u0394 Stock (MMbbl)", "Days"].forEach(h =>
            hr.appendChild(el("th", { style: { padding: "8px 6px", textAlign: h === "Week" ? "left" : "right", color: "#94a3b8", borderBottom: "2px solid #334155", fontSize: "10px", fontWeight: "700", textTransform: "uppercase" } }, h)));
          hd.appendChild(hr); tbl.appendChild(hd);
          const tb = el("tbody");
          ws.slice(-12).forEach((row, i) => {
            const tr = el("tr", { style: { borderBottom: "1px solid #1e293b", background: i % 2 === 0 ? "transparent" : "#0f172a30" } });
            tr.appendChild(el("td", { style: { padding: "6px 6px", color: "#e2e8f0", fontWeight: "600", fontSize: "10px" } }, `${row.week_start} to ${row.week_end}`));
            const netColor = row.avg_net_bpd >= 0 ? "#10b981" : "#ef4444";
            tr.appendChild(el("td", { style: { padding: "6px 6px", textAlign: "right", color: netColor, fontWeight: "700" } }, (row.avg_net_bpd >= 0 ? "+" : "") + Math.round(row.avg_net_bpd).toLocaleString()));
            const chgColor = row.implied_change_mmbbl >= 0 ? "#10b981" : "#ef4444";
            tr.appendChild(el("td", { style: { padding: "6px 6px", textAlign: "right", color: chgColor, fontWeight: "700" } }, (row.implied_change_mmbbl >= 0 ? "+" : "") + row.implied_change_mmbbl.toFixed(2)));
            tr.appendChild(el("td", { style: { padding: "6px 6px", textAlign: "right", color: "#64748b" } }, String(row.days)));
            tb.appendChild(tr);
          });
          tbl.appendChild(tb);
          box.appendChild(gsCard("WEEKLY IMPLIED CUSHING STOCK CHANGE", tbl));
        }
      }

      // Pipeline Utilization Table
      {
        const pipes = cushData.pipeline_utilization || [];
        if (pipes.length > 0) {
          const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px" } });
          const hd = el("thead");
          const hr = el("tr");
          ["Pipeline", "Direction", "Flow (BPD)", "Capacity (BPD)", "Utilization", "Route"].forEach(h =>
            hr.appendChild(el("th", { style: { padding: "8px 6px", textAlign: h === "Pipeline" || h === "Direction" || h === "Route" ? "left" : "right", color: "#94a3b8", borderBottom: "2px solid #334155", fontSize: "10px", fontWeight: "700", textTransform: "uppercase" } }, h)));
          hd.appendChild(hr); tbl.appendChild(hd);
          const tb = el("tbody");
          pipes.forEach((row, i) => {
            const util = row.utilization || 0;
            const utilColor = util > 100 ? "#ef4444" : util > 80 ? "#f59e0b" : util > 50 ? "#10b981" : "#64748b";
            const tr = el("tr", { style: { borderBottom: "1px solid #1e293b", background: i % 2 === 0 ? "transparent" : "#0f172a30" } });
            tr.appendChild(el("td", { style: { padding: "6px 6px", color: "#e2e8f0", fontWeight: "600", fontSize: "11px" } }, row.pipelineName));
            tr.appendChild(el("td", { style: { padding: "6px 6px", color: "#94a3b8", fontSize: "10px" } }, row.direction));
            tr.appendChild(el("td", { style: { padding: "6px 6px", textAlign: "right", color: "#f8fafc", fontWeight: "600" } }, Math.round(row.flowBpd).toLocaleString()));
            tr.appendChild(el("td", { style: { padding: "6px 6px", textAlign: "right", color: "#94a3b8" } }, row.pipelineCapacity ? Math.round(row.pipelineCapacity).toLocaleString() : "N/A"));
            const utilCell = el("td", { style: { padding: "6px 6px", textAlign: "right" } });
            const barWrap = el("div", { style: { display: "flex", alignItems: "center", justifyContent: "flex-end", gap: "6px" } });
            const barBg = el("div", { style: { width: "50px", height: "6px", background: "#1e293b", borderRadius: "3px", overflow: "hidden" } });
            barBg.appendChild(el("div", { style: { width: Math.min(util, 120) / 120 * 100 + "%", height: "100%", background: utilColor, borderRadius: "3px" } }));
            barWrap.appendChild(barBg);
            barWrap.appendChild(el("span", { style: { color: utilColor, fontWeight: "700", fontSize: "11px", minWidth: "36px" } }, util > 0 ? util.toFixed(0) + "%" : "N/A"));
            utilCell.appendChild(barWrap);
            tr.appendChild(utilCell);
            tr.appendChild(el("td", { style: { padding: "6px 6px", color: "#64748b", fontSize: "10px" } }, `${row.startPumpStation || ""} \u2192 ${row.finishPumpStation || ""}`));
            tb.appendChild(tr);
          });
          tbl.appendChild(tb);
          box.appendChild(gsCard("ALL PIPELINES — FLOW & UTILIZATION (LATEST DAY)", tbl));
        }
      }
    }

    loadPlotly(() => requestAnimationFrame(() => deferred.forEach(fn => fn())));
  }

  async function renderGenscape(box) {
    box.innerHTML = "";

    // Controls bar
    const controls = el("div", { style: { display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px", flexWrap: "wrap", background: "#0f172a", borderRadius: "10px", border: "1px solid #1e293b", padding: "12px 16px" } });
    const ctrlLabel = (t) => el("span", { style: { fontSize: "11px", color: "#94a3b8", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.05em" } }, t);
    const ctrlSelect = (opts, current, onChange) => {
      const s = el("select", { style: { background: "#1e293b", color: "#f1f5f9", border: "1px solid #334155", borderRadius: "6px", padding: "8px 12px", fontSize: "12px", fontWeight: "500" } });
      opts.forEach(o => { const opt = el("option", { value: o }, o); if (o === current) opt.selected = true; s.appendChild(opt); });
      s.onchange = () => onChange(s.value);
      return s;
    };

    controls.appendChild(ctrlLabel("Region"));
    controls.appendChild(ctrlSelect(["All", "US Total", "PADD1", "PADD2", "PADD3", "PADD4", "PADD5", "Canada", "Europe", "United Kingdom"], gspeRegion, v => { gspeRegion = v; }));
    controls.appendChild(ctrlLabel("Unit Type"));
    controls.appendChild(ctrlSelect(["All", "CDU", "FCC", "VDU", "HCU", "COK", "HT", "RFM", "ALK", "ISO", "CBU", "VBU", "ARO", "ASP", "GAS", "HGP", "POW", "SUL"], gspeCategory, v => { gspeCategory = v; }));
    controls.appendChild(ctrlLabel("From"));
    controls.appendChild(ctrlSelect(Array.from({length: 12}, (_, i) => String(2015 + i)), String(gspeStartYear), v => { gspeStartYear = parseInt(v); }));
    controls.appendChild(ctrlLabel("To"));
    controls.appendChild(ctrlSelect(Array.from({length: 12}, (_, i) => String(2015 + i)), String(gspeEndYear), v => { gspeEndYear = parseInt(v); }));

    const contentBox = el("div");
    const analyticsBox = el("div");

    const loadBtn = el("button", { style: { background: "linear-gradient(135deg, #f59e0b, #d97706)", color: "#000", border: "none", borderRadius: "8px", padding: "10px 24px", fontSize: "12px", fontWeight: "800", cursor: "pointer", letterSpacing: "0.03em", textTransform: "uppercase" }, onClick: async () => {
      loadBtn.textContent = "LOADING..."; loadBtn.disabled = true;
      try {
        const [mainData, facData, refData] = await Promise.all([
          fetchGspeData(gspeRegion, gspeCategory, gspeStartYear, gspeEndYear),
          fetchGspeFacilities(gspeRegion, gspeCategory),
          fetchGspeRefAnalytics(),
        ]);
        let pipeData = null;
        try { pipeData = await fetchGspePipeline(); } catch(e) {}
        let cushData = null;
        try { cushData = await fetchGspeCushingAnalytics(); } catch(e) {}
        try { renderGspeContent(contentBox, mainData, facData, pipeData); } catch(e1) { contentBox.innerHTML = `<div style="color:#ef4444;padding:20px;font-size:12px;">Content error: ${e1.message}</div>`; }
        analyticsBox.innerHTML = "";
        try { renderGspeAnalytics(analyticsBox, refData, cushData); } catch(e2) { analyticsBox.innerHTML += `<div style="color:#ef4444;padding:20px;font-size:12px;">Analytics error: ${e2.message}</div>`; }
      } catch (e) { contentBox.innerHTML = `<div style="color:#ef4444;padding:20px;font-size:12px;">Error: ${e.message}</div>`; }
      loadBtn.textContent = "LOAD DATA"; loadBtn.disabled = false;
      // Update last pulled timestamp
      try { const lp = await fetchGspeLastPulled(); if (lp) lastPulledLabel.textContent = "Last pulled: " + new Date(lp).toLocaleString(); } catch(e) {}
    } }, "LOAD DATA");
    controls.appendChild(loadBtn);

    // Refresh button — pulls 3 days from max date, dedup keep=first
    const refreshBtn = el("button", { style: { background: "linear-gradient(135deg, #22c55e, #16a34a)", color: "#fff", border: "none", borderRadius: "8px", padding: "10px 18px", fontSize: "11px", fontWeight: "700", cursor: "pointer", letterSpacing: "0.03em", textTransform: "uppercase" }, onClick: async () => {
      refreshBtn.textContent = "REFRESHING..."; refreshBtn.disabled = true;
      try {
        const res = await refreshGspeData(3);
        lastPulledLabel.textContent = "Last pulled: " + new Date(res.last_pulled).toLocaleString() + ` (${res.new_records} new records, dedup: keep=first)`;
        // Reload the tab data automatically
        loadBtn.click();
      } catch(e) { alert("Refresh error: " + e.message); }
      refreshBtn.textContent = "↻ REFRESH (3d)"; refreshBtn.disabled = false;
    } }, "↻ REFRESH (3d)");
    controls.appendChild(refreshBtn);

    // Last Pulled timestamp label
    const lastPulledLabel = el("span", { style: { fontSize: "10px", color: "#64748b", marginLeft: "auto", textAlign: "right" } }, "Last pulled: loading...");
    controls.appendChild(lastPulledLabel);

    // Trader Briefing section
    const briefingBox = el("div", { style: { marginBottom: "20px" } });

    box.appendChild(controls);
    box.appendChild(briefingBox);
    box.appendChild(contentBox);
    box.appendChild(analyticsBox);

    // Fetch and render trader briefing
    async function loadGspeBriefing() {
      try {
        const res = await fetch("/api/genscape/briefing");
        if (!res.ok) return;
        const data = await res.json();
        briefingBox.innerHTML = "";
        const panel = el("div", { style: { background: "linear-gradient(135deg, #0f172a 0%, #1a1f3a 100%)", border: "1px solid #f59e0b33", borderRadius: "12px", padding: "20px 24px", marginBottom: "8px" } });
        const hdr = el("div", { style: { display: "flex", alignItems: "center", gap: "10px", marginBottom: "14px" } });
        hdr.appendChild(el("span", { style: { fontSize: "15px", fontWeight: "800", color: "#f59e0b", letterSpacing: "0.02em" } }, "📋 TRADER BRIEFING"));
        if (data.date) hdr.appendChild(el("span", { style: { fontSize: "11px", color: "#64748b", marginLeft: "auto" } }, "Data as of " + data.date));
        panel.appendChild(hdr);

        // Summary badges
        if (data.total_offline_kbd !== undefined) {
          const badges = el("div", { style: { display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "14px" } });
          const badge = (label, val, color) => {
            const b = el("div", { style: { background: color + "18", border: "1px solid " + color + "44", borderRadius: "8px", padding: "8px 14px", display: "flex", flexDirection: "column", alignItems: "center" } });
            b.appendChild(el("span", { style: { fontSize: "16px", fontWeight: "800", color: color } }, val));
            b.appendChild(el("span", { style: { fontSize: "9px", color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", marginTop: "2px" } }, label));
            return b;
          };
          badges.appendChild(badge("Total Offline", data.total_offline_kbd.toLocaleString() + " kb/d", "#ef4444"));
          const wowColor = data.wow_change_kbd > 0 ? "#ef4444" : "#22c55e";
          const wowSign = data.wow_change_kbd > 0 ? "+" : "";
          badges.appendChild(badge("W/W Change", wowSign + data.wow_change_kbd.toLocaleString() + " kb/d", wowColor));
          panel.appendChild(badges);
        }

        // Bullet points
        const list = el("div", { style: { display: "flex", flexDirection: "column", gap: "6px" } });
        (data.bullets || []).forEach(b => {
          const isIndent = b.startsWith("  •");
          const item = el("div", { style: { fontSize: "12px", color: isIndent ? "#cbd5e1" : "#e2e8f0", paddingLeft: isIndent ? "16px" : "0", lineHeight: "1.5", fontWeight: isIndent ? "400" : "500" } });
          if (!isIndent) {
            item.innerHTML = "• " + b.replace(/▲/g, '<span style="color:#ef4444">▲</span>').replace(/▼/g, '<span style="color:#22c55e">▼</span>');
          } else {
            item.textContent = b;
          }
          list.appendChild(item);
        });
        panel.appendChild(list);

        // EU/UK bullets
        if (data.eu_bullets && data.eu_bullets.length > 0) {
          const euHdr = el("div", { style: { fontSize: "13px", fontWeight: "700", color: "#60a5fa", marginTop: "14px", marginBottom: "8px", borderTop: "1px solid #1e293b", paddingTop: "10px" } }, "🇪🇺 Europe / UK Update");
          panel.appendChild(euHdr);
          const euList = el("div", { style: { display: "flex", flexDirection: "column", gap: "5px" } });
          data.eu_bullets.forEach(b => {
            euList.appendChild(el("div", { style: { fontSize: "12px", color: "#e2e8f0", lineHeight: "1.5" } }, "• " + b));
          });
          panel.appendChild(euList);
        }

        briefingBox.appendChild(panel);
      } catch(e) { /* briefing is optional */ }
    }

    // Fetch and show last pulled timestamp, then auto-load
    fetchGspeLastPulled().then(lp => {
      if (lp) lastPulledLabel.textContent = "Last pulled: " + new Date(lp).toLocaleString();
      else lastPulledLabel.textContent = "Source: Genscape / Wood Mackenzie";
    });
    loadGspeBriefing();
    loadBtn.click();
  }

  // ========== OVERLAY DASHBOARD ==========
  // =====================================================================
  // IRR (Industrial Info Resources) Tab
  // =====================================================================
  async function renderIIR(box) {
    box.innerHTML = "";
    const C2 = C;
    const sectionTitle = (t) => el("div", { style: { fontSize: "16px", fontWeight: "700", color: C2.amber, margin: "24px 0 12px 0", borderBottom: "1px solid " + C2.border, paddingBottom: "8px" } }, t);
    const kbdFmt = (v) => v >= 1000 ? (v / 1000).toFixed(1) + " kbd" : v.toFixed(0) + " bpd";

    // Controls bar
    const controls = el("div", { style: { display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px", flexWrap: "wrap", background: "#0f172a", borderRadius: "10px", border: "1px solid #1e293b", padding: "12px 16px" } });
    const ctrlLabel = (t) => el("span", { style: { fontSize: "11px", color: "#94a3b8", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.05em" } }, t);

    controls.appendChild(ctrlLabel("Country"));
    const countrySelect = el("select", { style: { background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", borderRadius: "6px", padding: "6px 10px", fontSize: "12px" } });
    ["U.S.A.", "Canada", "India", "China", "Japan", "Republic of Korea - South Korea", ""].forEach(c => {
      const opt = el("option", { value: c }, c || "All Countries");
      countrySelect.appendChild(opt);
    });
    controls.appendChild(countrySelect);

    const loadBtn = el("button", { style: { background: "linear-gradient(135deg, #f59e0b, #d97706)", color: "#000", border: "none", borderRadius: "8px", padding: "8px 20px", fontWeight: "700", fontSize: "12px", cursor: "pointer" } }, "LOAD DATA");
    controls.appendChild(loadBtn);

    const refreshBtn = el("button", { style: { background: "linear-gradient(135deg, #22c55e, #16a34a)", color: "#fff", border: "none", borderRadius: "8px", padding: "8px 20px", fontWeight: "700", fontSize: "12px", cursor: "pointer" } }, "↻ REFRESH");
    controls.appendChild(refreshBtn);

    const statusLabel = el("span", { style: { fontSize: "10px", color: "#64748b", marginLeft: "auto" } }, "");
    controls.appendChild(statusLabel);
    box.appendChild(controls);

    // IIR Trader Briefing
    const iirBriefingBox = el("div", { style: { marginBottom: "20px" } });
    box.appendChild(iirBriefingBox);

    const contentArea = el("div", {});
    box.appendChild(contentArea);

    async function loadIIRBriefing(country) {
      try {
        const res = await fetch(`/api/iir/briefing?country=${encodeURIComponent(country)}`);
        if (!res.ok) return;
        const data = await res.json();
        iirBriefingBox.innerHTML = "";
        const panel = el("div", { style: { background: "linear-gradient(135deg, #0f172a 0%, #1a1f3a 100%)", border: "1px solid #f59e0b33", borderRadius: "12px", padding: "20px 24px", marginBottom: "8px" } });
        const hdr = el("div", { style: { display: "flex", alignItems: "center", gap: "10px", marginBottom: "14px" } });
        hdr.appendChild(el("span", { style: { fontSize: "15px", fontWeight: "800", color: "#f59e0b", letterSpacing: "0.02em" } }, "📋 TRADER BRIEFING — IIR Turnarounds"));
        hdr.appendChild(el("span", { style: { fontSize: "11px", color: "#64748b", marginLeft: "auto" } }, data.country || ""));
        panel.appendChild(hdr);

        // Summary badges
        const badges = el("div", { style: { display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "14px" } });
        const badge = (label, val, color) => {
          const b = el("div", { style: { background: color + "18", border: "1px solid " + color + "44", borderRadius: "8px", padding: "8px 14px", display: "flex", flexDirection: "column", alignItems: "center" } });
          b.appendChild(el("span", { style: { fontSize: "16px", fontWeight: "800", color: color } }, val));
          b.appendChild(el("span", { style: { fontSize: "9px", color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", marginTop: "2px" } }, label));
          return b;
        };
        badges.appendChild(badge("Ongoing Events", String(data.total_ongoing || 0), "#ef4444"));
        badges.appendChild(badge("Total Offline", (data.total_offline_capacity || 0).toLocaleString() + " b/d", "#f59e0b"));
        panel.appendChild(badges);

        // Bullet points
        const list = el("div", { style: { display: "flex", flexDirection: "column", gap: "5px" } });
        (data.bullets || []).forEach(b => {
          const isIndent = b.startsWith("  •");
          const isSub = b.startsWith("  •");
          const item = el("div", { style: { fontSize: "12px", color: isSub ? "#cbd5e1" : "#e2e8f0", paddingLeft: isSub ? "16px" : "0", lineHeight: "1.5", fontWeight: isSub ? "400" : "500" } });
          if (!isSub && !b.startsWith("Largest ongoing")) {
            item.innerHTML = "• " + b.replace(/NEW:/g, '<span style="color:#ef4444;font-weight:700">NEW:</span>').replace(/RETURNING:/g, '<span style="color:#22c55e;font-weight:700">RETURNING:</span>');
          } else if (b.startsWith("Largest ongoing")) {
            item.innerHTML = "<strong style='color:#f59e0b'>• " + b + "</strong>";
          } else {
            item.textContent = b;
          }
          list.appendChild(item);
        });
        panel.appendChild(list);
        iirBriefingBox.appendChild(panel);
      } catch(e) { /* briefing is optional */ }
    }

    async function loadData() {
      const country = countrySelect.value;
      contentArea.innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8;">Loading IIR data...</div>';
      statusLabel.textContent = "Fetching...";

      try {
        const [resp] = await Promise.all([
          fetch(`/api/iir/dashboard?country=${encodeURIComponent(country)}`),
          loadIIRBriefing(country),
        ]);
        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();
        statusLabel.textContent = `Loaded: ${data.ongoing.count} ongoing, ${data.future.count} future, ${data.past.count} recent past`;
        renderIIRContent(contentArea, data, country);
      } catch(e) {
        contentArea.innerHTML = '<div style="color:#ef4444;padding:20px;">Error: ' + e.message + '</div>';
        statusLabel.textContent = "Error";
      }
    }

    loadBtn.onclick = loadData;
    refreshBtn.onclick = loadData;

    function renderIIRContent(container, data, country) {
      container.innerHTML = "";
      const countryLabel = country || "Global";

      // Summary cards
      const cardRow = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "12px", marginBottom: "20px" } });

      const ongoingCap = data.ongoing.events.reduce((s, e) => s + (e.offlineCapacity?.capacityOffline || 0), 0);
      const futureCap = data.future.events.reduce((s, e) => s + (e.offlineCapacity?.capacityOffline || 0), 0);
      const pastCap = data.past.events.reduce((s, e) => s + (e.offlineCapacity?.capacityOffline || 0), 0);

      function makeCard(title, count, cap, color) {
        const c = el("div", { style: { background: "#0f172a", borderRadius: "10px", border: "1px solid #1e293b", padding: "16px", textAlign: "center" } });
        c.appendChild(el("div", { style: { fontSize: "11px", color: "#94a3b8", textTransform: "uppercase", fontWeight: "600", marginBottom: "8px" } }, title));
        c.appendChild(el("div", { style: { fontSize: "28px", fontWeight: "800", color: color } }, String(count)));
        c.appendChild(el("div", { style: { fontSize: "12px", color: "#64748b", marginTop: "4px" } }, kbdFmt(cap) + " offline"));
        return c;
      }

      cardRow.appendChild(makeCard("Ongoing Turnarounds", data.ongoing.count, ongoingCap, "#ef4444"));
      cardRow.appendChild(makeCard("Future Planned", data.future.count, futureCap, "#f59e0b"));
      cardRow.appendChild(makeCard("Completed (6mo)", data.past.count, pastCap, "#22c55e"));
      cardRow.appendChild(makeCard("Total Events", data.ongoing.count + data.future.count + data.past.count, ongoingCap + futureCap, "#60a5fa"));
      container.appendChild(cardRow);

      // ===== SEASONAL OFFLINE CAPACITY CHART =====
      container.appendChild(sectionTitle("📊 Seasonal Total Offline Capacity — Year-over-Year Comparison"));
      const seasonalDiv = el("div", { id: "iir-seasonal-chart", style: { width: "100%", height: "500px", marginBottom: "24px", background: "#0f172a", borderRadius: "10px", border: "1px solid #1e293b", display: "flex", alignItems: "center", justifyContent: "center", color: "#94a3b8", fontSize: "12px" } }, "Loading seasonal data...");
      container.appendChild(seasonalDiv);

      // Fetch seasonal data async
      (async () => {
        try {
          const sRes = await fetch(`/api/iir/seasonal?country=${encodeURIComponent(country)}`);
          if (!sRes.ok) throw new Error("Failed to load seasonal data");
          const sData = await sRes.json();
          const seasonal = sData.seasonal || {};
          const years = Object.keys(seasonal).map(Number).sort();
          if (years.length === 0) { seasonalDiv.textContent = "No seasonal data available"; return; }
          const weekLabels = Array.from({length: 52}, (_, i) => {
            const d = new Date(2026, 0, 1 + i * 7);
            return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
          });
          const yearColors = { 2023: "#64748b", 2024: "#a78bfa", 2025: "#60a5fa", 2026: "#f59e0b" };
          const traces = years.map(yr => {
            const s = seasonal[yr];
            const xVals = (s.weeks || []).map(w => weekLabels[w - 1] || `W${w}`);
            return {
              x: xVals,
              y: s.values || [],
              name: String(yr),
              type: "scatter",
              mode: "lines",
              line: { width: yr === years[years.length - 1] ? 3 : 1.5, color: yearColors[yr] || "#94a3b8", dash: yr === years[years.length - 1] ? "solid" : "dot" },
              hovertemplate: `%{x}<br>${yr}: %{y:,.0f} b/d<extra></extra>`,
            };
          });
          seasonalDiv.innerHTML = "";
          seasonalDiv.style.display = "block";
          Plotly.newPlot(seasonalDiv, traces, {
            title: { text: `Total Offline Capacity — ${country || "Global"} (Weekly)`, font: { color: "#f59e0b", size: 14 } },
            xaxis: { title: "", tickfont: { color: "#94a3b8", size: 10 }, gridcolor: "#1e293b", showgrid: false },
            yaxis: { title: "Offline Capacity (b/d)", tickfont: { color: "#94a3b8", size: 10 }, gridcolor: "#1e293b", tickformat: ",.0f" },
            paper_bgcolor: "#0f172a", plot_bgcolor: "#0f172a",
            legend: { orientation: "h", y: -0.15, font: { color: "#e2e8f0", size: 11 } },
            margin: { l: 70, r: 30, t: 50, b: 60 },
            hovermode: "x unified",
          }, { responsive: true });
        } catch(e) { seasonalDiv.textContent = "Could not load seasonal chart: " + e.message; }
      })();

      // ===== ONGOING TURNAROUNDS TABLE =====
      if (data.ongoing.events.length > 0) {
        container.appendChild(sectionTitle(`🔴 Ongoing Turnarounds — ${countryLabel} (${data.ongoing.count} events)`));

        // Aggregate by plant
        const plantMap = {};
        data.ongoing.events.forEach(e => {
          const pn = e.plantName || "Unknown";
          if (!plantMap[pn]) plantMap[pn] = { state: e.plantPhysicalAddress?.stateName || "", region: e.tradingRegionName || "", units: [], totalOffline: 0 };
          const cap = e.offlineCapacity?.capacityOffline || 0;
          plantMap[pn].units.push({
            name: e.unitName || "", type: e.unitTypeDesc || "", cap: cap,
            start: (e.associatedEntityStartDate || "").slice(0, 10),
            end: (e.associatedEntityEndDate || "").slice(0, 10),
            eventType: e.eventType || "", confirmation: e.eventConfirmationStatus || "",
            duration: e.eventDuration || 0, comments: e.eventComments || ""
          });
          plantMap[pn].totalOffline += cap;
        });
        const plantList = Object.entries(plantMap).sort((a, b) => b[1].totalOffline - a[1].totalOffline);

        const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px", marginBottom: "16px" } });
        const hdr = el("tr", {});
        ["Refinery", "State", "Unit", "Unit Type", "Capacity", "Offline", "Start", "End", "Days", "Type", "Status", "Notes"].forEach(h => {
          const th = el("th", { style: { padding: "8px 6px", background: "#1e293b", color: "#94a3b8", textAlign: "left", borderBottom: "2px solid #334155", fontWeight: "700", whiteSpace: "nowrap" } }, h);
          hdr.appendChild(th);
        });
        tbl.appendChild(hdr);

        plantList.forEach(([pn, info]) => {
          info.units.sort((a, b) => b.cap - a.cap);
          info.units.forEach((u, idx) => {
            const tr = el("tr", { style: { borderBottom: "1px solid #1e293b" } });
            const cell = (v, opts) => { const td = el("td", { style: { padding: "6px 6px", color: "#e2e8f0", ...opts } }, v); tr.appendChild(td); };
            cell(idx === 0 ? pn : "", { fontWeight: idx === 0 ? "700" : "400", color: idx === 0 ? "#f59e0b" : "transparent" });
            cell(idx === 0 ? info.state : "");
            cell(u.name, { color: "#e2e8f0" });
            cell(u.type, { color: "#94a3b8", fontSize: "10px" });
            cell(u.cap > 0 ? (u.cap / 1000).toFixed(1) + " kbd" : "-", { textAlign: "right", color: "#60a5fa" });
            cell(u.cap > 0 ? (u.cap / 1000).toFixed(1) + " kbd" : "-", { textAlign: "right", color: "#ef4444", fontWeight: "700" });
            cell(u.start);
            cell(u.end);
            cell(String(u.duration));
            cell(u.eventType, { color: u.eventType === "Unplanned" ? "#ef4444" : "#22c55e" });
            cell(u.confirmation, { color: u.confirmation === "Confirmed" ? "#22c55e" : "#f59e0b", fontSize: "10px" });
            cell(u.comments ? u.comments.slice(0, 60) + (u.comments.length > 60 ? "..." : "") : "", { color: "#64748b", fontSize: "10px", maxWidth: "200px" });
            tbl.appendChild(tr);
          });
        });
        container.appendChild(tbl);
      }

      // ===== OFFLINE BY UNIT TYPE (ONGOING) =====
      if (Object.keys(data.byUnitType).length > 0) {
        container.appendChild(sectionTitle(`⚙️ Ongoing Offline by Unit Type — ${countryLabel}`));
        const chartDiv1 = el("div", { id: "iir-unittype-chart", style: { width: "100%", height: "450px", marginBottom: "20px" } });
        container.appendChild(chartDiv1);

        const utEntries = Object.entries(data.byUnitType).filter(([k, v]) => v.ongoing > 0).sort((a, b) => b[1].ongoing - a[1].ongoing);
        if (utEntries.length > 0) {
          loadPlotly(() => {
            Plotly.newPlot("iir-unittype-chart", [{
              x: utEntries.map(([k]) => k),
              y: utEntries.map(([, v]) => v.ongoing / 1000),
              type: "bar",
              marker: { color: utEntries.map((_, i) => ["#ef4444", "#f59e0b", "#22c55e", "#60a5fa", "#a78bfa", "#ec4899", "#14b8a6", "#f97316"][i % 8]) },
              text: utEntries.map(([, v]) => (v.ongoing / 1000).toFixed(1) + " kbd"),
              textposition: "outside",
              hovertemplate: "%{x}<br>%{y:.1f} kbd offline<extra></extra>"
            }], {
              title: { text: "Current Offline Capacity by Unit Type (kbd)", font: { color: "#f59e0b", size: 14 } },
              paper_bgcolor: "#0f172a", plot_bgcolor: "#0f172a",
              xaxis: { color: "#94a3b8", tickangle: -35, tickfont: { size: 10 } },
              yaxis: { color: "#94a3b8", title: { text: "Offline Capacity (kbd)", font: { size: 11 } }, gridcolor: "#1e293b" },
              margin: { t: 50, b: 120, l: 60, r: 20 }
            }, { responsive: true });
          });
        }
      }

      // ===== OFFLINE BY STATE (ONGOING) =====
      if (Object.keys(data.byState).length > 0) {
        container.appendChild(sectionTitle(`📍 Ongoing Offline by State — ${countryLabel}`));
        const chartDiv2 = el("div", { id: "iir-state-chart", style: { width: "100%", height: "450px", marginBottom: "20px" } });
        container.appendChild(chartDiv2);

        const stEntries = Object.entries(data.byState).filter(([k, v]) => v.ongoing > 0 && k).sort((a, b) => b[1].ongoing - a[1].ongoing);
        if (stEntries.length > 0) {
          loadPlotly(() => {
            Plotly.newPlot("iir-state-chart", [{
              x: stEntries.map(([k]) => k),
              y: stEntries.map(([, v]) => v.ongoing / 1000),
              type: "bar",
              marker: { color: "#60a5fa" },
              text: stEntries.map(([, v]) => (v.ongoing / 1000).toFixed(1) + " kbd"),
              textposition: "outside",
              hovertemplate: "%{x}<br>%{y:.1f} kbd offline<extra></extra>"
            }], {
              title: { text: "Current Offline Capacity by State/Province (kbd)", font: { color: "#f59e0b", size: 14 } },
              paper_bgcolor: "#0f172a", plot_bgcolor: "#0f172a",
              xaxis: { color: "#94a3b8", tickangle: -35, tickfont: { size: 10 } },
              yaxis: { color: "#94a3b8", title: { text: "Offline Capacity (kbd)", font: { size: 11 } }, gridcolor: "#1e293b" },
              margin: { t: 50, b: 100, l: 60, r: 20 }
            }, { responsive: true });
          });
        }
      }

      // ===== FUTURE TURNAROUNDS =====
      if (data.future.events.length > 0) {
        container.appendChild(sectionTitle(`📅 Upcoming Planned Turnarounds — ${countryLabel} (${data.future.count} events)`));

        // Group by month
        const byMonth = {};
        data.future.events.forEach(e => {
          const sd = (e.associatedEntityStartDate || "").slice(0, 7);
          if (!sd) return;
          if (!byMonth[sd]) byMonth[sd] = { events: [], totalCap: 0, plants: new Set() };
          const cap = e.offlineCapacity?.capacityOffline || 0;
          byMonth[sd].events.push(e);
          byMonth[sd].totalCap += cap;
          byMonth[sd].plants.add(e.plantName || "");
        });
        const sortedMonths = Object.entries(byMonth).sort((a, b) => a[0].localeCompare(b[0]));

        // Monthly bar chart
        const chartDiv3 = el("div", { id: "iir-future-chart", style: { width: "100%", height: "450px", marginBottom: "20px" } });
        container.appendChild(chartDiv3);

        if (sortedMonths.length > 0) {
          loadPlotly(() => {
            Plotly.newPlot("iir-future-chart", [{
              x: sortedMonths.map(([m]) => m),
              y: sortedMonths.map(([, d]) => d.totalCap / 1000),
              type: "bar",
              marker: { color: sortedMonths.map(([m]) => m.slice(0, 7) <= new Date().toISOString().slice(0, 7) ? "#ef4444" : "#f59e0b") },
              text: sortedMonths.map(([, d]) => (d.totalCap / 1000).toFixed(0) + " kbd"),
              textposition: "outside",
              hovertemplate: "%{x}<br>%{y:.0f} kbd planned offline<br>%{customdata} events<extra></extra>",
              customdata: sortedMonths.map(([, d]) => d.events.length)
            }], {
              title: { text: "Planned Turnaround Offline Capacity by Month (kbd)", font: { color: "#f59e0b", size: 14 } },
              paper_bgcolor: "#0f172a", plot_bgcolor: "#0f172a",
              xaxis: { color: "#94a3b8", tickangle: -45, tickfont: { size: 10 } },
              yaxis: { color: "#94a3b8", title: { text: "Planned Offline (kbd)", font: { size: 11 } }, gridcolor: "#1e293b" },
              margin: { t: 50, b: 80, l: 60, r: 20 }
            }, { responsive: true });
          });
        }

        // Future turnarounds table (top 50 by capacity)
        const futureEvents = [...data.future.events].sort((a, b) => (b.offlineCapacity?.capacityOffline || 0) - (a.offlineCapacity?.capacityOffline || 0)).slice(0, 50);
        const ftbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px", marginBottom: "16px" } });
        const fhdr = el("tr", {});
        ["Refinery", "State", "Unit", "Unit Type", "Offline (kbd)", "Start", "End", "Days", "Type", "Status"].forEach(h => {
          const th = el("th", { style: { padding: "8px 6px", background: "#1e293b", color: "#94a3b8", textAlign: "left", borderBottom: "2px solid #334155", fontWeight: "700", whiteSpace: "nowrap" } }, h);
          fhdr.appendChild(th);
        });
        ftbl.appendChild(fhdr);

        futureEvents.forEach(e => {
          const cap = e.offlineCapacity?.capacityOffline || 0;
          const tr = el("tr", { style: { borderBottom: "1px solid #1e293b" } });
          const cell = (v, opts) => { const td = el("td", { style: { padding: "6px 6px", color: "#e2e8f0", ...opts } }, v); tr.appendChild(td); };
          cell(e.plantName || "", { fontWeight: "700", color: "#f59e0b" });
          cell(e.plantPhysicalAddress?.stateName || "");
          cell(e.unitName || "");
          cell(e.unitTypeDesc || "", { color: "#94a3b8", fontSize: "10px" });
          cell(cap > 0 ? (cap / 1000).toFixed(1) : "-", { textAlign: "right", color: "#ef4444", fontWeight: "700" });
          cell((e.associatedEntityStartDate || "").slice(0, 10));
          cell((e.associatedEntityEndDate || "").slice(0, 10));
          cell(String(e.eventDuration || 0));
          cell(e.eventType || "", { color: e.eventType === "Unplanned" ? "#ef4444" : "#22c55e" });
          cell(e.eventConfirmationStatus || "", { color: e.eventConfirmationStatus === "Confirmed" ? "#22c55e" : "#f59e0b", fontSize: "10px" });
          ftbl.appendChild(tr);
        });
        container.appendChild(ftbl);
      }

      // ===== RECENT PAST =====
      if (data.past.events.length > 0) {
        container.appendChild(sectionTitle(`✅ Recently Completed Turnarounds — ${countryLabel} (last 6 months, ${data.past.count} events)`));

        // Top 30 by capacity
        const pastEvents = [...data.past.events].sort((a, b) => (b.offlineCapacity?.capacityOffline || 0) - (a.offlineCapacity?.capacityOffline || 0)).slice(0, 30);
        const ptbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px", marginBottom: "16px" } });
        const phdr = el("tr", {});
        ["Refinery", "State", "Unit", "Unit Type", "Offline (kbd)", "Start", "End", "Days", "Type"].forEach(h => {
          const th = el("th", { style: { padding: "8px 6px", background: "#1e293b", color: "#94a3b8", textAlign: "left", borderBottom: "2px solid #334155", fontWeight: "700", whiteSpace: "nowrap" } }, h);
          phdr.appendChild(th);
        });
        ptbl.appendChild(phdr);

        pastEvents.forEach(e => {
          const cap = e.offlineCapacity?.capacityOffline || 0;
          const tr = el("tr", { style: { borderBottom: "1px solid #1e293b" } });
          const cell = (v, opts) => { const td = el("td", { style: { padding: "6px 6px", color: "#e2e8f0", ...opts } }, v); tr.appendChild(td); };
          cell(e.plantName || "", { fontWeight: "700", color: "#22c55e" });
          cell(e.plantPhysicalAddress?.stateName || "");
          cell(e.unitName || "");
          cell(e.unitTypeDesc || "", { color: "#94a3b8", fontSize: "10px" });
          cell(cap > 0 ? (cap / 1000).toFixed(1) : "-", { textAlign: "right", color: "#60a5fa", fontWeight: "700" });
          cell((e.associatedEntityStartDate || "").slice(0, 10));
          cell((e.associatedEntityEndDate || "").slice(0, 10));
          cell(String(e.eventDuration || 0));
          cell(e.eventType || "", { color: e.eventType === "Unplanned" ? "#ef4444" : "#22c55e" });
          ptbl.appendChild(tr);
        });
        container.appendChild(ptbl);
      }

      // ===== TURNAROUND TIMELINE (GANTT) =====
      container.appendChild(sectionTitle(`📊 Turnaround Timeline — ${countryLabel}`));
      const chartDiv4 = el("div", { id: "iir-gantt-chart", style: { width: "100%", height: "600px", marginBottom: "20px" } });
      container.appendChild(chartDiv4);

      // Build Gantt-like view using ongoing + future events with capacity > 0
      const ganttEvents = [...data.ongoing.events, ...data.future.events]
        .filter(e => (e.offlineCapacity?.capacityOffline || 0) > 10000)
        .sort((a, b) => (a.associatedEntityStartDate || "").localeCompare(b.associatedEntityStartDate || ""));

      if (ganttEvents.length > 0) {
        const ganttData = [];
        const colors = { "Planned": "#f59e0b", "Unplanned": "#ef4444", "Maintenance": "#60a5fa" };
        const statuses = [...new Set(ganttEvents.map(e => e.eventType || "Planned"))];

        statuses.forEach(status => {
          const evts = ganttEvents.filter(e => (e.eventType || "Planned") === status);
          ganttData.push({
            x: evts.map(e => {
              const s = (e.associatedEntityStartDate || "").slice(0, 10);
              const en = (e.associatedEntityEndDate || "").slice(0, 10);
              if (!s || !en) return 0;
              return (new Date(en) - new Date(s)) / 86400000;
            }),
            y: evts.map(e => (e.plantName || "") + " — " + (e.unitName || "").slice(0, 20)),
            base: evts.map(e => (e.associatedEntityStartDate || "").slice(0, 10)),
            type: "bar",
            orientation: "h",
            name: status,
            marker: { color: colors[status] || "#94a3b8" },
            text: evts.map(e => {
              const cap = e.offlineCapacity?.capacityOffline || 0;
              return (cap / 1000).toFixed(0) + " kbd, " + (e.eventDuration || 0) + "d";
            }),
            hovertemplate: "%{y}<br>Start: %{base}<br>Duration: %{x} days<br>%{text}<extra></extra>"
          });
        });

        loadPlotly(() => {
          Plotly.newPlot("iir-gantt-chart", ganttData, {
            title: { text: "Turnaround Schedule (>10 kbd units)", font: { color: "#f59e0b", size: 14 } },
            barmode: "stack",
            paper_bgcolor: "#0f172a", plot_bgcolor: "#0f172a",
            xaxis: { color: "#94a3b8", type: "date", gridcolor: "#1e293b", title: { text: "Date", font: { size: 11 } } },
            yaxis: { color: "#94a3b8", autorange: "reversed", tickfont: { size: 9 } },
            margin: { t: 50, b: 60, l: 280, r: 20 },
            legend: { font: { color: "#94a3b8" } },
            showlegend: true,
          }, { responsive: true });
        });
      }

      // ===== FUTURE OFFLINE BY UNIT TYPE =====
      if (Object.keys(data.byUnitType).length > 0) {
        container.appendChild(sectionTitle(`🔧 Total Planned Offline by Unit Type (Future) — ${countryLabel}`));
        const chartDiv5 = el("div", { id: "iir-future-unittype-chart", style: { width: "100%", height: "450px", marginBottom: "20px" } });
        container.appendChild(chartDiv5);

        const futEntries = Object.entries(data.byUnitType).filter(([k, v]) => v.future > 0).sort((a, b) => b[1].future - a[1].future);
        if (futEntries.length > 0) {
          loadPlotly(() => {
            Plotly.newPlot("iir-future-unittype-chart", [{
              x: futEntries.map(([k]) => k),
              y: futEntries.map(([, v]) => v.future / 1000),
              type: "bar",
              marker: { color: "#a78bfa" },
              text: futEntries.map(([, v]) => (v.future / 1000).toFixed(0) + " kbd"),
              textposition: "outside",
              hovertemplate: "%{x}<br>%{y:.0f} kbd planned<extra></extra>"
            }], {
              title: { text: "Planned Future Offline Capacity by Unit Type (kbd)", font: { color: "#f59e0b", size: 14 } },
              paper_bgcolor: "#0f172a", plot_bgcolor: "#0f172a",
              xaxis: { color: "#94a3b8", tickangle: -35, tickfont: { size: 10 } },
              yaxis: { color: "#94a3b8", title: { text: "Planned Offline (kbd)", font: { size: 11 } }, gridcolor: "#1e293b" },
              margin: { t: 50, b: 120, l: 60, r: 20 }
            }, { responsive: true });
          });
        }
      }

      // ===== REFINERY EXPLORER =====
      container.appendChild(sectionTitle(`🏭 Refinery Explorer — ${countryLabel}`));
      const refExplorer = el("div", { style: { marginBottom: "24px" } });
      container.appendChild(refExplorer);

      const refLoadBtn = el("button", { style: { background: "linear-gradient(135deg, #60a5fa, #3b82f6)", color: "#fff", border: "none", borderRadius: "8px", padding: "10px 24px", fontWeight: "700", fontSize: "12px", cursor: "pointer", marginBottom: "16px" } }, "LOAD REFINERY LIST");
      refExplorer.appendChild(refLoadBtn);

      const refSearch = el("input", { type: "text", placeholder: "Search refineries...", style: { background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", borderRadius: "6px", padding: "8px 12px", fontSize: "12px", width: "250px", marginLeft: "12px", display: "none" } });
      refExplorer.appendChild(refSearch);

      const refListArea = el("div", {});
      refExplorer.appendChild(refListArea);

      const refDetailArea = el("div", { style: { marginTop: "16px" } });
      container.appendChild(refDetailArea);

      refLoadBtn.onclick = async () => {
        refLoadBtn.textContent = "Loading...";
        refLoadBtn.disabled = true;
        try {
          const resp = await fetch(`/api/iir/refineries?country=${encodeURIComponent(country)}`);
          if (!resp.ok) throw new Error(await resp.text());
          const rData = await resp.json();
          refLoadBtn.style.display = "none";
          refSearch.style.display = "inline-block";
          _renderRefineryList(refListArea, refDetailArea, rData, country);
        } catch(e) {
          refListArea.innerHTML = '<div style="color:#ef4444;padding:12px;">Error: ' + e.message + '</div>';
        }
        refLoadBtn.textContent = "LOAD REFINERY LIST";
        refLoadBtn.disabled = false;
      };

      refSearch.oninput = () => {
        const q = refSearch.value.toLowerCase();
        const rows = refListArea.querySelectorAll("tr[data-refinery]");
        rows.forEach(row => {
          const name = (row.getAttribute("data-refinery") || "").toLowerCase();
          const state = (row.getAttribute("data-state") || "").toLowerCase();
          row.style.display = (name.includes(q) || state.includes(q)) ? "" : "none";
        });
      };
    }

    function _renderRefineryList(listArea, detailArea, rData, country) {
      listArea.innerHTML = "";
      const refs = rData.refineries || [];

      const summary = el("div", { style: { fontSize: "12px", color: "#94a3b8", marginBottom: "12px" } }, `${refs.length} refineries found in ${rData.country || country}. Click a refinery to view its full history.`);
      listArea.appendChild(summary);

      const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px" } });
      const hdr = el("tr", {});
      ["", "Refinery", "State", "Status", "Currently Offline", "Ongoing", "Future", "Past (2yr)", "Total", "Unit Types"].forEach(h => {
        hdr.appendChild(el("th", { style: { padding: "8px 6px", background: "#1e293b", color: "#94a3b8", textAlign: h === "Currently Offline" ? "right" : "left", borderBottom: "2px solid #334155", fontWeight: "700", whiteSpace: "nowrap", position: "sticky", top: "0", zIndex: "1" } }, h));
      });
      tbl.appendChild(hdr);

      refs.forEach(r => {
        const tr = el("tr", { "data-refinery": r.plantName, "data-state": r.state, style: { borderBottom: "1px solid #1e293b", cursor: "pointer", transition: "background 0.15s" } });
        tr.onmouseenter = () => { tr.style.background = "#1e293b"; };
        tr.onmouseleave = () => { tr.style.background = ""; };

        const isOffline = r.ongoingEvents > 0;
        const statusDot = el("td", { style: { padding: "6px 4px", textAlign: "center" } });
        statusDot.innerHTML = isOffline ? '<span style="color:#ef4444;font-size:14px;">●</span>' : '<span style="color:#22c55e;font-size:14px;">●</span>';
        tr.appendChild(statusDot);

        const cell = (v, opts) => { tr.appendChild(el("td", { style: { padding: "6px 6px", color: "#e2e8f0", ...opts } }, String(v))); };
        cell(r.plantName, { fontWeight: "700", color: "#f59e0b" });
        cell(r.state);
        cell(isOffline ? "OFFLINE" : "ONLINE", { color: isOffline ? "#ef4444" : "#22c55e", fontWeight: "700", fontSize: "10px" });
        cell(isOffline ? (r.ongoingOffline / 1000).toFixed(1) + " kbd" : "-", { textAlign: "right", color: isOffline ? "#ef4444" : "#64748b", fontWeight: isOffline ? "700" : "400" });
        cell(r.ongoingEvents, { textAlign: "center", color: r.ongoingEvents > 0 ? "#ef4444" : "#64748b" });
        cell(r.futureEvents, { textAlign: "center", color: r.futureEvents > 0 ? "#f59e0b" : "#64748b" });
        cell(r.pastEvents, { textAlign: "center", color: r.pastEvents > 0 ? "#22c55e" : "#64748b" });
        cell(r.totalEvents, { textAlign: "center", fontWeight: "600" });
        cell((r.unitTypes || []).join(", "), { color: "#94a3b8", fontSize: "10px", maxWidth: "200px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" });

        tr.onclick = () => {
          _loadRefineryDetail(detailArea, r.plantName, country);
          detailArea.scrollIntoView({ behavior: "smooth", block: "start" });
        };
        tbl.appendChild(tr);
      });

      const wrapper = el("div", { style: { maxHeight: "500px", overflowY: "auto", border: "1px solid #1e293b", borderRadius: "8px" } });
      wrapper.appendChild(tbl);
      listArea.appendChild(wrapper);
    }

    async function _loadRefineryDetail(detailArea, plantName, country) {
      detailArea.innerHTML = '<div style="text-align:center;padding:30px;color:#94a3b8;">Loading ' + plantName + ' history...</div>';
      try {
        const resp = await fetch(`/api/iir/refinery_detail?plant_name=${encodeURIComponent(plantName)}&country=${encodeURIComponent(country)}`);
        if (!resp.ok) throw new Error(await resp.text());
        const d = await resp.json();
        _renderRefineryDetail(detailArea, d);
      } catch(e) {
        detailArea.innerHTML = '<div style="color:#ef4444;padding:20px;">Error loading refinery: ' + e.message + '</div>';
      }
    }

    function _renderRefineryDetail(detailArea, d) {
      detailArea.innerHTML = "";
      const C2 = C;

      // Header
      const hdr = el("div", { style: { display: "flex", alignItems: "center", gap: "16px", marginBottom: "16px", flexWrap: "wrap" } });
      hdr.appendChild(el("div", { style: { fontSize: "20px", fontWeight: "800", color: "#f59e0b" } }, d.plantName));
      const statusColor = d.currentStatus === "Offline" ? "#ef4444" : d.currentStatus === "Upcoming" ? "#f59e0b" : "#22c55e";
      hdr.appendChild(el("span", { style: { background: statusColor + "22", color: statusColor, border: "1px solid " + statusColor + "66", borderRadius: "6px", padding: "4px 12px", fontSize: "11px", fontWeight: "700" } }, d.currentStatus.toUpperCase()));
      if (d.state) hdr.appendChild(el("span", { style: { fontSize: "12px", color: "#94a3b8" } }, d.state + (d.region ? " / " + d.region : "")));
      const closeBtn = el("button", { style: { marginLeft: "auto", background: "#334155", color: "#e2e8f0", border: "none", borderRadius: "6px", padding: "6px 14px", fontSize: "11px", cursor: "pointer" } }, "CLOSE");
      closeBtn.onclick = () => { detailArea.innerHTML = ""; };
      hdr.appendChild(closeBtn);
      detailArea.appendChild(hdr);

      // Summary cards
      const cardRow = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "10px", marginBottom: "20px" } });
      function miniCard(label, val, color) {
        const c = el("div", { style: { background: "#0f172a", borderRadius: "8px", border: "1px solid #1e293b", padding: "12px", textAlign: "center" } });
        c.appendChild(el("div", { style: { fontSize: "10px", color: "#94a3b8", textTransform: "uppercase", fontWeight: "600", marginBottom: "6px" } }, label));
        c.appendChild(el("div", { style: { fontSize: "22px", fontWeight: "800", color: color } }, String(val)));
        return c;
      }
      cardRow.appendChild(miniCard("Currently Offline", d.currentOfflineBpd > 0 ? (d.currentOfflineBpd / 1000).toFixed(1) + " kbd" : "-", "#ef4444"));
      cardRow.appendChild(miniCard("Ongoing Events", d.ongoingEvents.length, "#ef4444"));
      cardRow.appendChild(miniCard("Future Planned", d.futureEvents.length, "#f59e0b"));
      cardRow.appendChild(miniCard("Past Events", d.pastEvents.length, "#22c55e"));
      cardRow.appendChild(miniCard("Total Events", d.totalEvents, "#60a5fa"));
      detailArea.appendChild(cardRow);

      // Ongoing events detail
      if (d.ongoingEvents.length > 0) {
        detailArea.appendChild(el("div", { style: { fontSize: "14px", fontWeight: "700", color: "#ef4444", margin: "16px 0 8px 0" } }, "Currently Offline Units"));
        const otbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px", marginBottom: "16px" } });
        const ohdr = el("tr", {});
        ["Unit", "Unit Type", "Offline (kbd)", "Start", "End", "Days", "Type", "Confirmation", "Notes"].forEach(h => {
          ohdr.appendChild(el("th", { style: { padding: "6px 6px", background: "#1e293b", color: "#94a3b8", textAlign: "left", borderBottom: "2px solid #ef444444", fontWeight: "700" } }, h));
        });
        otbl.appendChild(ohdr);
        d.ongoingEvents.forEach(ev => {
          const tr = el("tr", { style: { borderBottom: "1px solid #1e293b" } });
          const cell = (v, opts) => { tr.appendChild(el("td", { style: { padding: "5px 6px", color: "#e2e8f0", ...opts } }, String(v))); };
          cell(ev.unitName);
          cell(ev.unitTypeDesc, { color: "#94a3b8" });
          cell(ev.capacityOffline > 0 ? (ev.capacityOffline / 1000).toFixed(1) : "-", { textAlign: "right", color: "#ef4444", fontWeight: "700" });
          cell(ev.startDate);
          cell(ev.endDate);
          cell(ev.duration || "-");
          cell(ev.eventType, { color: ev.eventType === "Unplanned" ? "#ef4444" : "#22c55e" });
          cell(ev.confirmation, { color: ev.confirmation === "Confirmed" ? "#22c55e" : "#f59e0b", fontSize: "10px" });
          cell(ev.comments ? ev.comments.slice(0, 80) + (ev.comments.length > 80 ? "..." : "") : "-", { color: "#64748b", fontSize: "10px" });
          otbl.appendChild(tr);
        });
        detailArea.appendChild(otbl);
      }

      // Historical offline capacity chart
      if (d.timeline && d.timeline.length > 0) {
        detailArea.appendChild(el("div", { style: { fontSize: "14px", fontWeight: "700", color: "#60a5fa", margin: "16px 0 8px 0" } }, "Historical Offline Capacity"));
        const chartId = "iir-ref-timeline-" + Date.now();
        const chartDiv = el("div", { id: chartId, style: { width: "100%", height: "400px", marginBottom: "20px" } });
        detailArea.appendChild(chartDiv);

        loadPlotly(() => {
          const months = d.timeline.map(t => t.month);
          const vals = d.timeline.map(t => t.offlineBpd / 1000);
          const evCounts = d.timeline.map(t => t.events);
          const colors = vals.map(v => v > 0 ? "#ef4444" : "#22c55e");
          Plotly.newPlot(chartId, [{
            x: months,
            y: vals,
            type: "bar",
            marker: { color: colors },
            text: vals.map((v, i) => v.toFixed(1) + " kbd (" + evCounts[i] + " events)"),
            hovertemplate: "%{x}<br>%{y:.1f} kbd offline<br>%{text}<extra></extra>"
          }], {
            title: { text: d.plantName + " — Monthly Avg Offline Capacity (kbd)", font: { color: "#f59e0b", size: 14 } },
            paper_bgcolor: "#0f172a", plot_bgcolor: "#0f172a",
            xaxis: { color: "#94a3b8", tickangle: -45, tickfont: { size: 10 }, gridcolor: "#1e293b" },
            yaxis: { color: "#94a3b8", title: { text: "Avg Offline (kbd)", font: { size: 11 } }, gridcolor: "#1e293b" },
            margin: { t: 50, b: 80, l: 60, r: 20 }
          }, { responsive: true });
        });
      }

      // Unit type breakdown chart
      if (d.unitSummary && d.unitSummary.length > 0) {
        detailArea.appendChild(el("div", { style: { fontSize: "14px", fontWeight: "700", color: "#a78bfa", margin: "16px 0 8px 0" } }, "Events by Unit Type"));
        const ucId = "iir-ref-units-" + Date.now();
        const ucDiv = el("div", { id: ucId, style: { width: "100%", height: "350px", marginBottom: "20px" } });
        detailArea.appendChild(ucDiv);

        loadPlotly(() => {
          const unitColors = ["#ef4444", "#f59e0b", "#22c55e", "#60a5fa", "#a78bfa", "#ec4899", "#14b8a6", "#f97316"];
          Plotly.newPlot(ucId, [{
            labels: d.unitSummary.map(u => u.unitType),
            values: d.unitSummary.map(u => u.events),
            type: "pie",
            marker: { colors: unitColors },
            textinfo: "label+value",
            textfont: { size: 11, color: "#e2e8f0" },
            hovertemplate: "%{label}<br>%{value} events<br>Max capacity: %{customdata} b/d<extra></extra>",
            customdata: d.unitSummary.map(u => (u.maxCapacity || 0).toLocaleString()),
          }], {
            title: { text: d.plantName + " — Events by Unit Type", font: { color: "#a78bfa", size: 14 } },
            paper_bgcolor: "#0f172a", plot_bgcolor: "#0f172a",
            legend: { font: { color: "#94a3b8", size: 10 } },
            margin: { t: 50, b: 20, l: 20, r: 20 }
          }, { responsive: true });
        });
      }

      // Full event history table
      detailArea.appendChild(el("div", { style: { fontSize: "14px", fontWeight: "700", color: "#f59e0b", margin: "16px 0 8px 0" } }, "Full Event History (" + d.totalEvents + " events)"));
      const htbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px", marginBottom: "20px" } });
      const hhdr = el("tr", {});
      ["Status", "Unit", "Unit Type", "Offline (kbd)", "Start", "End", "Days", "Type", "Confirmation", "Notes"].forEach(h => {
        hhdr.appendChild(el("th", { style: { padding: "7px 6px", background: "#1e293b", color: "#94a3b8", textAlign: "left", borderBottom: "2px solid #334155", fontWeight: "700", whiteSpace: "nowrap", position: "sticky", top: "0", zIndex: "1" } }, h));
      });
      htbl.appendChild(hhdr);

      (d.allEvents || []).forEach(ev => {
        const tr = el("tr", { style: { borderBottom: "1px solid #1e293b" } });
        const statusColors = { "Ongoing": "#ef4444", "Future": "#f59e0b", "Past": "#22c55e" };
        const sc = statusColors[ev.eventStatus] || "#64748b";
        const cell = (v, opts) => { tr.appendChild(el("td", { style: { padding: "5px 6px", color: "#e2e8f0", ...opts } }, String(v))); };
        cell(ev.eventStatus, { color: sc, fontWeight: "700", fontSize: "10px" });
        cell(ev.unitName);
        cell(ev.unitTypeDesc, { color: "#94a3b8", fontSize: "10px" });
        cell(ev.capacityOffline > 0 ? (ev.capacityOffline / 1000).toFixed(1) : "-", { textAlign: "right", color: "#60a5fa", fontWeight: "600" });
        cell(ev.startDate);
        cell(ev.endDate);
        cell(ev.duration || "-");
        cell(ev.eventType, { color: ev.eventType === "Unplanned" ? "#ef4444" : "#22c55e" });
        cell(ev.confirmation || "-", { color: ev.confirmation === "Confirmed" ? "#22c55e" : "#f59e0b", fontSize: "10px" });
        cell(ev.comments ? ev.comments.slice(0, 100) + (ev.comments.length > 100 ? "..." : "") : "-", { color: "#64748b", fontSize: "10px" });
        htbl.appendChild(tr);
      });

      const hwrap = el("div", { style: { maxHeight: "400px", overflowY: "auto", border: "1px solid #1e293b", borderRadius: "8px" } });
      hwrap.appendChild(htbl);
      detailArea.appendChild(hwrap);
    }

    // Auto-load on tab open
    loadData();
  }


  // ═══════════════════════════════════════════════════════════════════════════
  // ═══  CRUDE BALANCES & MARGINS (NWE/MED)
  // ═══════════════════════════════════════════════════════════════════════════

  // ── Global crude balances dashboard (monthly supply/demand/balance, runs,
  // quality, OPEC+, stocks, price outlook). Rendered at the top of the
  // Crude Bal & Margins tab. Source branding intentionally omitted.
  async function renderCrudeBalances(container) {
    let d;
    try {
      const r = await fetch("/api/crude-balances");
      if (!r.ok) return;
      d = await r.json();
    } catch (e) { return; }
    if (!d || !d.months) return;
    await new Promise(res => loadPlotly(res));

    const M = d.months;
    const ci = M.indexOf(d.current_month);
    const cur = ci >= 0 ? ci : M.length - 1;
    const fcIdx = M.indexOf(d.forecast_from);
    const mb = v => (v == null ? null : v / 1000);
    const REG_COL = {
      "North America": C.cyan, "Latin America": "#f59e0b", "Europe": C.blue,
      "FSU": C.purple, "North Africa": "#eab308", "Africa": "#f97316",
      "Middle East": C.green, "Asia": C.red,
    };
    // Forecast shading for month-indexed charts
    const fcShapes = () => (fcIdx > 0 ? [{
      type: "rect", xref: "x", yref: "paper",
      x0: M[fcIdx], x1: M[M.length - 1], y0: 0, y1: 1,
      fillcolor: "rgba(148,163,184,0.07)", line: { width: 0 }, layer: "below",
    }] : []);
    const fcAnno = () => (fcIdx > 0 ? [{
      x: M[fcIdx], y: 1, yref: "paper", xref: "x", yanchor: "bottom",
      text: "forecast →", showarrow: false, font: { size: 10, color: C.muted },
    }] : []);
    const monthLabel = m => { const [y, mm] = m.split("-"); return ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][+mm] + " " + y.slice(2); };

    // ── Header ──
    container.appendChild(el("div", { style: { fontSize: "16px", fontWeight: "800", color: C.gold, marginBottom: "3px" } },
      "🛢️ GLOBAL CRUDE BALANCES"));
    container.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, marginBottom: "14px" } },
      `Monthly crude & condensate supply / demand / balance, refinery runs, OPEC+ output and price outlook · ${monthLabel(M[0])} → ${monthLabel(M[M.length - 1])} · latest actual ${monthLabel(d.current_month)}, thereafter forecast (kb/d unless noted)`));

    // ── KPI row ──
    const g = d.global;
    const bal = g.balance[cur];
    const brent = d.prices["Dated Brent"] ? d.prices["Dated Brent"][d.sd_months.indexOf(d.current_month)] : null;
    const days = d.stocks_mmb["OECD stocks Days Cover"] ? d.stocks_mmb["OECD stocks Days Cover"][d.sd_months.indexOf(d.current_month)] : null;
    container.appendChild(card("Snapshot — " + monthLabel(d.current_month), statRow([
      ["Crude Supply", mb(g.supply[cur]).toFixed(2) + " mb/d", C.text],
      ["Crude Demand", mb(g.demand[cur]).toFixed(2) + " mb/d", C.text],
      [bal >= 0 ? "Surplus" : "Deficit", (bal >= 0 ? "+" : "") + mb(bal).toFixed(2) + " mb/d", bal >= 0 ? C.green : C.red],
      ["Refinery Runs", mb(g.refinery_intake[cur]).toFixed(2) + " mb/d", C.cyan],
      ["OECD Days Cover", days != null ? days.toFixed(1) + "d" : "—", C.text],
      ["Dated Brent", brent != null ? "$" + brent.toFixed(1) : "—", C.gold],
    ])));

    // ── Chart 1: Global balance ──
    const c1 = el("div", { id: "cb-global", style: { width: "100%", height: "440px" } });
    container.appendChild(card("Global Crude Balance — supply vs demand (lines) & balance (bars), mb/d", c1));
    const balColors = M.map((_, i) => (g.balance[i] >= 0 ? C.green : C.red));
    Plotly.newPlot("cb-global", [
      { x: M, y: g.balance.map(mb), type: "bar", name: "Balance", marker: { color: balColors, opacity: 0.55 } },
      { x: M, y: g.supply.map(mb), name: "Supply", line: { color: C.cyan, width: 2 } },
      { x: M, y: g.demand.map(mb), name: "Demand", line: { color: C.gold, width: 2 } },
    ], {
      ...plotLayout, height: 440, barmode: "relative",
      yaxis: { ...plotLayout.yaxis, title: { text: "mb/d", font: { size: 12 } } },
      xaxis: { ...plotLayout.xaxis, type: "category", nticks: 20 },
      shapes: fcShapes(), annotations: fcAnno(),
    }, { responsive: true, displaylogo: false });

    // ── Chart 2: Regional balance (with region filter) ──
    const head2 = el("div", { style: { display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px", flexWrap: "wrap" } });
    head2.appendChild(el("span", { style: { fontSize: "11.5px", fontWeight: "700", color: C.amber, textTransform: "uppercase", letterSpacing: "1.2px" } }, "Regional Crude Balance"));
    const regSel = el("select", { style: { background: C.card, color: C.text, border: "1px solid " + C.border, borderRadius: "4px", padding: "4px 10px", fontSize: "12px" } });
    ["ALL (current month)", ...d.regions].forEach(r => { const o = document.createElement("option"); o.value = r; o.textContent = r; regSel.appendChild(o); });
    head2.appendChild(regSel);
    const c2 = el("div", { id: "cb-region", style: { width: "100%", height: "420px" } });
    const cardR = card(null, el("div", {}, [head2, c2]));
    container.appendChild(cardR);
    function drawRegion(sel) {
      if (sel.startsWith("ALL")) {
        const vals = d.regions.map(r => mb(d.balance[r][cur]));
        Plotly.newPlot("cb-region", [{
          x: d.regions, y: vals, type: "bar",
          marker: { color: vals.map(v => (v >= 0 ? C.green : C.red)) },
          text: vals.map(v => (v >= 0 ? "+" : "") + v.toFixed(1)), textposition: "outside",
        }], {
          ...plotLayout, height: 420, showlegend: false,
          title: { text: "Net crude balance by region — " + monthLabel(d.current_month) + " (mb/d, surplus vs deficit)", font: { size: 12, color: C.muted } },
          yaxis: { ...plotLayout.yaxis, title: { text: "mb/d", font: { size: 12 } } },
          xaxis: { ...plotLayout.xaxis },
        }, { responsive: true, displaylogo: false });
      } else {
        const col = REG_COL[sel] || C.cyan;
        Plotly.newPlot("cb-region", [
          { x: M, y: d.balance[sel].map(mb), type: "bar", name: "Balance", marker: { color: M.map((_, i) => (d.balance[sel][i] >= 0 ? C.green : C.red)), opacity: 0.5 } },
          { x: M, y: d.supply[sel].map(mb), name: "Supply", line: { color: C.cyan, width: 2 } },
          { x: M, y: d.demand[sel].map(mb), name: "Demand", line: { color: C.gold, width: 2 } },
        ], {
          ...plotLayout, height: 420, barmode: "relative",
          title: { text: sel + " — crude supply / demand / balance (mb/d)", font: { size: 12, color: C.muted } },
          yaxis: { ...plotLayout.yaxis, title: { text: "mb/d", font: { size: 12 } } },
          xaxis: { ...plotLayout.xaxis, type: "category", nticks: 20 },
          shapes: fcShapes(), annotations: fcAnno(),
        }, { responsive: true, displaylogo: false });
      }
    }
    regSel.addEventListener("change", () => drawRegion(regSel.value));
    drawRegion("ALL (current month)");

    // ── Chart 3: Refinery runs ──
    const c3 = el("div", { id: "cb-runs", style: { width: "100%", height: "420px" } });
    container.appendChild(card("Global Refinery Runs (crude intake, mb/d)", c3));
    Plotly.newPlot("cb-runs", [
      { x: M, y: g.refinery_intake.map(mb), name: "Global Runs", line: { color: C.cyan, width: 2.5 }, fill: "tozeroy", fillcolor: "rgba(34,211,238,0.10)" },
    ], {
      ...plotLayout, height: 420, showlegend: false,
      yaxis: { ...plotLayout.yaxis, title: { text: "mb/d", font: { size: 12 } } },
      xaxis: { ...plotLayout.xaxis, type: "category", nticks: 20 },
      shapes: fcShapes(), annotations: fcAnno(),
    }, { responsive: true, displaylogo: false });

    // Regional runs (separate monthly window)
    if (d.runs && d.runs_months && d.runs_months.length) {
      const RM = d.runs_months;
      const runRegs = Object.keys(d.runs).filter(k => k !== "Total" && k !== "China" && k !== "Rest of Asia");
      const c3b = el("div", { id: "cb-runs-reg", style: { width: "100%", height: "440px" } });
      container.appendChild(card("Refinery Runs by Region (mb/d) — " + monthLabel(RM[0]) + " → " + monthLabel(RM[RM.length - 1]), c3b));
      const traces = runRegs.map(r => ({
        x: RM.map(monthLabel), y: d.runs[r].map(mb), type: "bar", name: r,
        marker: { color: REG_COL[r === "Asia Pacific" ? "Asia" : r] || C.muted },
      }));
      Plotly.newPlot("cb-runs-reg", traces, {
        ...plotLayout, height: 440, barmode: "stack",
        yaxis: { ...plotLayout.yaxis, title: { text: "mb/d", font: { size: 12 } } },
        xaxis: { ...plotLayout.xaxis },
      }, { responsive: true, displaylogo: false });
    }

    // ── Chart 4: Supply by quality ──
    if (d.quality) {
      const q = d.quality;
      const c4 = el("div", { id: "cb-quality", style: { width: "100%", height: "420px" } });
      container.appendChild(card("Global Supply by Quality (mb/d, stacked)", c4));
      const qDefs = [
        ["Heavy", "Heavy Crude", C.red], ["Medium", "Medium Crude", "#f59e0b"],
        ["Light", "Light Crude", C.gold], ["Condensate", "Condensate", C.cyan],
        ["NGLs", "NGLs", C.blue], ["Biofuels", "Biofuels", C.green],
      ];
      Plotly.newPlot("cb-quality", qDefs.filter(x => q[x[0]]).map(x => ({
        x: M, y: q[x[0]].map(mb), name: x[1], stackgroup: "q", line: { width: 0.5, color: x[2] }, fillcolor: x[2],
      })), {
        ...plotLayout, height: 420,
        yaxis: { ...plotLayout.yaxis, title: { text: "mb/d", font: { size: 12 } } },
        xaxis: { ...plotLayout.xaxis, type: "category", nticks: 20 },
        shapes: fcShapes(), annotations: fcAnno(),
      }, { responsive: true, displaylogo: false });
    }

    // ── Chart 5: OPEC+ output & spare capacity ──
    if (d.opec && d.opec_months && d.opec["Total OPEC+"]) {
      const OM = d.opec_months;
      const c5 = el("div", { id: "cb-opec", style: { width: "100%", height: "420px" } });
      container.appendChild(card("OPEC+ Crude Output & Spare Capacity (mb/d)", c5));
      const tr = [
        { key: "Total OPEC+", col: C.gold, w: 2.5 },
        { key: "Total OPEC OPEC+", col: C.cyan, w: 2, name: "OPEC (of OPEC+)" },
        { key: "Total Non-OPEC OPEC+", col: C.blue, w: 2, name: "Non-OPEC (of OPEC+)" },
        { key: "Spare Capacity", col: C.purple, w: 2, dash: "dot" },
      ].filter(t => d.opec[t.key]);
      Plotly.newPlot("cb-opec", tr.map(t => ({
        x: OM, y: d.opec[t.key].map(mb), name: t.name || t.key, line: { color: t.col, width: t.w, dash: t.dash },
      })), {
        ...plotLayout, height: 420,
        yaxis: { ...plotLayout.yaxis, title: { text: "mb/d", font: { size: 12 } } },
        xaxis: { ...plotLayout.xaxis, type: "category", nticks: 20 },
      }, { responsive: true, displaylogo: false });
    }

    // ── Chart 6: OECD stocks & days cover ──
    if (d.stocks_mmb && d.stocks_mmb["Onland OECD Company Stocks"]) {
      const SM = d.sd_months;
      const s = d.stocks_mmb;
      const c6 = el("div", { id: "cb-stocks", style: { width: "100%", height: "420px" } });
      container.appendChild(card("OECD Onland Company Stocks (mmb) & Days Cover", c6));
      const tr6 = [
        { x: SM, y: s["Onland OECD Company Stocks"], name: "OECD Stocks (mmb)", line: { color: C.cyan, width: 2.5 } },
      ];
      if (s["5 Year Average"]) tr6.push({ x: SM, y: s["5 Year Average"], name: "5-Yr Avg (mmb)", line: { color: C.muted, width: 1.5, dash: "dot" } });
      if (s["OECD stocks Days Cover"]) tr6.push({ x: SM, y: s["OECD stocks Days Cover"], name: "Days Cover (RHS)", yaxis: "y2", line: { color: C.gold, width: 2 } });
      Plotly.newPlot("cb-stocks", tr6, {
        ...plotLayout, height: 420,
        yaxis: { ...plotLayout.yaxis, title: { text: "mmb", font: { size: 12 } } },
        yaxis2: { overlaying: "y", side: "right", gridcolor: "rgba(0,0,0,0)", tickfont: { size: 11, color: C.gold }, title: { text: "days", font: { size: 11, color: C.gold } } },
        xaxis: { ...plotLayout.xaxis, type: "category", nticks: 16 },
      }, { responsive: true, displaylogo: false });
    }

    // ── Chart 7: Price outlook ──
    if (d.prices && d.prices["Dated Brent"]) {
      const SM = d.sd_months;
      const c7 = el("div", { id: "cb-prices", style: { width: "100%", height: "400px" } });
      container.appendChild(card("Crude Price Outlook ($/bbl)", c7));
      const pDefs = [["Dated Brent", C.gold], ["WTI Cushing", C.cyan], ["Dubai M1", C.green], ["Urals CIF NWE", C.red]];
      Plotly.newPlot("cb-prices", pDefs.filter(p => d.prices[p[0]]).map(p => ({
        x: SM, y: d.prices[p[0]], name: p[0], line: { color: p[1], width: 2 },
      })), {
        ...plotLayout, height: 400,
        yaxis: { ...plotLayout.yaxis, title: { text: "$/bbl", font: { size: 12 } } },
        xaxis: { ...plotLayout.xaxis, type: "category", nticks: 16 },
      }, { responsive: true, displaylogo: false });
    }

    // ── Regional balance table ──
    const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "12px" } });
    const thead = el("thead");
    const hr = el("tr", { style: { borderBottom: `2px solid ${C.border}` } });
    ["Region", "Supply (mb/d)", "Demand (mb/d)", "Balance (mb/d)", "Status"].forEach((h, i) => {
      hr.appendChild(el("th", { style: { textAlign: i === 0 ? "left" : "right", padding: "8px 10px", color: C.amber, fontSize: "10px", textTransform: "uppercase" } }, h));
    });
    thead.appendChild(hr); tbl.appendChild(thead);
    const tb = el("tbody");
    d.regions.forEach(r => {
      const b = mb(d.balance[r][cur]);
      const tr = el("tr", { style: { borderBottom: `1px solid ${C.border}` } });
      tr.appendChild(el("td", { style: { padding: "7px 10px", color: C.text, fontWeight: "600" } }, r));
      tr.appendChild(el("td", { style: { padding: "7px 10px", textAlign: "right", color: C.text } }, mb(d.supply[r][cur]).toFixed(2)));
      tr.appendChild(el("td", { style: { padding: "7px 10px", textAlign: "right", color: C.text } }, mb(d.demand[r][cur]).toFixed(2)));
      tr.appendChild(el("td", { style: { padding: "7px 10px", textAlign: "right", color: b >= 0 ? C.green : C.red, fontWeight: "700" } }, (b >= 0 ? "+" : "") + b.toFixed(2)));
      tr.appendChild(el("td", { style: { padding: "7px 10px", textAlign: "right", color: b >= 0 ? C.green : C.red } }, b >= 0 ? "Surplus" : "Deficit"));
      tb.appendChild(tr);
    });
    tbl.appendChild(tb);
    container.appendChild(card("Regional Crude Balance — " + monthLabel(d.current_month), tbl));

    container.appendChild(el("div", { style: { height: "1px", background: C.border, margin: "10px 0 22px" } }));
  }

  // ─── CRUDE BALANCES TAB (multi-sheet workbook: /api/crude_bal_v2) ───
  // Dropdown selects a sheet; each view renders analysis → overall table →
  // total-balance graph (first) → detail/statistical/seasonal charts.
  async function renderCBM(box) {
    box.innerHTML = '<div style="color:#94a3b8;padding:40px;text-align:center;">Loading Crude Balances…</div>';
    let blob;
    try {
      const r = await fetch("/api/crude_bal_v2");
      if (!r.ok) throw new Error(await r.text());
      blob = await r.json();
    } catch (e) {
      box.innerHTML = `<div style="color:#ef4444;padding:40px;">Failed to load Crude Balances: ${e.message}</div>`;
      return;
    }
    box.innerHTML = "";
    const sheets = (blob.sheets || []);
    const anchor = blob.anchor || "2026-07";
    if (!sheets.length) { box.innerHTML = '<div style="color:#94a3b8;padding:40px;">No data.</div>'; return; }

    const PAL = ["#38bdf8", "#f59e0b", "#22c55e", "#ef4444", "#8b5cf6", "#ec4899", "#22d3ee", "#84cc16", "#f97316", "#6366f1", "#14b8a6", "#e11d48"];
    const YRCOL = { 2015: "#3f4a63", 2016: "#475569", 2017: "#5b6577", 2018: "#64748b", 2019: "#0ea5e9", 2020: "#ef4444", 2021: "#f59e0b", 2022: "#22c55e", 2023: "#3b82f6", 2024: "#8b5cf6", 2025: "#ec4899", 2026: "#ffffff", 2027: "#f5b90f" };
    const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

    function seriesOf(sheet, grp, lbl) {
      const g = sheet.groups.find(x => x.code === grp);
      if (!g) return null;
      return g.series.find(s => s.label === lbl) || null;
    }
    function fmtVal(v, unit) {
      if (v == null) return "—";
      if (unit === "ratio") return (v * 100).toFixed(1) + "%";
      return v.toLocaleString(undefined, { maximumFractionDigits: unit === "mb" ? 1 : 0 });
    }
    function unitLabel(u) { return u === "ratio" ? "%" : u; }

    function baseLayout(title, yTitle, extra, months) {
      const ly = JSON.parse(JSON.stringify(plotLayout));
      ly.title = { text: title, font: { color: C.amber, size: 14 } };
      ly.paper_bgcolor = "transparent"; ly.plot_bgcolor = "transparent";
      ly.margin = { l: 70, r: 60, t: 44, b: 60 };
      ly.yaxis = { title: { text: yTitle, font: { color: C.muted, size: 11 } }, gridcolor: "#1e293b", color: C.muted, separatethousands: true, zeroline: true, zerolinecolor: "#334155" };
      ly.xaxis = { gridcolor: "#1e293b", color: C.muted, tickfont: { size: 10 } };
      // forecast boundary marker
      if (months && months.indexOf(anchor) >= 0 && months.indexOf(anchor) < months.length - 1) {
        const ax = anchor + "-01";
        ly.shapes = [{ type: "line", x0: ax, x1: ax, yref: "paper", y0: 0, y1: 1, line: { color: C.gold, width: 1, dash: "dot" } }];
        ly.annotations = [{ x: ax, xanchor: "left", yref: "paper", y: 1.02, text: " forecast ▶", showarrow: false, font: { size: 10, color: C.muted } }];
      }
      return Object.assign(ly, extra || {});
    }
    function rolling(vals, w) {
      return vals.map((_, i) => {
        const s = vals.slice(Math.max(0, i - w + 1), i + 1).filter(v => v != null);
        return s.length ? s.reduce((a, b) => a + b, 0) / s.length : null;
      });
    }
    function yoy(vals) { return vals.map((v, i) => (i >= 12 && v != null && vals[i - 12] != null) ? v - vals[i - 12] : null); }

    // ── header + dropdown ──
    const hdr = el("div", { style: { display: "flex", alignItems: "center", gap: "14px", marginBottom: "16px", flexWrap: "wrap" } });
    hdr.appendChild(el("div", { style: { fontSize: "20px", fontWeight: "800", color: C.amber } }, "🛢️ Crude Balances"));
    hdr.appendChild(el("span", { style: { color: C.muted, fontSize: "12px" } }, "Balance set:"));
    const sel = el("select", { style: { background: C.card, color: C.text, border: "1px solid " + C.border, borderRadius: "6px", padding: "7px 14px", fontSize: "13px", fontWeight: "600" } });
    sheets.forEach(s => { const o = document.createElement("option"); o.value = s.id; o.textContent = s.name; sel.appendChild(o); });
    const defId = sheets.some(s => s.id === "global") ? "global" : sheets[0].id;
    sel.value = defId;
    hdr.appendChild(sel);
    hdr.appendChild(el("span", { style: { color: C.muted, fontSize: "11px", marginLeft: "auto" } }, "As of July 2026 · model output, not investment advice"));
    box.appendChild(hdr);

    const view = el("div");
    box.appendChild(view);

    function plot(div, traces, layout) { try { Plotly.newPlot(div, traces, layout, { responsive: true, displayModeBar: false }); } catch (e) { div.innerHTML = `<div style="color:#ef4444;padding:12px">${e.message}</div>`; } }
    function chartDiv(h) { return el("div", { style: { width: "100%", height: (h || 420) + "px" } }); }

    // total-balance bar trace (sign-coloured)
    function balBar(x, vals, name, unit) {
      return { x, y: vals, name: name, type: "bar", marker: { color: vals.map(v => v == null ? "#334155" : v >= 0 ? C.green : C.red) }, hovertemplate: "%{x|%Y-%m}<br>" + name + ": %{y:,.0f} " + unitLabel(unit) + "<extra></extra>" };
    }
    function lineTrace(x, vals, name, color, unit, width) {
      return { x, y: vals, name, type: "scatter", mode: "lines", line: { width: width || 2, color }, connectgaps: false, hovertemplate: "%{x|%Y-%m}<br>" + name + ": %{y:,.1f} " + unitLabel(unit || "") + "<extra></extra>" };
    }
    // seasonal overlay of one series (month-of-year x, one trace per year)
    function seasonalTraces(months, vals) {
      const byYr = {};
      months.forEach((m, i) => {
        if (vals[i] == null) return;
        const [y, mo] = m.split("-").map(Number);
        (byYr[y] = byYr[y] || {})[mo - 1] = vals[i];
      });
      return Object.keys(byYr).sort().map(y => {
        const idx = Object.keys(byYr[y]).map(Number).sort((a, b) => a - b);
        return { x: idx.map(i => MON[i]), y: idx.map(i => byYr[y][i]), name: y, type: "scatter", mode: "lines+markers", line: { width: (+y >= 2025 ? 3 : 1.5), color: YRCOL[y] || "#64748b" }, marker: { size: (+y >= 2025 ? 6 : 3) }, opacity: (+y >= 2022 ? 1 : 0.45) };
      });
    }

    function overallTable(sheet, grp, order, maxCols) {
      const months = sheet.months;
      const start = Math.max(0, (months.indexOf(anchor) >= 0 ? months.indexOf(anchor) - 11 : months.length - 18));
      const rows = [];
      for (let i = months.length - 1; i >= start; i--) rows.push(i);
      const cols = order.slice(0, maxCols || 8).map(o => ({ o, s: seriesOf(sheet, o.group, o.label) })).filter(x => x.s);
      let h = '<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:11px;color:' + C.text + '">';
      h += '<thead><tr style="background:#111a2e;color:' + C.amber + '"><th style="padding:7px 9px;text-align:left;border:1px solid ' + C.border + ';position:sticky;left:0;background:#111a2e">Month</th>';
      cols.forEach(c => { h += `<th style="padding:7px 9px;text-align:right;border:1px solid ${C.border}">${c.s.label}<br><span style="color:${C.muted};font-weight:400">${unitLabel(c.s.unit)}</span></th>`; });
      h += "</tr></thead><tbody>";
      rows.forEach((i, ri) => {
        const bg = ri % 2 ? "#0f172a" : C.card;
        const fcst = months.indexOf(anchor) >= 0 && i >= months.indexOf(anchor);
        h += `<tr style="background:${bg}"><td style="padding:5px 9px;border:1px solid ${C.border};position:sticky;left:0;background:${bg}">${months[i]}${fcst ? ' <span style="color:' + C.gold + ';font-size:9px">FCST</span>' : ""}</td>`;
        cols.forEach(c => {
          const v = c.s.values[i];
          let col = C.text;
          if (c.s.unit !== "ratio" && /balance/i.test(c.s.label) && v != null) col = v >= 0 ? C.green : C.red;
          h += `<td style="padding:5px 9px;text-align:right;border:1px solid ${C.border};color:${col}">${fmtVal(v, c.s.unit)}</td>`;
        });
        h += "</tr>";
      });
      h += "</tbody></table></div>";
      const w = el("div"); w.innerHTML = h; return w;
    }

    function renderRegionalOrGlobal(sheet) {
      const months = sheet.months, x = months.map(m => m + "-01");
      const grp = sheet.groups[0];
      const primary = sheet.primary[0];
      const ps = seriesOf(sheet, primary.group, primary.label);
      // analysis
      view.appendChild(card("Analysis — " + sheet.name + " crude balance", sheet.analysis));
      // overall table
      view.appendChild(card("Overall table — recent months & forecast", overallTable(sheet, grp.code, sheet.order, 8)));
      // 1) total balance (first graph)
      const d1 = chartDiv(430); view.appendChild(card("Total balance (first) — " + primary.label + " (" + unitLabel(ps.unit) + ")", d1));
      // detail line charts
      const others = sheet.order.filter(o => o.label !== primary.label);
      const ratioS = others.filter(o => (seriesOf(sheet, o.group, o.label) || {}).unit === "ratio");
      const balS = others.filter(o => /balance/i.test(o.label) && (seriesOf(sheet, o.group, o.label) || {}).unit !== "ratio");
      const flowS = others.filter(o => !ratioS.includes(o) && !balS.includes(o));
      const d2 = balS.length ? chartDiv(400) : null; if (d2) view.appendChild(card("Balance breakdown — sweet / sour / total", d2));
      const flowTitle = sheet.kind === "global" ? "Regional & sweet / sour balances" : "Supply, trade & runs";
      const d3 = flowS.length ? chartDiv(420) : null; if (d3) view.appendChild(card(flowTitle, d3));
      const d4 = ratioS.length ? chartDiv(340) : null; if (d4) view.appendChild(card("Refinery utilisation", d4));
      // statistical
      const d5 = chartDiv(400); view.appendChild(card("Statistical — 12-month rolling mean vs actual", d5));
      const d6 = chartDiv(360); view.appendChild(card("Statistical — year-on-year change", d6));
      // seasonal
      const d7 = chartDiv(430); view.appendChild(card("Seasonal — " + primary.label + " by month, year overlay", d7));

      plot(d1, [balBar(x, ps.values, primary.label, ps.unit)], baseLayout(sheet.name + " — " + primary.label, unitLabel(ps.unit), { barmode: "relative" }, months));
      if (d2) plot(d2, balS.map((o, i) => { const s = seriesOf(sheet, o.group, o.label); return lineTrace(x, s.values, s.label, PAL[i % PAL.length], s.unit, 2); }).concat([lineTrace(x, ps.values, ps.label, "#ffffff", ps.unit, 2.5)]), baseLayout("Balance breakdown", unitLabel(ps.unit), {}, months));
      if (d3) plot(d3, flowS.map((o, i) => { const s = seriesOf(sheet, o.group, o.label); return lineTrace(x, s.values, s.label, PAL[i % PAL.length], s.unit, 2); }), baseLayout(flowTitle, "kb/d", {}, months));
      if (d4) plot(d4, ratioS.map((o, i) => { const s = seriesOf(sheet, o.group, o.label); return { x, y: s.values.map(v => v == null ? null : v * 100), name: s.label, type: "scatter", mode: "lines", line: { width: 2, color: PAL[i % PAL.length] }, connectgaps: false }; }), baseLayout("Refinery utilisation", "%", {}, months));
      plot(d5, [lineTrace(x, ps.values, "Actual", "#334155", ps.unit, 1.2), lineTrace(x, rolling(ps.values, 12), "12m rolling mean", C.amber, ps.unit, 3)], baseLayout("Rolling mean", unitLabel(ps.unit), {}, months));
      plot(d6, [balBar(x, yoy(ps.values), "YoY change", ps.unit)], baseLayout("Year-on-year change", unitLabel(ps.unit), {}, months));
      plot(d7, seasonalTraces(months, ps.values), baseLayout("Seasonal overlay", unitLabel(ps.unit), { hovermode: "closest" }, null));
    }

    function renderUS(sheet) {
      const months = sheet.months, x = months.map(m => m + "-01");
      const stk = seriesOf(sheet, "US", "Stocks (mb)");
      const bal = seriesOf(sheet, "US", "Balance");
      view.appendChild(card("Analysis — United States crude stocks & balances", sheet.analysis));
      view.appendChild(card("Overall table — US stocks, balance, supply & demand (recent & forecast)", overallTable(sheet, "US", sheet.order.filter(o => o.group === "US"), 9)));
      // 1) stocks & balance first
      const d1 = chartDiv(440); view.appendChild(card("Stocks & balance (first) — US crude stocks (mb) vs balance (kb/d)", d1));
      const d2 = chartDiv(420); view.appendChild(card("Supply, demand, runs & production", d2));
      const d3 = chartDiv(380); view.appendChild(card("Monthly stock change", d3));
      const d4 = chartDiv(430); view.appendChild(card("Seasonal — US crude stocks by month, year overlay", d4));
      const d5 = chartDiv(400); view.appendChild(card("Statistical — stocks 12-month rolling mean vs actual", d5));
      // PADD / Cushing detail
      const detHdr = el("div", { style: { display: "flex", gap: "10px", alignItems: "center", margin: "6px 0 4px" } });
      detHdr.appendChild(el("span", { style: { color: C.muted, fontSize: "12px" } }, "Regional detail:"));
      const gsel = el("select", { style: { background: C.card, color: C.text, border: "1px solid " + C.border, borderRadius: "6px", padding: "6px 12px", fontSize: "12px" } });
      sheet.groups.filter(g => g.code !== "US").forEach(g => { const o = document.createElement("option"); o.value = g.code; o.textContent = g.name; gsel.appendChild(o); });
      detHdr.appendChild(gsel);
      view.appendChild(detHdr);
      const dDetail = chartDiv(420); view.appendChild(card("Regional detail — stocks & balance", dDetail));

      plot(d1, [
        { x, y: stk.values, name: "Stocks (mb)", type: "scatter", mode: "lines", line: { width: 3, color: C.amber }, connectgaps: false, hovertemplate: "%{x|%Y-%m}<br>Stocks: %{y:,.1f} mb<extra></extra>" },
        Object.assign(balBar(x, bal.values, "Balance (kb/d)", "kb/d"), { yaxis: "y2", opacity: 0.55 }),
      ], baseLayout("US crude stocks & balance", "Stocks (mb)", { yaxis2: { title: { text: "Balance kb/d", font: { color: C.muted, size: 11 } }, overlaying: "y", side: "right", color: C.muted, gridcolor: "transparent", zeroline: true, zerolinecolor: "#334155" } }, months));
      const flow = ["Supply", "Demand", "Runs", "Production", "Imports"].map((l, i) => { const s = seriesOf(sheet, "US", l); return s ? lineTrace(x, s.values, l, PAL[i % PAL.length], "kb/d", 2) : null; }).filter(Boolean);
      plot(d2, flow, baseLayout("US supply / demand / runs", "kb/d", {}, months));
      const sc = seriesOf(sheet, "US", "Stock Change (mb)");
      if (sc) plot(d3, [balBar(x, sc.values, "Stock change", "mb")], baseLayout("US monthly stock change", "mb", {}, months));
      plot(d4, seasonalTraces(months, stk.values), baseLayout("US stocks seasonal", "mb", { hovermode: "closest" }, null));
      plot(d5, [lineTrace(x, stk.values, "Actual", "#334155", "mb", 1.2), lineTrace(x, rolling(stk.values, 12), "12m rolling mean", C.amber, "mb", 3)], baseLayout("US stocks rolling mean", "mb", {}, months));

      function drawDetail() {
        const g = gsel.value;
        const gs = seriesOf(sheet, g, "Stocks (mb)");
        const gb = seriesOf(sheet, g, "Balance");
        const gname = (sheet.groups.find(x => x.code === g) || {}).name || g;
        const tr = [];
        if (gs) tr.push({ x, y: gs.values, name: "Stocks (mb)", type: "scatter", mode: "lines", line: { width: 3, color: C.amber }, connectgaps: false });
        if (gb) tr.push(Object.assign(balBar(x, gb.values, "Balance (kb/d)", "kb/d"), { yaxis: "y2", opacity: 0.55 }));
        plot(dDetail, tr, baseLayout(gname + " — stocks & balance", "Stocks (mb)", { yaxis2: { title: { text: "Balance kb/d", font: { color: C.muted, size: 11 } }, overlaying: "y", side: "right", color: C.muted, gridcolor: "transparent" } }, months));
      }
      gsel.addEventListener("change", drawDetail);
      drawDetail();
    }

    function render(sheet) {
      view.innerHTML = "";
      if (sheet.kind === "us") renderUS(sheet); else renderRegionalOrGlobal(sheet);
    }

    sel.addEventListener("change", () => { const s = sheets.find(z => z.id === sel.value); if (s) loadPlotly(() => render(s)); });
    loadPlotly(() => render(sheets.find(s => s.id === defId) || sheets[0]));
  }


  // ─── PRODUCT STOCKS TAB (weekly hub stocks: /api/product_stocks) ───
  // Region dropdown (Fujairah / ARA / Japan / Singapore); each view shows a
  // retrospective, a latest-figures stats table, a combined history chart, and
  // per-product history / seasonal / YoY detail.
  async function renderPS(box) {
    box.innerHTML = '<div style="color:#94a3b8;padding:40px;text-align:center;">Loading Product Stocks…</div>';
    let blob;
    try {
      const r = await fetch("/api/product_stocks");
      if (!r.ok) throw new Error(await r.text());
      blob = await r.json();
    } catch (e) {
      box.innerHTML = `<div style="color:#ef4444;padding:40px;">Failed to load Product Stocks: ${e.message}</div>`;
      return;
    }
    box.innerHTML = "";
    const regions = blob.regions || [];
    if (!regions.length) { box.innerHTML = '<div style="color:#94a3b8;padding:40px;">No data.</div>'; return; }

    const PAL = ["#22c55e", "#f59e0b", "#c084fc", "#38bdf8", "#ef4444", "#f9a8d4", "#94a3b8", "#14b8a6", "#f97316"];
    const YRCOL = { 2019: "#3f4a63", 2020: "#475569", 2021: "#5b6577", 2022: "#64748b", 2023: "#0ea5e9", 2024: "#8b5cf6", 2025: "#ec4899", 2026: "#ffffff" };
    const unitLbl = u => u === "kt" ? "kt" : "mmbbl";
    const fmt1 = v => v == null ? "—" : v.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const signCol = v => v == null ? C.muted : v >= 0 ? C.green : C.red;
    const sfmt = v => v == null ? "—" : (v >= 0 ? "+" : "") + fmt1(v);

    function plot(div, traces, layout) { try { Plotly.newPlot(div, traces, layout, { responsive: true, displayModeBar: false }); } catch (e) { div.innerHTML = `<div style="color:#ef4444;padding:12px">${e.message}</div>`; } }
    function chartDiv(h) { return el("div", { style: { width: "100%", height: (h || 420) + "px" } }); }
    function baseLayout(title, yTitle, extra) {
      return Object.assign({
        title: { text: title, font: { color: C.text, size: 13 } },
        paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: C.muted, size: 11 }, showlegend: true,
        legend: { orientation: "h", y: -0.18, font: { size: 10 } },
        margin: { l: 64, r: 30, t: 40, b: 60 },
        yaxis: { title: { text: yTitle, font: { color: C.muted, size: 11 } }, gridcolor: "#1e293b", color: C.muted, separatethousands: true },
        xaxis: { gridcolor: "#1e293b", color: C.muted, tickfont: { size: 10 } },
      }, extra || {});
    }

    // stats over the last N points of a product
    function stats(p) {
      const pairs = p.dates.map((d, i) => [d, p.values[i]]).filter(x => x[1] != null);
      if (!pairs.length) return null;
      const n = pairs.length;
      const latest = pairs[n - 1][1], latestD = pairs[n - 1][0];
      const wow = n >= 2 ? latest - pairs[n - 2][1] : null;
      const w4 = n >= 5 ? latest - pairs[n - 5][1] : null;
      const yoy = n >= 53 ? latest - pairs[n - 53][1] : null;
      const last52 = pairs.slice(-52).map(x => x[1]);
      const lo = Math.min(...last52), hi = Math.max(...last52);
      const win5 = pairs.slice(-260).map(x => x[1]).sort((a, b) => a - b);
      const pctile = win5.length ? Math.round(100 * win5.filter(v => v <= latest).length / win5.length) : null;
      return { latest, latestD, wow, w4, yoy, lo, hi, pctile };
    }

    function seasonal(p) {
      const byYr = {};
      p.dates.forEach((d, i) => {
        if (p.values[i] == null) return;
        const y = +d.slice(0, 4);
        (byYr[y] = byYr[y] || []).push(["2000-" + d.slice(5), p.values[i]]);
      });
      return Object.keys(byYr).sort().map(y => ({
        x: byYr[y].map(z => z[0]), y: byYr[y].map(z => z[1]), name: y,
        type: "scatter", mode: "lines",
        line: { width: (+y >= 2026 ? 3 : +y >= 2024 ? 2 : 1.2), color: YRCOL[y] || "#64748b" },
        opacity: (+y >= 2023 ? 1 : 0.5),
      }));
    }
    function rolling(vals, w) {
      return vals.map((_, i) => { const s = vals.slice(Math.max(0, i - w + 1), i + 1).filter(v => v != null); return s.length ? s.reduce((a, b) => a + b, 0) / s.length : null; });
    }
    function yoyW(dates, vals) {
      return vals.map((v, i) => (i >= 52 && v != null && vals[i - 52] != null) ? v - vals[i - 52] : null);
    }

    // ── header + region dropdown ──
    const hdr = el("div", { style: { display: "flex", alignItems: "center", gap: "14px", marginBottom: "16px", flexWrap: "wrap" } });
    hdr.appendChild(el("div", { style: { fontSize: "20px", fontWeight: "800", color: C.amber } }, "🛢️ Product Stocks"));
    hdr.appendChild(el("span", { style: { color: C.muted, fontSize: "12px" } }, "Hub:"));
    const sel = el("select", { style: { background: C.card, color: C.text, border: "1px solid " + C.border, borderRadius: "6px", padding: "7px 14px", fontSize: "13px", fontWeight: "600" } });
    regions.forEach(rg => { const o = document.createElement("option"); o.value = rg.id; o.textContent = rg.name; sel.appendChild(o); });
    hdr.appendChild(sel);
    hdr.appendChild(el("span", { style: { color: C.muted, fontSize: "11px", marginLeft: "auto" } }, "Weekly refined-product stocks · as of " + (blob.as_of || "")));
    box.appendChild(hdr);

    const view = el("div");
    box.appendChild(view);

    function latestTable(rg) {
      let h = '<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:11.5px;color:' + C.text + '">';
      h += '<thead><tr style="background:#111a2e;color:' + C.amber + '">';
      ["Product", "Latest (" + unitLbl(rg.unit) + ")", "As of", "WoW", "4-wk Δ", "YoY", "52w low", "52w high", "5y %ile"].forEach((c, i) => {
        h += `<th style="padding:7px 9px;text-align:${i === 0 ? "left" : "right"};border:1px solid ${C.border}">${c}</th>`;
      });
      h += "</tr></thead><tbody>";
      rg.products.forEach((p, ri) => {
        const s = stats(p); if (!s) return;
        const bg = ri % 2 ? "#0f172a" : C.card;
        h += `<tr style="background:${bg}">`;
        h += `<td style="padding:5px 9px;border:1px solid ${C.border};text-align:left">${p.name}</td>`;
        h += `<td style="padding:5px 9px;border:1px solid ${C.border};text-align:right;font-weight:700">${fmt1(s.latest)}</td>`;
        h += `<td style="padding:5px 9px;border:1px solid ${C.border};text-align:right;color:${C.muted}">${s.latestD}</td>`;
        h += `<td style="padding:5px 9px;border:1px solid ${C.border};text-align:right;color:${signCol(s.wow)}">${sfmt(s.wow)}</td>`;
        h += `<td style="padding:5px 9px;border:1px solid ${C.border};text-align:right;color:${signCol(s.w4)}">${sfmt(s.w4)}</td>`;
        h += `<td style="padding:5px 9px;border:1px solid ${C.border};text-align:right;color:${signCol(s.yoy)}">${sfmt(s.yoy)}</td>`;
        h += `<td style="padding:5px 9px;border:1px solid ${C.border};text-align:right;color:${C.muted}">${fmt1(s.lo)}</td>`;
        h += `<td style="padding:5px 9px;border:1px solid ${C.border};text-align:right;color:${C.muted}">${fmt1(s.hi)}</td>`;
        h += `<td style="padding:5px 9px;border:1px solid ${C.border};text-align:right">${s.pctile == null ? "—" : s.pctile + "%"}</td>`;
        h += "</tr>";
      });
      h += "</tbody></table></div>";
      const w = el("div"); w.innerHTML = h; return w;
    }

    function render(rg) {
      view.innerHTML = "";
      const u = unitLbl(rg.unit);
      // retrospective analysis
      view.appendChild(card("Retrospective — " + rg.name + " product stocks", rg.analysis));
      // latest figures table
      view.appendChild(card("Latest figures & stats", latestTable(rg)));
      // combined history (all products)
      const dC = chartDiv(460);
      view.appendChild(card(rg.name + " product stocks history (weekly)", dC));
      plot(dC, rg.products.map((p, i) => ({
        x: p.dates, y: p.values, name: p.name, type: "scatter", mode: "lines",
        line: { width: 1.8, color: PAL[i % PAL.length] }, connectgaps: false,
        hovertemplate: "%{x}<br>" + p.name + ": %{y:,.1f} " + u + "<extra></extra>",
      })), baseLayout(rg.name + " — all products", u));

      // per-product detail selector
      const drow = el("div", { style: { display: "flex", alignItems: "center", gap: "10px", margin: "6px 0 12px" } });
      drow.appendChild(el("span", { style: { color: C.muted, fontSize: "12px" } }, "Product detail:"));
      const psel = el("select", { style: { background: C.card, color: C.text, border: "1px solid " + C.border, borderRadius: "6px", padding: "6px 12px", fontSize: "12px" } });
      rg.products.forEach(p => { const o = document.createElement("option"); o.value = p.name; o.textContent = p.name; psel.appendChild(o); });
      drow.appendChild(psel);
      view.appendChild(drow);

      const dHist = chartDiv(380); view.appendChild(card("Product history & 4-week average", dHist));
      const dSeas = chartDiv(400); view.appendChild(card("Seasonal — weekly stocks by year", dSeas));
      const dYoy = chartDiv(320); view.appendChild(card("Year-on-year change", dYoy));

      function drawDetail() {
        const p = rg.products.find(z => z.name === psel.value) || rg.products[0];
        plot(dHist, [
          { x: p.dates, y: p.values, name: p.name, type: "scatter", mode: "lines", line: { width: 1.5, color: "#334155" }, connectgaps: false },
          { x: p.dates, y: rolling(p.values, 4), name: "4-wk avg", type: "scatter", mode: "lines", line: { width: 2.5, color: C.amber }, connectgaps: false },
        ], baseLayout(p.name + " — history", u));
        plot(dSeas, seasonal(p), baseLayout(p.name + " — seasonal (year overlay)", u, { xaxis: { tickformat: "%b", gridcolor: "#1e293b", color: C.muted }, hovermode: "closest" }));
        plot(dYoy, [{ x: p.dates, y: yoyW(p.dates, p.values), name: "YoY Δ", type: "bar", marker: { color: yoyW(p.dates, p.values).map(v => v == null ? "#334155" : v >= 0 ? C.green : C.red) } }], baseLayout(p.name + " — YoY change", u));
      }
      psel.addEventListener("change", drawDetail);
      drawDetail();
    }

    sel.addEventListener("change", () => { const rg = regions.find(z => z.id === sel.value); if (rg) loadPlotly(() => render(rg)); });
    loadPlotly(() => render(regions[0]));
  }


  // ─── VOLUME & OI TRACKER TAB (/api/voloi + live /api/voloi/live + COT) ───
  // 3-min volume anomaly flags vs a rolling baseline, cumulative signed-volume
  // (buying/selling pressure), daily OI regime (ΔOI vs Δprice), and a
  // CFTC-COT correlation that produces a potential-direction read.
  async function renderVOLOI(box) {
    box.innerHTML = '<div style="color:#94a3b8;padding:40px;text-align:center;">Loading Volume & OI Tracker…</div>';
    let base, cot = null;
    try {
      const r = await fetch("/api/voloi");
      if (!r.ok) throw new Error(await r.text());
      base = await r.json();
    } catch (e) {
      box.innerHTML = `<div style="color:#ef4444;padding:40px;">Failed to load Volume & OI: ${e.message}</div>`;
      return;
    }
    try { const rc = await fetch("/api/cot/net-positioning"); if (rc.ok) cot = await rc.json(); } catch (e) { cot = null; }

    box.innerHTML = "";
    const COMMS = ["Brent", "RBOB", "Gasoil"];
    const CONTRACTS = { Brent: ["CO1", "CO2"], RBOB: ["XB1", "XB2"], Gasoil: ["QS1", "QS2"] };
    const Z_ELEV = 2, Z_EXTREME = 3, BASE_WIN = 100, SESSION_BARS = 700;

    const num = v => (typeof v === "number" && isFinite(v)) ? v : null;
    const fmt = (v, d) => v == null ? "—" : v.toLocaleString(undefined, { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 });
    const sgn = (v, d) => v == null ? "—" : (v >= 0 ? "+" : "") + fmt(v, d);
    const sCol = v => v == null ? C.muted : v > 0 ? C.green : v < 0 ? C.red : C.muted;

    function plot(div, traces, layout) { try { Plotly.newPlot(div, traces, layout, { responsive: true, displayModeBar: false }); } catch (e) { div.innerHTML = `<div style="color:#ef4444;padding:12px">${e.message}</div>`; } }
    function chartDiv(h) { return el("div", { style: { width: "100%", height: (h || 380) + "px" } }); }
    function baseLayout(title, extra) {
      return Object.assign({
        title: { text: title, font: { color: C.text, size: 13 } },
        paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: C.muted, size: 11 }, showlegend: true,
        legend: { orientation: "h", y: -0.2, font: { size: 10 } },
        margin: { l: 60, r: 60, t: 40, b: 55 },
        xaxis: { gridcolor: "#1e293b", color: C.muted, tickfont: { size: 10 } },
        yaxis: { gridcolor: "#1e293b", color: C.muted },
      }, extra || {});
    }

    // merge live tail bars onto the shipped baseline (append newer timestamps)
    function mergeLive(baseObj, live) {
      const out = JSON.parse(JSON.stringify(baseObj));
      if (!live || !live.data) return out;
      const ld = live.data;
      if (ld.intraday) {
        Object.keys(ld.intraday).forEach(code => {
          const b = out.intraday[code], l = ld.intraday[code];
          if (!b) { out.intraday[code] = l; return; }
          const last = b.t[b.t.length - 1];
          l.t.forEach((ts, i) => { if (ts > last) { b.t.push(ts); b.p.push(l.p[i]); b.v.push(l.v[i]); } });
          // update the final (in-progress) bar if same timestamp
          const li = l.t.indexOf(last);
          if (li >= 0) { b.p[b.p.length - 1] = l.p[li]; b.v[b.v.length - 1] = l.v[li]; }
        });
      }
      if (ld.oi) out.oi = Object.assign(out.oi, ld.oi);
      return out;
    }

    // rolling volume z-score + direction flags for a contract's bars
    function anomalies(series) {
      const t = series.t, p = series.p, v = series.v, n = v.length;
      const z = new Array(n).fill(null), flag = new Array(n).fill(0), dir = new Array(n).fill(0);
      for (let i = 0; i < n; i++) {
        const s = v.slice(Math.max(0, i - BASE_WIN), i).filter(x => x != null);
        if (s.length >= 20) {
          const m = s.reduce((a, b) => a + b, 0) / s.length;
          const sd = Math.sqrt(s.reduce((a, b) => a + (b - m) * (b - m), 0) / s.length) || 1;
          z[i] = (v[i] - m) / sd;
          flag[i] = Math.abs(z[i]) >= Z_EXTREME ? 2 : Math.abs(z[i]) >= Z_ELEV ? 1 : 0;
          const dp = i > 0 && p[i] != null && p[i - 1] != null ? p[i] - p[i - 1] : 0;
          dir[i] = dp > 0 ? 1 : dp < 0 ? -1 : 0;
        }
      }
      return { z, flag, dir };
    }
    function sessionOf(ts) { return ts.slice(0, 10); }

    // ── header ──
    const hdr = el("div", { style: { display: "flex", alignItems: "center", gap: "14px", marginBottom: "14px", flexWrap: "wrap" } });
    hdr.appendChild(el("div", { style: { fontSize: "20px", fontWeight: "800", color: C.amber } }, "📊 Volume & OI Tracker"));
    hdr.appendChild(el("span", { style: { color: C.muted, fontSize: "12px" } }, "Contract:"));
    const csel = el("select", { style: { background: C.card, color: C.text, border: "1px solid " + C.border, borderRadius: "6px", padding: "7px 12px", fontSize: "13px", fontWeight: "600" } });
    COMMS.forEach(cm => CONTRACTS[cm].forEach(code => { const o = document.createElement("option"); o.value = code; o.textContent = (base.intraday[code] || {}).label || code; csel.appendChild(o); }));
    hdr.appendChild(csel);
    const liveBadge = el("span", { style: { fontSize: "11px", fontWeight: "700", padding: "3px 9px", borderRadius: "10px", background: "rgba(148,163,184,0.15)", color: C.muted } }, "○ baseline");
    hdr.appendChild(liveBadge);
    hdr.appendChild(el("span", { style: { color: C.muted, fontSize: "11px", marginLeft: "auto" } }, "3-min bars · anomaly z-score vs " + BASE_WIN + "-bar baseline · not investment advice"));
    box.appendChild(hdr);

    const view = el("div");
    box.appendChild(view);

    let merged = base;

    // ── COT spec signal (single CFTC Managed-Money series loaded on the platform) ──
    function cotSignal() {
      if (!cot || !cot.series || !cot.series.length) return null;
      const s = cot.series, key = "Managed Money";
      const vals = s.map(r => num(r[key])).filter(x => x != null);
      if (vals.length < 6) return null;
      const latest = vals[vals.length - 1];
      const w1 = latest - vals[vals.length - 2];
      const w4 = vals.length >= 5 ? latest - vals[vals.length - 5] : null;
      const win = vals.slice(-104);
      const lo = Math.min(...win), hi = Math.max(...win);
      const pctile = Math.round(100 * win.filter(x => x <= latest).length / win.length);
      const date = s[s.length - 1].date;
      return { latest, w1, w4, pctile, lo, hi, date };
    }

    function oiRegime(commodity) {
      const oi = merged.oi[commodity]; if (!oi) return null;
      const c = oi.contracts[0]; // front contract
      const dates = c.dates, px = c.px, oiv = c.oi;
      // last valid OI (top rows lag / may be null)
      let li = oiv.length - 1; while (li >= 0 && oiv[li] == null) li--;
      let pi = li - 1; while (pi >= 0 && oiv[pi] == null) pi--;
      if (li < 1 || pi < 0) return { oi, c, rows: [] };
      const rows = [];
      let lastIdx = null;
      for (let i = 0; i < oiv.length; i++) {
        if (oiv[i] == null || px[i] == null) continue;
        if (lastIdx != null) {
          const dOI = oiv[i] - oiv[lastIdx], dP = px[i] - px[lastIdx];
          const prevOI = oiv[lastIdx];
          let reg = "—";
          // huge one-day OI jump on the generic front = contract roll, not flow
          if (prevOI && Math.abs(dOI) > 0.4 * prevOI) reg = "Contract roll";
          else if (dOI > 0 && dP > 0) reg = "New longs";
          else if (dOI > 0 && dP < 0) reg = "New shorts";
          else if (dOI < 0 && dP > 0) reg = "Short covering";
          else if (dOI < 0 && dP < 0) reg = "Long liquidation";
          rows.push({ date: dates[i], px: px[i], oi: oiv[i], dOI, dP, reg });
        }
        lastIdx = i;
      }
      return { oi, c, rows, latest: rows[rows.length - 1] };
    }

    function directionCard(commodity, code, flow) {
      const cs = cotSignal(), reg = oiRegime(commodity);
      let score = 0; const notes = [];
      if (cs) {
        const t = cs.w4 != null ? cs.w4 : cs.w1;
        if (t > 0) { score += 1; notes.push(`CFTC Managed-Money net ${sgn(cs.latest, 0)} and building (${sgn(t, 0)} over 4w, ${cs.pctile}%ile) — spec longs adding, bullish tilt.`); }
        else if (t < 0) { score -= 1; notes.push(`CFTC Managed-Money net ${sgn(cs.latest, 0)} and trimming (${sgn(t, 0)} over 4w, ${cs.pctile}%ile) — spec longs cutting, bearish tilt.`); }
        else notes.push(`CFTC Managed-Money net flat at ${fmt(cs.latest, 0)}.`);
      }
      if (reg && reg.latest) {
        const r = reg.latest;
        const m = { "New longs": 1, "Short covering": 0.5, "New shorts": -1, "Long liquidation": -0.5 }[r.reg] || 0;
        score += m;
        notes.push(`Latest OI regime: <b>${r.reg}</b> (ΔOI ${sgn(r.dOI, 0)}, Δprice ${sgn(r.dP, 2)}) — ${m > 0 ? "supportive" : m < 0 ? "negative" : "neutral"}.`);
      }
      if (flow != null) {
        if (flow > 0) { score += 1; notes.push(`Intraday signed volume net <b>buying</b> this session (${sgn(flow, 0)} lots) — demand at the offer.`); }
        else if (flow < 0) { score -= 1; notes.push(`Intraday signed volume net <b>selling</b> this session (${sgn(flow, 0)} lots) — supply at the bid.`); }
      }
      const lean = score >= 1 ? "BULLISH" : score <= -1 ? "BEARISH" : "MIXED / NEUTRAL";
      const col = score >= 1 ? C.green : score <= -1 ? C.red : C.gold;
      const wrap = el("div");
      wrap.appendChild(el("div", { style: { fontSize: "17px", fontWeight: "800", color: col, marginBottom: "8px" } }, `Potential direction — ${commodity}: ${lean}  (score ${sgn(score, 1)})`));
      const ul = el("div", { style: { color: C.text, fontSize: "12.5px", lineHeight: "1.7" } });
      ul.innerHTML = notes.map(n => "• " + n).join("<br>");
      wrap.appendChild(ul);
      wrap.appendChild(el("div", { style: { color: C.muted, fontSize: "10.5px", marginTop: "8px" } }, "Blend of CFTC spec positioning + daily OI regime + intraday volume flow. Directional lean, not investment advice."));
      return wrap;
    }

    function render(code) {
      view.innerHTML = "";
      const s = merged.intraday[code];
      if (!s) { view.appendChild(card("", "No data for " + code)); return; }
      const commodity = s.commodity, u = s.unit;
      const an = anomalies(s);
      const n = s.t.length;
      const start = Math.max(0, n - SESSION_BARS);
      const idx = []; for (let i = start; i < n; i++) idx.push(i);
      const curSession = sessionOf(s.t[n - 1]);

      // session flow (signed volume) + stats
      let flow = 0, sessVol = 0, nElev = 0, nExt = 0, maxV = 0, maxVt = null;
      for (let i = 0; i < n; i++) {
        if (sessionOf(s.t[i]) === curSession) {
          sessVol += s.v[i] || 0;
          if (an.dir[i]) flow += (s.v[i] || 0) * an.dir[i];
          if (an.flag[i] === 1) nElev++; if (an.flag[i] === 2) nExt++;
          if ((s.v[i] || 0) > maxV) { maxV = s.v[i]; maxVt = s.t[i]; }
        }
      }
      // direction / COT card first
      view.appendChild(card("Direction read", directionCard(commodity, code, flow)));

      // stat row
      const stats = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(130px,1fr))", gap: "8px" } });
      const sc = (l, val, c) => { const b = el("div", { style: { background: C.card, border: "1px solid " + C.border, borderRadius: "8px", padding: "10px 12px", textAlign: "center" } }); b.appendChild(el("div", { style: { fontSize: "10px", color: C.muted, marginBottom: "3px" } }, l)); b.appendChild(el("div", { style: { fontSize: "16px", fontWeight: "700", color: c || C.text } }, val)); return b; };
      stats.appendChild(sc("Latest (" + u + ")", fmt(s.p[n - 1], 2)));
      stats.appendChild(sc("Session volume", fmt(sessVol, 0)));
      stats.appendChild(sc("Net signed vol", sgn(flow, 0), sCol(flow)));
      stats.appendChild(sc("Elevated bars", String(nElev), nElev ? C.gold : C.muted));
      stats.appendChild(sc("Extreme bars", String(nExt), nExt ? C.red : C.muted));
      stats.appendChild(sc("Biggest bar", fmt(maxV, 0) + (maxVt ? " @" + maxVt.slice(11) : "")));
      view.appendChild(card("Session snapshot — " + curSession + " (" + s.label + ")", stats));

      // volume anomaly chart (recent session window)
      const barCol = idx.map(i => an.flag[i] === 2 ? C.red : an.flag[i] === 1 ? C.gold : "#3b4d6b");
      const dV = chartDiv(400);
      view.appendChild(card("3-min volume with anomaly flags + price", dV));
      plot(dV, [
        { x: idx.map(i => s.t[i]), y: idx.map(i => s.v[i]), name: "Volume", type: "bar", marker: { color: barCol }, hovertemplate: "%{x}<br>vol %{y:,.0f}<extra></extra>" },
        { x: idx.map(i => s.t[i]), y: idx.map(i => s.p[i]), name: "Price (" + u + ")", type: "scatter", mode: "lines", line: { color: "#38bdf8", width: 1.5 }, yaxis: "y2", hovertemplate: "%{x}<br>px %{y:,.2f}<extra></extra>" },
      ], baseLayout(s.label + " — volume & price (last " + idx.length + " bars)", {
        yaxis: { title: { text: "Volume (lots)", font: { size: 10, color: C.muted } }, gridcolor: "#1e293b", color: C.muted },
        yaxis2: { title: { text: u, font: { size: 10, color: C.muted } }, overlaying: "y", side: "right", color: "#38bdf8", showgrid: false },
      }));

      // cumulative signed volume (buying/selling pressure) vs price
      const cum = []; let acc = 0;
      idx.forEach(i => { if (an.dir[i]) acc += (s.v[i] || 0) * an.dir[i]; cum.push(acc); });
      const dOBV = chartDiv(320);
      view.appendChild(card("Cumulative signed volume (buying vs selling pressure) vs price", dOBV));
      plot(dOBV, [
        { x: idx.map(i => s.t[i]), y: cum, name: "Cum. signed vol", type: "scatter", mode: "lines", line: { color: C.amber, width: 2 }, fill: "tozeroy", fillcolor: "rgba(245,158,11,0.10)" },
        { x: idx.map(i => s.t[i]), y: idx.map(i => s.p[i]), name: "Price", type: "scatter", mode: "lines", line: { color: "#38bdf8", width: 1.4 }, yaxis: "y2" },
      ], baseLayout("Pressure vs price — divergence flags absorption/exhaustion", {
        yaxis: { title: { text: "Σ signed vol", font: { size: 10, color: C.muted } }, gridcolor: "#1e293b", color: C.muted, zeroline: true, zerolinecolor: "#334155" },
        yaxis2: { title: { text: u, font: { size: 10, color: C.muted } }, overlaying: "y", side: "right", color: "#38bdf8", showgrid: false },
      }));

      // anomaly table (most recent flagged bars)
      const flagged = [];
      for (let i = n - 1; i >= 0 && flagged.length < 25; i--) if (an.flag[i]) flagged.push(i);
      let h = '<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:11.5px;color:' + C.text + '">';
      h += '<thead><tr style="background:#111a2e;color:' + C.amber + '">';
      ["Time", "Price", "Δpx", "Volume", "×avg", "z", "Flag", "Flow"].forEach((c, i) => { h += `<th style="padding:6px 8px;text-align:${i === 0 ? "left" : "right"};border:1px solid ${C.border}">${c}</th>`; });
      h += "</tr></thead><tbody>";
      flagged.forEach((i, ri) => {
        const bg = ri % 2 ? "#0f172a" : C.card;
        const dp = i > 0 ? s.p[i] - s.p[i - 1] : null;
        const mult = an.z[i] != null ? (1 + an.z[i] * 0) : null;
        const s2 = s.v.slice(Math.max(0, i - BASE_WIN), i).filter(x => x != null);
        const avg = s2.length ? s2.reduce((a, b) => a + b, 0) / s2.length : null;
        const x = avg ? s.v[i] / avg : null;
        const fl = an.flag[i] === 2 ? "EXTREME" : "Elevated";
        const flc = an.flag[i] === 2 ? C.red : C.gold;
        const flow = an.dir[i] > 0 ? "BUY" : an.dir[i] < 0 ? "SELL" : "—";
        h += `<tr style="background:${bg}">`;
        h += `<td style="padding:4px 8px;border:1px solid ${C.border};text-align:left">${s.t[i].replace("T", " ")}</td>`;
        h += `<td style="padding:4px 8px;border:1px solid ${C.border};text-align:right">${fmt(s.p[i], 2)}</td>`;
        h += `<td style="padding:4px 8px;border:1px solid ${C.border};text-align:right;color:${sCol(dp)}">${sgn(dp, 2)}</td>`;
        h += `<td style="padding:4px 8px;border:1px solid ${C.border};text-align:right;font-weight:700">${fmt(s.v[i], 0)}</td>`;
        h += `<td style="padding:4px 8px;border:1px solid ${C.border};text-align:right">${x == null ? "—" : x.toFixed(1) + "×"}</td>`;
        h += `<td style="padding:4px 8px;border:1px solid ${C.border};text-align:right">${an.z[i] == null ? "—" : an.z[i].toFixed(1)}</td>`;
        h += `<td style="padding:4px 8px;border:1px solid ${C.border};text-align:right;color:${flc};font-weight:700">${fl}</td>`;
        h += `<td style="padding:4px 8px;border:1px solid ${C.border};text-align:right;color:${an.dir[i] > 0 ? C.green : an.dir[i] < 0 ? C.red : C.muted}">${flow}</td>`;
        h += "</tr>";
      });
      h += "</tbody></table></div>";
      const tw = el("div"); tw.innerHTML = h;
      view.appendChild(card("Recent volume anomalies (z ≥ " + Z_ELEV + ")", flagged.length ? tw : "No anomalies in the recent window."));

      // ── Open Interest ──
      const reg = oiRegime(commodity);
      if (reg && reg.oi) {
        const oi = reg.oi, cts = oi.contracts;
        const dOI = chartDiv(360);
        view.appendChild(card(commodity + " open interest & price (daily, 6 months)", dOI));
        const traces = [];
        const oiCol = ["#22c55e", "#8b5cf6"];
        cts.forEach((c, k) => {
          traces.push({ x: c.dates, y: c.oi, name: c.code + " OI", type: "scatter", mode: "lines", line: { color: oiCol[k], width: 2 }, connectgaps: false });
        });
        traces.push({ x: cts[0].dates, y: cts[0].px, name: cts[0].code + " price", type: "scatter", mode: "lines", line: { color: "#38bdf8", width: 1.4 }, yaxis: "y2", connectgaps: false });
        plot(dOI, traces, baseLayout(commodity + " — OI (front/2nd) vs front price", {
          yaxis: { title: { text: "Open interest", font: { size: 10, color: C.muted } }, gridcolor: "#1e293b", color: C.muted },
          yaxis2: { title: { text: oi.unit, font: { size: 10, color: C.muted } }, overlaying: "y", side: "right", color: "#38bdf8", showgrid: false },
        }));

        // OI regime table (recent 15 days)
        const rr = reg.rows.slice(-15).reverse();
        let oh = '<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:11.5px;color:' + C.text + '">';
        oh += '<thead><tr style="background:#111a2e;color:' + C.amber + '">';
        ["Date", "Price", "ΔPrice", "OI", "ΔOI", "Regime"].forEach((c, i) => { oh += `<th style="padding:6px 8px;text-align:${i === 0 ? "left" : "right"};border:1px solid ${C.border}">${c}</th>`; });
        oh += "</tr></thead><tbody>";
        const regCol = { "New longs": C.green, "Short covering": "#4ade80", "New shorts": C.red, "Long liquidation": "#f87171" };
        rr.forEach((r, ri) => {
          const bg = ri % 2 ? "#0f172a" : C.card;
          oh += `<tr style="background:${bg}">`;
          oh += `<td style="padding:4px 8px;border:1px solid ${C.border};text-align:left">${r.date}</td>`;
          oh += `<td style="padding:4px 8px;border:1px solid ${C.border};text-align:right">${fmt(r.px, 2)}</td>`;
          oh += `<td style="padding:4px 8px;border:1px solid ${C.border};text-align:right;color:${sCol(r.dP)}">${sgn(r.dP, 2)}</td>`;
          oh += `<td style="padding:4px 8px;border:1px solid ${C.border};text-align:right">${fmt(r.oi, 0)}</td>`;
          oh += `<td style="padding:4px 8px;border:1px solid ${C.border};text-align:right;color:${sCol(r.dOI)}">${sgn(r.dOI, 0)}</td>`;
          oh += `<td style="padding:4px 8px;border:1px solid ${C.border};text-align:right;color:${regCol[r.reg] || C.muted};font-weight:700">${r.reg}</td>`;
          oh += "</tr>";
        });
        oh += "</tbody></table></div>";
        const ow = el("div"); ow.innerHTML = oh;
        view.appendChild(card("OI regime — ΔOI vs Δprice (front contract, last 15 days)", ow));
      }
    }

    // live polling — 3-min volume/OI pushes ~every 50s (vs prices every 5s), so a
    // single skipped push (transient Excel COM error) can leave the feed >120s old.
    // Always merge the newer live bars (they are real, strictly-newer 3-min bars);
    // staleness only drives the badge. Revert to baseline only when there is no
    // live data at all — never throw away bars just because the last push lagged.
    async function refreshLive() {
      try {
        const r = await fetch("/api/voloi/live");
        if (!r.ok) return;
        const live = await r.json();
        const hasData = live && live.data && live.data.intraday && Object.keys(live.data.intraday).length;
        if (hasData) {
          merged = mergeLive(base, live);
          const ss = live.stale_seconds;
          if (ss != null && ss < 600) {
            liveBadge.textContent = "● LIVE";
            liveBadge.style.background = "rgba(34,197,94,0.18)"; liveBadge.style.color = C.green;
          } else {
            const mins = ss != null ? Math.round(ss / 60) : null;
            liveBadge.textContent = mins != null ? ("◐ live · " + mins + "m ago") : "◐ live · delayed";
            liveBadge.style.background = "rgba(245,158,11,0.15)"; liveBadge.style.color = C.gold;
          }
        } else {
          merged = base;
          liveBadge.textContent = "○ baseline";
          liveBadge.style.background = "rgba(148,163,184,0.15)"; liveBadge.style.color = C.muted;
        }
      } catch (e) { /* keep last merged */ }
    }

    csel.addEventListener("change", () => loadPlotly(() => render(csel.value)));
    await refreshLive();
    loadPlotly(() => render(csel.value));
    setInterval(async () => { await refreshLive(); loadPlotly(() => render(csel.value)); }, 20000);
  }


  // ─── GENSCAPE EUROPE TAB ───
  async function renderGspeEurope(box) {
    box.innerHTML = "";
    const hdr = el("div", { style: { display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px", marginBottom: "15px" } });
    hdr.appendChild(el("h2", { style: { color: C.amber, margin: 0, fontSize: "20px" } }, "🇪🇺 Genscape Europe & UK — Refinery Turnaround Tracker"));

    const controls = el("div", { style: { display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" } });
    const lastPulledSpan = el("span", { style: { color: C.muted, fontSize: "11px" } }, "");

    // Region selector
    const regionSel = el("select", { style: { background: C.card, color: C.text, border: `1px solid ${C.border}`, padding: "6px 10px", borderRadius: "4px", fontSize: "12px" } });
    ["All EU+UK", "Europe", "United Kingdom"].forEach(r => {
      const o = document.createElement("option"); o.value = r; o.textContent = r; regionSel.appendChild(o);
    });
    controls.appendChild(regionSel);

    // Refresh button
    const refreshBtn = el("button", { style: { background: "#10b981", color: "#fff", border: "none", padding: "6px 14px", borderRadius: "4px", cursor: "pointer", fontSize: "12px", fontWeight: "600" } }, "↻ REFRESH EU (3d)");
    controls.appendChild(refreshBtn);
    const loadBtn = el("button", { style: { background: C.amber, color: "#000", border: "none", padding: "6px 14px", borderRadius: "4px", cursor: "pointer", fontSize: "12px", fontWeight: "600" } }, "LOAD DATA");
    controls.appendChild(loadBtn);
    controls.appendChild(lastPulledSpan);
    hdr.appendChild(controls);
    box.appendChild(hdr);

    // EU Briefing section
    const euBriefingBox = el("div", { style: { marginBottom: "20px" } });
    box.appendChild(euBriefingBox);

    const contentBox = el("div");
    box.appendChild(contentBox);

    let euData = null;

    function renderEuBriefing(data) {
      euBriefingBox.innerHTML = "";
      const panel = el("div", { style: { background: "linear-gradient(135deg, #0f172a 0%, #1a1f3a 100%)", border: "1px solid #60a5fa33", borderRadius: "12px", padding: "20px 24px", marginBottom: "8px" } });
      const bHdr = el("div", { style: { display: "flex", alignItems: "center", gap: "10px", marginBottom: "14px" } });
      bHdr.appendChild(el("span", { style: { fontSize: "15px", fontWeight: "800", color: "#60a5fa", letterSpacing: "0.02em" } }, "📋 TRADER BRIEFING — Europe & UK Refineries"));
      if (data.date_range) bHdr.appendChild(el("span", { style: { fontSize: "11px", color: "#64748b", marginLeft: "auto" } }, "Data: " + data.date_range.min + " to " + data.date_range.max));
      panel.appendChild(bHdr);

      const bullets = [];
      // Total offline
      const euCap = data.latest_by_country?.["Europe"] || 0;
      const ukCap = data.latest_by_country?.["United Kingdom"] || 0;
      const totalCap = euCap + ukCap;
      bullets.push(`Total EU+UK offline: ${totalCap.toLocaleString()} kb/d (Europe: ${euCap.toLocaleString()}, UK: ${ukCap.toLocaleString()})`);

      // By category
      if (data.latest_by_category) {
        const cats = Object.entries(data.latest_by_category).sort((a, b) => b[1] - a[1]).slice(0, 5);
        bullets.push("By unit type — " + cats.map(([c, v]) => `${c}: ${v.toLocaleString()} kb/d`).join(" | "));
      }

      // Offline facilities count
      const facs = data.facility_offline || [];
      if (facs.length > 0) {
        bullets.push(`Currently ${facs.length} units offline`);
        // Top outages
        const topFacs = facs.slice(0, 5);
        bullets.push("Largest outages:");
        topFacs.forEach(f => {
          const otype = f.outageType || "N/A";
          bullets.push(`  • ${f.facility} — ${f.category} ${f.unit} (${f.capacity} kb/d, ${otype})`);
        });
      }

      // Unplanned
      if (facs.length > 0) {
        const unplanned = facs.filter(f => f.outageType && (f.outageType.toLowerCase().includes("unplanned") || f.outageType.toLowerCase().includes("force")));
        if (unplanned.length > 0) {
          const unplCap = unplanned.reduce((s, f) => s + (f.capacity || 0), 0);
          bullets.push(`Unplanned/forced outages: ${unplanned.length} units, ${unplCap.toLocaleString()} kb/d offline`);
        }
      }

      // Summary badges
      const badges = el("div", { style: { display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "14px" } });
      const badge = (label, val, color) => {
        const b = el("div", { style: { background: color + "18", border: "1px solid " + color + "44", borderRadius: "8px", padding: "8px 14px", display: "flex", flexDirection: "column", alignItems: "center" } });
        b.appendChild(el("span", { style: { fontSize: "16px", fontWeight: "800", color: color } }, val));
        b.appendChild(el("span", { style: { fontSize: "9px", color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", marginTop: "2px" } }, label));
        return b;
      };
      badges.appendChild(badge("EU Offline", euCap.toLocaleString() + " kb/d", "#ef4444"));
      badges.appendChild(badge("UK Offline", ukCap.toLocaleString() + " kb/d", "#f59e0b"));
      badges.appendChild(badge("Total", totalCap.toLocaleString() + " kb/d", "#60a5fa"));
      if (facs.length > 0) badges.appendChild(badge("Units Offline", String(facs.length), "#a78bfa"));
      panel.appendChild(badges);

      // Bullet list
      const list = el("div", { style: { display: "flex", flexDirection: "column", gap: "5px" } });
      bullets.forEach(b => {
        const isSub = b.startsWith("  •");
        const item = el("div", { style: { fontSize: "12px", color: isSub ? "#cbd5e1" : "#e2e8f0", paddingLeft: isSub ? "16px" : "0", lineHeight: "1.5", fontWeight: isSub ? "400" : "500" } });
        if (!isSub && !b.startsWith("Largest")) {
          item.textContent = "• " + b;
        } else if (b.startsWith("Largest")) {
          item.innerHTML = "<strong style='color:#f59e0b'>• " + b + "</strong>";
        } else {
          item.textContent = b;
        }
        list.appendChild(item);
      });
      panel.appendChild(list);
      euBriefingBox.appendChild(panel);
    }

    async function loadData() {
      contentBox.innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8;">Loading Europe/UK data...</div>';
      try {
        const [analytics, lastPulled] = await Promise.all([
          fetch("/api/genscape/europe_analytics").then(r => { if(!r.ok) throw new Error(r.statusText); return r.json(); }),
          fetch("/api/genscape/last_pulled").then(r => r.json()),
        ]);
        euData = analytics;
        if (lastPulled.last_pulled) {
          const d = new Date(lastPulled.last_pulled);
          lastPulledSpan.textContent = `Last pulled: ${d.toLocaleDateString()} ${d.toLocaleTimeString()}`;
        }
        renderEuBriefing(euData);
        renderEuContent(contentBox, euData, regionSel.value);
      } catch(e) {
        contentBox.innerHTML = `<div style="color:${C.red};padding:20px;">Error loading data: ${e.message}</div>`;
      }
    }

    regionSel.addEventListener("change", () => {
      if (euData) renderEuContent(contentBox, euData, regionSel.value);
    });

    refreshBtn.addEventListener("click", async () => {
      refreshBtn.textContent = "Refreshing..."; refreshBtn.disabled = true;
      try {
        const r = await fetch("/api/genscape/refresh_europe?lookback_days=3", { method: "POST" });
        if (!r.ok) throw new Error(await r.text());
        const res = await r.json();
        refreshBtn.textContent = `✓ ${res.new_records} rows`;
        await loadData();
      } catch(e) {
        refreshBtn.textContent = "Error!";
        contentBox.innerHTML += `<div style="color:${C.red};padding:10px;">Refresh error: ${e.message}</div>`;
      } finally {
        setTimeout(() => { refreshBtn.textContent = "↻ REFRESH EU (3d)"; refreshBtn.disabled = false; }, 3000);
      }
    });

    loadBtn.addEventListener("click", loadData);
    loadData();
  }

  function renderEuContent(container, data, regionFilter) {
    container.innerHTML = "";
    const isAll = regionFilter === "All EU+UK";
    const countries = isAll ? data.countries : [regionFilter];

    // Section helper
    function euSection(title, subtitle) {
      const s = el("div", { style: { marginBottom: "25px" } });
      s.appendChild(el("h3", { style: { color: C.amber, margin: "0 0 4px 0", fontSize: "16px", borderBottom: `1px solid ${C.border}`, paddingBottom: "6px" } }, title));
      if (subtitle) s.appendChild(el("p", { style: { color: C.muted, fontSize: "12px", margin: "0 0 10px 0" } }, subtitle));
      return s;
    }

    // ── Summary Cards ──
    const cardsSection = euSection("Summary — Latest Day (" + data.date_range.max + ")", `Data: ${data.date_range.min} to ${data.date_range.max}`);
    const cardsRow = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "10px", marginBottom: "15px" } });

    // Country cards
    countries.forEach(c => {
      const stats = data.country_stats[c] || {};
      const offKbd = stats.latest_offline_kbd || 0;
      const card = el("div", { style: { background: C.card, border: `1px solid ${C.border}`, borderRadius: "6px", padding: "12px" } });
      card.innerHTML = `
        <div style="color:${C.muted};font-size:11px;margin-bottom:4px;">${c}</div>
        <div style="color:${C.red};font-size:22px;font-weight:700;">${offKbd.toFixed(0)} <span style="font-size:12px;color:${C.muted}">kbd offline</span></div>
        <div style="color:${C.muted};font-size:11px;margin-top:4px;">${stats.total_facilities || 0} refineries · ${stats.total_units || 0} units</div>
      `;
      cardsRow.appendChild(card);
    });

    // Category cards
    const catEntries = Object.entries(data.latest_by_category).sort((a,b) => b[1] - a[1]);
    catEntries.forEach(([cat, val]) => {
      const card = el("div", { style: { background: C.card, border: `1px solid ${C.border}`, borderRadius: "6px", padding: "12px" } });
      card.innerHTML = `
        <div style="color:${C.muted};font-size:11px;margin-bottom:4px;">${cat}</div>
        <div style="color:#f59e0b;font-size:20px;font-weight:700;">${val.toFixed(0)} <span style="font-size:12px;color:${C.muted}">kbd</span></div>
      `;
      cardsRow.appendChild(card);
    });
    cardsSection.appendChild(cardsRow);
    container.appendChild(cardsSection);

    // ── Charts ──
    const chartColors = ["#f59e0b", "#ef4444", "#3b82f6", "#10b981", "#8b5cf6", "#ec4899", "#06b6d4", "#f97316"];
    const catColors = { CDU: "#ef4444", FCC: "#f59e0b", HCU: "#3b82f6", VDU: "#10b981", COK: "#8b5cf6", RFM: "#ec4899", HT: "#06b6d4", ALK: "#f97316" };

    function plotDiv(id, h) {
      const d = el("div", { id: "gspe-eu-" + id, style: { width: "100%", height: (h||500) + "px", marginBottom: "20px" } });
      return d;
    }

    // 1) Total EU+UK offline time series
    const tsSection = euSection("Total Europe + UK Offline Capacity (180d)", "Daily total offline capacity across all European and UK refineries");
    const tsChart = plotDiv("total-ts", 450);
    tsSection.appendChild(tsChart);
    container.appendChild(tsSection);

    // 2) By Country
    if (isAll && data.daily_by_country) {
      const cntSection = euSection("Offline by Country", "Europe vs United Kingdom daily offline capacity");
      const cntChart = plotDiv("by-country", 450);
      cntSection.appendChild(cntChart);
      container.appendChild(cntSection);
    }

    // 3) By Category stacked area
    const catSection = euSection("Offline by Unit Category", "CDU, FCC, VDU, HCU, COK, RFM breakdown");
    const catChart = plotDiv("by-cat", 500);
    catSection.appendChild(catChart);
    container.appendChild(catSection);

    // 4) Seasonal overlay
    const seasonSection = euSection("Seasonal Overlay — Total EU+UK Offline", "Each year plotted on a Jan-Dec axis");
    const seasonChart = plotDiv("seasonal", 500);
    seasonSection.appendChild(seasonChart);
    container.appendChild(seasonSection);

    // 5) Latest offline facilities table
    const facSection = euSection("Currently Offline — Facility Detail", "All units offline as of " + data.date_range.max);
    const facTbl = el("div");
    facSection.appendChild(facTbl);
    container.appendChild(facSection);

    // 6) 2-week offline table
    const tblSection = euSection("2-Week Daily Offline Capacity Table", "Click to load detailed PADD-style table");
    const tblBox = el("div", { style: { overflowX: "auto" } });
    const tblLoadRow = el("div", { style: { display: "flex", gap: "8px", marginBottom: "10px" } });

    countries.forEach(c => {
      const b = el("button", { style: { background: C.amber, color: "#000", border: "none", padding: "6px 14px", borderRadius: "4px", cursor: "pointer", fontSize: "12px", fontWeight: "600" } }, `Load ${c}`);
      b.addEventListener("click", async () => {
        b.textContent = "Loading..."; b.disabled = true;
        try {
          const r = await fetch(`/api/genscape/offline_table?days=14&region=${encodeURIComponent(c)}`);
          if (!r.ok) throw new Error(await r.text());
          const d = await r.json();
          renderOfflineTable(tblBox, d);
        } catch(e) { tblBox.innerHTML = `<div style="color:${C.red}">Error: ${e.message}</div>`; }
        finally { b.textContent = `Load ${c}`; b.disabled = false; }
      });
      tblLoadRow.appendChild(b);
    });
    tblSection.appendChild(tblLoadRow);
    tblSection.appendChild(tblBox);
    container.appendChild(tblSection);

    // ── Draw charts ──
    function drawEuCharts() {
      const layout = (title) => ({
        title: { text: title, font: { color: C.text, size: 14 } },
        paper_bgcolor: "transparent", plot_bgcolor: "transparent",
        font: { color: C.text, size: 11 },
        xaxis: { gridcolor: "#1e293b", linecolor: C.border },
        yaxis: { title: "Offline Capacity (kbd)", gridcolor: "#1e293b", linecolor: C.border },
        legend: { orientation: "h", y: -0.15, font: { size: 10 } },
        margin: { t: 40, r: 20, b: 60, l: 60 },
        hovermode: "x unified",
      });

      // 1) Total time series
      if (data.daily_total) {
        Plotly.newPlot("gspe-eu-total-ts", [{
          x: data.daily_total.dates, y: data.daily_total.values,
          type: "scatter", mode: "lines", fill: "tozeroy",
          line: { color: "#ef4444", width: 2 }, fillcolor: "rgba(239,68,68,0.15)",
          name: "Total Offline",
        }], layout("Total EU + UK Offline Capacity (kbd)"), { responsive: true });
      }

      // 2) By country
      if (isAll && data.daily_by_country) {
        const traces = [];
        data.countries.forEach((c, i) => {
          const d = data.daily_by_country[c];
          if (d) traces.push({
            x: d.dates, y: d.values, type: "scatter", mode: "lines",
            fill: "tonexty", line: { color: chartColors[i % chartColors.length], width: 2 },
            name: c, stackgroup: "one",
          });
        });
        Plotly.newPlot("gspe-eu-by-country", traces, layout("Offline by Country (kbd)"), { responsive: true });
      }

      // 3) By category stacked
      if (data.daily_by_category) {
        const traces = [];
        Object.entries(data.daily_by_category).forEach(([cat, d]) => {
          traces.push({
            x: d.dates, y: d.values, type: "scatter", mode: "lines",
            fill: "tonexty", line: { color: catColors[cat] || "#94a3b8", width: 1.5 },
            name: cat, stackgroup: "one",
          });
        });
        Plotly.newPlot("gspe-eu-by-cat", traces, layout("Offline by Unit Category (kbd)"), { responsive: true });
      }

      // 4) Seasonal overlay
      if (data.seasonal) {
        const yrColors = { 2024: "#3b82f6", 2025: "#f59e0b", 2026: "#ef4444" };
        const traces = [];
        Object.entries(data.seasonal).forEach(([yr, d]) => {
          if (parseInt(yr) >= 2024) {
            // Convert DOY to month-day for display
            const xDates = d.doy.map(doy => {
              const dt = new Date(2024, 0, 1);
              dt.setDate(dt.getDate() + doy - 1);
              return `${String(dt.getMonth()+1).padStart(2,'0')}-${String(dt.getDate()).padStart(2,'0')}`;
            });
            traces.push({
              x: xDates, y: d.values, type: "scatter", mode: "lines",
              line: { color: yrColors[yr] || "#94a3b8", width: yr === "2026" ? 3 : 2, dash: yr === "2026" ? "solid" : "dot" },
              name: yr,
            });
          }
        });
        const sLayout = layout("Seasonal Overlay — EU+UK Offline (kbd)");
        sLayout.xaxis.type = "category";
        sLayout.xaxis.tickangle = -45;
        sLayout.xaxis.nticks = 24;
        Plotly.newPlot("gspe-eu-seasonal", traces, sLayout, { responsive: true });
      }
    }

    // ── Facility offline table ──
    const filteredFacs = data.facility_offline.filter(f => isAll || f.country === regionFilter);
    if (filteredFacs.length > 0) {
      const tbl = document.createElement("table");
      tbl.style.cssText = `width:100%;border-collapse:collapse;font-size:12px;`;
      const hdrS = `padding:8px 10px;border-bottom:2px solid ${C.border};color:${C.amber};font-weight:600;text-align:left;background:#111827;`;
      const cellS = `padding:6px 10px;border-bottom:1px solid ${C.border};`;
      tbl.innerHTML = `<thead><tr>
        <th style="${hdrS}">Country</th><th style="${hdrS}">Refinery</th><th style="${hdrS}">Unit</th>
        <th style="${hdrS}">Category</th><th style="${hdrS}text-align:right;">Capacity (kbd)</th><th style="${hdrS}">Outage Type</th>
      </tr></thead>`;
      const tbody = document.createElement("tbody");
      filteredFacs.forEach((f, i) => {
        const bgc = i % 2 === 0 ? "transparent" : "rgba(30,41,59,0.3)";
        const capColor = f.capacity >= 100 ? C.red : (f.capacity >= 50 ? "#f59e0b" : C.text);
        const otColor = f.outageType === "Unplanned" ? C.red : (f.outageType === "Planned" ? "#10b981" : C.muted);
        const tr = document.createElement("tr");
        tr.style.background = bgc;
        tr.innerHTML = `
          <td style="${cellS}color:${C.muted};">${f.country}</td>
          <td style="${cellS}color:${C.text};font-weight:600;">${f.facility}</td>
          <td style="${cellS}color:${C.text};">${f.unit}</td>
          <td style="${cellS}color:${catColors[f.category] || C.text};">${f.category}</td>
          <td style="${cellS}text-align:right;color:${capColor};font-weight:600;">${f.capacity.toFixed(1)}</td>
          <td style="${cellS}color:${otColor};">${f.outageType}</td>
        `;
        tbody.appendChild(tr);
      });
      tbl.appendChild(tbody);
      facTbl.appendChild(tbl);
    } else {
      facTbl.innerHTML = `<div style="color:${C.green};padding:10px;">No offline units for this region as of ${data.date_range.max}</div>`;
    }

    loadPlotly(() => drawEuCharts());
  }


  // ─── LOCAL GASOLINE BALANCES — QUARTERLY (LEM) TAB ───
  async function renderLEM(box) {
    box.innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8;">Loading quarterly balances...</div>';
    let data;
    try {
      const r = await fetch("/api/lem/quarterly");
      if (!r.ok) throw new Error(r.statusText);
      data = await r.json();
    } catch(e) {
      box.innerHTML = `<div style="color:${C.red};padding:20px;">Error loading quarterly balance data: ${e.message}</div>`;
      return;
    }
    box.innerHTML = "";
    renderLEMQuarterly(box, data);
  }

  function renderLEMQuarterly(box, data) {
    const Q = data.quarters;
    const gas = data.gasoline;
    const notes = data.ai_notes || {};

    function lemSection(title, subtitle) {
      const s = el("div", { style: { marginBottom: "25px" } });
      s.appendChild(el("h3", { style: { color: C.amber, margin: "0 0 4px 0", fontSize: "16px", borderBottom: `1px solid ${C.border}`, paddingBottom: "6px" } }, title));
      if (subtitle) s.appendChild(el("p", { style: { color: C.muted, fontSize: "12px", margin: "0 0 10px 0" } }, subtitle));
      return s;
    }

    function qTable(rows, opts) {
      // rows: [{name, series:{Balance:[..8], Demand:[..], Supply:[..]}}]
      const o = opts || {};
      const t = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px" } });
      const thead = el("tr", {});
      thead.appendChild(el("th", { style: { textAlign: "left", padding: "5px 8px", color: C.muted, borderBottom: `1px solid ${C.border}` } }, o.firstCol || ""));
      Q.forEach(q => thead.appendChild(el("th", { style: { textAlign: "right", padding: "5px 8px", color: q.endsWith("'26") ? C.gold : C.muted, borderBottom: `1px solid ${C.border}` } }, q)));
      t.appendChild(thead);
      rows.forEach(row => {
        Object.keys(row.series).forEach((metric, mi) => {
          const vals = row.series[metric];
          if (!vals) return;
          const tr = el("tr", {});
          const isBal = metric === "Balance";
          tr.appendChild(el("td", { style: { padding: "4px 8px", color: mi === 0 ? C.text : C.muted, fontWeight: mi === 0 ? "700" : "400", paddingLeft: mi === 0 ? "8px" : "20px", borderBottom: `1px solid ${C.border}22` } }, mi === 0 ? row.name : metric));
          vals.forEach(v => {
            const col = !isBal ? C.text : v == null ? C.muted : v < 0 ? C.red : C.green;
            tr.appendChild(el("td", { style: { textAlign: "right", padding: "4px 8px", color: col, fontVariantNumeric: "tabular-nums", borderBottom: `1px solid ${C.border}22` } }, isBal ? eaSign(v) : eaFmt(v)));
          });
          t.appendChild(tr);
        });
      });
      const wrap = el("div", { style: { overflowX: "auto" } });
      wrap.appendChild(t);
      return wrap;
    }

    // ── Header ──
    const hdr = el("div", { style: { marginBottom: "20px" } });
    hdr.appendChild(el("h2", { style: { color: C.amber, margin: "0 0 6px 0", fontSize: "20px" } }, "⛽ Local Gasoline Balances — Quarterly (Q1'25 → Q4'26)"));
    hdr.appendChild(el("p", { style: { color: C.muted, fontSize: "12px", margin: 0 } }, `Quarterly light-ends balances · demand / supply / balance in kb/d · as of ${data.as_of} · '26 quarters include forecast`));
    box.appendChild(hdr);

    // ── AI Analyst Notes ──
    if (notes.points) {
      const sec = lemSection("🤖 AI Analyst Notes — " + (notes.headline || ""), notes.generated);
      const grid = el("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" } });
      notes.points.forEach((pt, i) => {
        const c = el("div", { style: { background: C.card, border: `1px solid ${C.border}`, borderLeft: `3px solid ${C.gold}`, borderRadius: "6px", padding: "10px 12px", fontSize: "12px", color: C.text, lineHeight: "1.5" } });
        c.appendChild(el("span", { style: { color: C.gold, fontWeight: "700", marginRight: "6px" } }, `${i + 1}.`));
        c.appendChild(document.createTextNode(pt));
        grid.appendChild(c);
      });
      sec.appendChild(grid);
      if (notes.conclusion) {
        sec.appendChild(el("div", { style: { marginTop: "10px", background: "#132018", border: `1px solid ${C.green}55`, borderRadius: "6px", padding: "12px 14px", fontSize: "12.5px", color: C.text, lineHeight: "1.55" } }, notes.conclusion));
      }
      box.appendChild(sec);
    }

    // ── Regional quarterly balances ──
    const regSec = lemSection("🌍 Regional Gasoline Balances by Quarter (kb/d)", "Balance = supply − demand · negative = deficit (needs imports) · positive = surplus (exports)");
    const regChart = el("div", { style: { height: "360px", marginBottom: "12px" } });
    regSec.appendChild(card("Quarterly balance by region", regChart));
    const regionNames = Object.keys(gas.regions).filter(r => r !== "Global");
    const regRows = regionNames.concat(gas.regions.Global ? ["Global"] : []).map(r => ({
      name: r === "Global" ? "GLOBAL" : r,
      series: { Balance: gas.regions[r].balance, Demand: gas.regions[r].demand, Supply: gas.regions[r].supply },
    }));
    regSec.appendChild(card("Regional quarterly table (kb/d)", qTable(regRows, { firstCol: "Region / metric" })));
    box.appendChild(regSec);

    // ── Country explorer ──
    const ctrySec = lemSection("🗺️ Country Balances by Quarter (kb/d)", "Pick a region to see its country-level quarterly gasoline balances");
    const chipRow = el("div", { style: { display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "10px" } });
    const ctryBody = el("div", {});
    ctrySec.appendChild(chipRow);
    ctrySec.appendChild(ctryBody);
    const ctryRegions = Object.keys(gas.countries);
    let activeReg = ctryRegions[0];
    function drawCountries() {
      ctryBody.innerHTML = "";
      const cs = gas.countries[activeReg];
      const rows = Object.keys(cs).map(cn => ({ name: cn === "Total" ? `TOTAL ${activeReg.toUpperCase()}` : cn, series: { Balance: cs[cn].balance, Demand: cs[cn].demand, Supply: cs[cn].supply } }));
      ctryBody.appendChild(card(`${activeReg} — country quarterly balances (kb/d)`, qTable(rows, { firstCol: "Country / metric" })));
    }
    ctryRegions.forEach(rn => {
      const chip = el("button", { style: { background: rn === activeReg ? C.gold : C.card, color: rn === activeReg ? "#000" : C.text, border: `1px solid ${C.border}`, borderRadius: "14px", padding: "5px 14px", fontSize: "12px", cursor: "pointer" } }, rn);
      chip.onclick = () => {
        activeReg = rn;
        Array.from(chipRow.children).forEach((c, i) => { c.style.background = ctryRegions[i] === rn ? C.gold : C.card; c.style.color = ctryRegions[i] === rn ? "#000" : C.text; });
        drawCountries();
      };
      chipRow.appendChild(chip);
    });
    drawCountries();
    box.appendChild(ctrySec);

    // ── US & PADD detail ──
    const usSec = lemSection("🇺🇸 United States & PADD Quarterly Balances (kb/d)", "US total incl. refinery gasoline + ethanol split · Canada & Mexico below");
    const usRows = Object.keys(gas.us).map(k => {
      const e = gas.us[k];
      const series = { Balance: e.balance, Demand: e.demand, Supply: e.supply };
      if (e.refinery_gasoline) series["· refinery gasoline"] = e.refinery_gasoline;
      if (e.ethanol) series["· ethanol"] = e.ethanol;
      return { name: k, series };
    });
    Object.keys(gas.north_america).forEach(k => {
      if (k === "Total") return;
      const e = gas.north_america[k];
      usRows.push({ name: k, series: { Balance: e.balance, Demand: e.demand, Supply: e.supply } });
    });
    usSec.appendChild(card("US / PADD / Canada / Mexico (kb/d)", qTable(usRows, { firstCol: "Area / metric" })));
    box.appendChild(usSec);

    // ── Naphtha ──
    const napSec = lemSection("🧪 Naphtha Quarterly Balances", "Country-level naphtha balances — Asia Pacific & Europe (source units)");
    Object.keys(data.naphtha.countries).forEach(reg => {
      const cs = data.naphtha.countries[reg];
      const rows = Object.keys(cs).map(cn => ({ name: cn, series: { Balance: cs[cn].balance, Demand: cs[cn].demand, Supply: cs[cn].supply } }));
      napSec.appendChild(card(`${reg} — naphtha quarterly balances`, qTable(rows, { firstCol: "Country / metric" })));
    });
    box.appendChild(napSec);

    // ── Refinery runs + maintenance ──
    const refSec = lemSection("🏭 Refinery Runs & Maintenance", "Quarterly crude runs (mb/d) by region · monthly offline capacity (kb/d) May–Nov 2026");
    const runsChart = el("div", { style: { height: "360px" } });
    const maintChart = el("div", { style: { height: "320px" } });
    refSec.appendChild(card("Refinery runs by region (mb/d)", runsChart));
    refSec.appendChild(card("Quarterly runs table (mb/d)", qTable(Object.keys(data.refinery_runs_mbd).map(k => ({ name: k, series: { Runs: data.refinery_runs_mbd[k] } })), { firstCol: "Region" })));
    refSec.appendChild(card("Maintenance — offline capacity by region (kb/d)", maintChart));
    box.appendChild(refSec);

    loadPlotly(() => {
      const balTraces = regionNames.map(r => ({ x: Q, y: gas.regions[r].balance, name: r, type: "bar" }));
      Plotly.newPlot(regChart, balTraces, { ...plotLayout,
        barmode: "group", xaxis: { ...plotLayout.xaxis, type: "category" },
        yaxis: { ...plotLayout.yaxis, title: "kb/d", zeroline: true, zerolinecolor: "#64748b" },
      }, { responsive: true });

      const runKeys = ["North America", "Europe", "Asia", "Middle East", "FSU", "Latin America", "Africa", "Global Runs"].filter(k => data.refinery_runs_mbd[k]);
      Plotly.newPlot(runsChart, runKeys.map(k => ({
        x: Q, y: data.refinery_runs_mbd[k], name: k, mode: "lines+markers",
        line: { width: k === "Global Runs" ? 3 : 1.6 }, yaxis: k === "Global Runs" ? "y2" : "y",
      })), { ...plotLayout,
        xaxis: { ...plotLayout.xaxis, type: "category" }, yaxis: { ...plotLayout.yaxis, title: "regional mb/d" },
        yaxis2: { title: "global mb/d", overlaying: "y", side: "right", gridcolor: "#1e293b" },
      }, { responsive: true });

      const m = data.maintenance_kbd;
      Plotly.newPlot(maintChart, Object.keys(m.regions).filter(k => k !== "Total").map(k => ({
        x: m.months, y: m.regions[k], name: k, type: "bar",
      })), { ...plotLayout,
        barmode: "stack", xaxis: { ...plotLayout.xaxis, type: "category" }, yaxis: { ...plotLayout.yaxis, title: "kb/d offline" },
      }, { responsive: true });
    });
  }


  // ==========================================================================
  // Kpler Refinery Trade Flows tab
  // ==========================================================================
  // ========== LOCAL BALANCES (global gasoline) ==========

  function eaFmt(n, dec) { return n == null ? "–" : Number(n).toLocaleString(undefined, { maximumFractionDigits: dec == null ? 0 : dec, minimumFractionDigits: dec == null ? 0 : dec }); }
  function eaSign(n, dec) { return n == null ? "–" : (n > 0 ? "+" : "") + eaFmt(n, dec); }

  // ═══════════════════════════════════════════════════════════════════════
  // PLATTS / S&P GLOBAL COMMODITY INSIGHTS
  // ═══════════════════════════════════════════════════════════════════════
  const PLATTS_BENCHMARKS = [
    { sym: "PCAAS00", name: "Dated Brent", uom: "$/bbl" },
    { sym: "POABC00", name: "Gasoil FOB Singapore", uom: "$/bbl" },
    { sym: "PJAAU00", name: "Jet CIF NWE", uom: "$/mt" },
    { sym: "PAAAL00", name: "Naphtha CIF NWE", uom: "$/mt" },
    { sym: "AAQZV00", name: "Gasoline Eurobob FOB AR", uom: "$/mt" },
    { sym: "PUMFD00", name: "Marine Fuel 0.5% FOB Rdam", uom: "$/mt" },
  ];

  async function plattsFetch(path) {
    const r = await fetch(path);
    if (!r.ok) {
      let msg = r.statusText;
      try { const j = await r.json(); msg = j.detail || j.error || msg; } catch (e) {}
      throw new Error(msg);
    }
    return r.json();
  }

  function plattsSection(box, title, subtitle) {
    const s = el("div", { style: { marginBottom: "24px" } });
    s.appendChild(el("h3", { style: { color: C.amber, margin: "0 0 4px 0", fontSize: "16px", borderBottom: `1px solid ${C.border}`, paddingBottom: "6px" } }, title));
    if (subtitle) s.appendChild(el("p", { style: { color: C.muted, fontSize: "12px", margin: "0 0 10px 0" } }, subtitle));
    box.appendChild(s);
    return s;
  }

  async function renderPlatts(box) {
    box.innerHTML = "";

    // ── Header + connection badge ──
    const hdr = el("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "18px" } });
    const hl = el("div", {});
    hl.appendChild(el("h2", { style: { color: C.amber, margin: "0 0 6px 0", fontSize: "20px" } }, "🅿️ Platts — S&P Global Commodity Insights"));
    hl.appendChild(el("p", { style: { color: C.muted, fontSize: "12px", margin: 0 } }, "Live Platts assessments, forward curves & market commentary · credentials stay server-side"));
    hdr.appendChild(hl);
    const badge = el("span", { style: { fontSize: "10.5px", fontWeight: "700", letterSpacing: "1px", padding: "5px 10px", borderRadius: "999px", border: `1px solid ${C.border}`, color: C.muted, whiteSpace: "nowrap" } }, "○ CHECKING…");
    hdr.appendChild(badge);
    box.appendChild(hdr);

    plattsFetch("/api/platts/status").then(st => {
      if (st.connected) { badge.textContent = "● CONNECTED"; badge.style.color = C.green; badge.style.borderColor = C.green + "88"; }
      else if (st.configured) { badge.textContent = "○ AUTH ERROR"; badge.style.color = C.red; badge.style.borderColor = C.red + "88"; }
      else { badge.textContent = "○ NOT CONFIGURED"; badge.style.color = C.amber; }
    }).catch(() => { badge.textContent = "○ OFFLINE"; badge.style.color = C.red; });

    // ══ Benchmarks ══
    const benSec = plattsSection(box, "📊 Key Platts Benchmarks (latest assessment)", "Click a row to load its price history below");
    const benCard = card("Benchmarks", el("div", { style: { color: C.muted, fontSize: "12px", padding: "8px" } }, "Loading…"));
    benSec.appendChild(benCard);

    // ══ History chart target ══
    const histSec = plattsSection(box, "📈 Assessment History", "Select a benchmark above or search a symbol below");
    const histTitle = el("div", { style: { color: C.text, fontSize: "13px", fontWeight: "700", marginBottom: "8px" } }, "No symbol selected");
    const histChart = el("div", { style: { height: "340px" } });
    histSec.appendChild(card(histTitle, histChart));

    let plotReady = false;
    loadPlotly(() => { plotReady = true; });

    async function showHistory(sym, label, uom) {
      histTitle.textContent = `${label || sym} (${sym})${uom ? " · " + uom : ""}`;
      histChart.innerHTML = `<div style="color:${C.muted};padding:40px;text-align:center;">Loading history…</div>`;
      try {
        const start = new Date(Date.now() - 400 * 864e5).toISOString().slice(0, 10);
        const j = await plattsFetch(`/api/platts/history?symbol=${encodeURIComponent(sym)}&start=${start}&bate=c&page_size=5000`);
        const res = (j.results || []).filter(r => r.symbol === sym);
        let pts = [];
        res.forEach(r => (r.data || []).forEach(d => pts.push([d.assessDate, d.value])));
        pts = pts.filter(p => p[1] != null).sort((a, b) => a[0] < b[0] ? -1 : 1);
        if (!pts.length) { histChart.innerHTML = `<div style="color:${C.muted};padding:40px;text-align:center;">No history returned</div>`; return; }
        const draw = () => Plotly.newPlot(histChart, [{
          x: pts.map(p => p[0].slice(0, 10)), y: pts.map(p => p[1]),
          mode: "lines", line: { color: C.amber, width: 1.8 }, name: sym,
          fill: "tozeroy", fillcolor: "rgba(56,189,248,0.06)",
        }], { ...plotLayout, yaxis: { ...plotLayout.yaxis, title: uom || "" } }, { responsive: true });
        if (plotReady) draw(); else loadPlotly(() => { plotReady = true; draw(); });
      } catch (e) {
        histChart.innerHTML = `<div style="color:${C.red};padding:20px;">Error: ${e.message}</div>`;
      }
    }

    // Load benchmark current values
    (async () => {
      try {
        const syms = PLATTS_BENCHMARKS.map(b => b.sym).join(",");
        const j = await plattsFetch(`/api/platts/current?symbols=${syms}&bate=c,h,l`);
        const bySym = {};
        (j.results || []).forEach(r => { bySym[r.symbol] = r.data || []; });
        const t = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "12px" } });
        const hr = el("tr", {});
        ["Benchmark", "Symbol", "Close", "High", "Low", "Date"].forEach((h, i) =>
          hr.appendChild(el("th", { style: { textAlign: i === 0 ? "left" : "right", padding: "6px 10px", color: C.muted, borderBottom: `1px solid ${C.border}` } }, h)));
        t.appendChild(hr);
        PLATTS_BENCHMARKS.forEach(b => {
          const data = bySym[b.sym] || [];
          const pick = code => { const d = data.find(x => x.bate === code); return d ? d.value : null; };
          const dt = data.length ? (data[0].assessDate || "").slice(0, 10) : "";
          const tr = el("tr", { style: { cursor: "pointer" }, onClick: () => showHistory(b.sym, b.name, b.uom) });
          tr.addEventListener("mouseenter", () => tr.style.background = "rgba(56,189,248,0.06)");
          tr.addEventListener("mouseleave", () => tr.style.background = "transparent");
          tr.appendChild(el("td", { style: { padding: "6px 10px", color: C.text, fontWeight: "600", borderBottom: `1px solid ${C.border}22` } }, `${b.name} · ${b.uom}`));
          tr.appendChild(el("td", { style: { textAlign: "right", padding: "6px 10px", color: C.blue, fontVariantNumeric: "tabular-nums", borderBottom: `1px solid ${C.border}22` } }, b.sym));
          [pick("c"), pick("h"), pick("l")].forEach(v =>
            tr.appendChild(el("td", { style: { textAlign: "right", padding: "6px 10px", color: C.text, fontVariantNumeric: "tabular-nums", borderBottom: `1px solid ${C.border}22` } }, v == null ? "–" : eaFmt(v, 2))));
          tr.appendChild(el("td", { style: { textAlign: "right", padding: "6px 10px", color: C.muted, borderBottom: `1px solid ${C.border}22` } }, dt));
          t.appendChild(tr);
        });
        benCard.replaceChild(t, benCard.lastChild);
        // Auto-load first benchmark history
        showHistory(PLATTS_BENCHMARKS[0].sym, PLATTS_BENCHMARKS[0].name, PLATTS_BENCHMARKS[0].uom);
      } catch (e) {
        benCard.replaceChild(el("div", { style: { color: C.red, padding: "10px", fontSize: "12px" } }, "Error loading benchmarks: " + e.message), benCard.lastChild);
      }
    })();

    // ══ Symbol search ══
    const searchSec = plattsSection(box, "🔎 Symbol Search", "Search Platts' assessment universe by keyword (e.g. 'Dubai', 'ULSD', 'RBOB'). Click a result to chart it.");
    const searchRow = el("div", { style: { display: "flex", gap: "8px", marginBottom: "10px" } });
    const searchInput = el("input", { placeholder: "Search assessments…", style: { flex: "1", padding: "8px 12px", background: C.card, border: `1px solid ${C.border}`, borderRadius: "6px", color: C.text, fontSize: "13px" } });
    const searchBtn = el("button", { style: { padding: "8px 18px", background: C.amber, color: "#04121c", border: "none", borderRadius: "6px", fontWeight: "700", cursor: "pointer", fontSize: "13px" } }, "Search");
    searchRow.appendChild(searchInput); searchRow.appendChild(searchBtn);
    searchSec.appendChild(searchRow);
    const searchOut = el("div", {});
    searchSec.appendChild(searchOut);

    async function doSearch() {
      const q = searchInput.value.trim();
      if (!q) return;
      searchOut.innerHTML = `<div style="color:${C.muted};padding:12px;font-size:12px;">Searching…</div>`;
      try {
        const j = await plattsFetch(`/api/platts/search?q=${encodeURIComponent(q)}&page_size=40`);
        const rows = j.results || [];
        if (!rows.length) { searchOut.innerHTML = `<div style="color:${C.muted};padding:12px;font-size:12px;">No matches.</div>`; return; }
        searchOut.innerHTML = "";
        searchOut.appendChild(el("div", { style: { color: C.muted, fontSize: "11px", marginBottom: "6px" } }, `${j.count != null ? j.count.toLocaleString() : rows.length} matches · showing ${rows.length}`));
        const t = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11.5px" } });
        const hr = el("tr", {});
        ["Symbol", "Description", "Commodity", "Freq", "UOM"].forEach((h, i) =>
          hr.appendChild(el("th", { style: { textAlign: "left", padding: "5px 8px", color: C.muted, borderBottom: `1px solid ${C.border}` } }, h)));
        t.appendChild(hr);
        rows.forEach(r => {
          const tr = el("tr", { style: { cursor: "pointer" }, onClick: () => { showHistory(r.symbol, r.description, r.uom); histSec.scrollIntoView({ behavior: "smooth", block: "start" }); } });
          tr.addEventListener("mouseenter", () => tr.style.background = "rgba(56,189,248,0.06)");
          tr.addEventListener("mouseleave", () => tr.style.background = "transparent");
          tr.appendChild(el("td", { style: { padding: "5px 8px", color: C.blue, fontWeight: "700", borderBottom: `1px solid ${C.border}22` } }, r.symbol));
          tr.appendChild(el("td", { style: { padding: "5px 8px", color: C.text, borderBottom: `1px solid ${C.border}22` } }, r.description || ""));
          tr.appendChild(el("td", { style: { padding: "5px 8px", color: C.muted, borderBottom: `1px solid ${C.border}22` } }, r.commodity || ""));
          tr.appendChild(el("td", { style: { padding: "5px 8px", color: C.muted, borderBottom: `1px solid ${C.border}22` } }, r.assessment_frequency || ""));
          tr.appendChild(el("td", { style: { padding: "5px 8px", color: C.muted, borderBottom: `1px solid ${C.border}22` } }, r.uom || ""));
          t.appendChild(tr);
        });
        const wrap = el("div", { style: { overflowX: "auto", maxHeight: "360px", overflowY: "auto" } });
        wrap.appendChild(t);
        searchOut.appendChild(wrap);
      } catch (e) {
        searchOut.innerHTML = `<div style="color:${C.red};padding:12px;font-size:12px;">Error: ${e.message}</div>`;
      }
    }
    searchBtn.addEventListener("click", doSearch);
    searchInput.addEventListener("keydown", e => { if (e.key === "Enter") doSearch(); });

    // ══ Forward curves ══
    const curveSec = plattsSection(box, "📉 Forward Curves", "Search a forward curve (e.g. 'Brent', 'Gasoil') and chart its term structure.");
    const curveRow = el("div", { style: { display: "flex", gap: "8px", marginBottom: "10px" } });
    const curveInput = el("input", { placeholder: "Search forward curves…", value: "Brent", style: { flex: "1", padding: "8px 12px", background: C.card, border: `1px solid ${C.border}`, borderRadius: "6px", color: C.text, fontSize: "13px" } });
    const curveBtn = el("button", { style: { padding: "8px 18px", background: C.amber, color: "#04121c", border: "none", borderRadius: "6px", fontWeight: "700", cursor: "pointer", fontSize: "13px" } }, "Search");
    curveRow.appendChild(curveInput); curveRow.appendChild(curveBtn);
    curveSec.appendChild(curveRow);
    const curveList = el("div", { style: { display: "flex", flexWrap: "wrap", gap: "6px", marginBottom: "10px" } });
    curveSec.appendChild(curveList);
    const curveChart = el("div", { style: { height: "320px" } });
    curveSec.appendChild(card("Term structure", curveChart));

    async function drawCurve(code, name) {
      curveChart.innerHTML = `<div style="color:${C.muted};padding:40px;text-align:center;">Loading ${name}…</div>`;
      try {
        const j = await plattsFetch(`/api/platts/curve?code=${encodeURIComponent(code)}&page_size=80`);
        const res = j.results || {};
        const rowsArr = Array.isArray(res) ? res : (res.symbol_data || []);
        const closeOf = d => {
          if (d.value != null) return d.value;
          const cs = (d.data || []).filter(x => x.bate === "c" && x.value != null).sort((a, b) => a.assessDate < b.assessDate ? 1 : -1);
          return cs.length ? cs[0].value : null;
        };
        const pts = rowsArr
          .map(d => ({ label: d.contract_label || d.contractLabel || d.symbol, pos: d.derivative_position != null ? d.derivative_position : 0, value: closeOf(d) }))
          .filter(p => p.value != null)
          .sort((a, b) => a.pos - b.pos);
        if (!pts.length) { curveChart.innerHTML = `<div style="color:${C.muted};padding:40px;text-align:center;">No curve data</div>`; return; }
        const draw = () => Plotly.newPlot(curveChart, [{
          x: pts.map(p => p.label), y: pts.map(p => p.value),
          mode: "lines+markers", line: { color: C.purple, width: 2 }, marker: { size: 6 }, name: name,
        }], { ...plotLayout, xaxis: { ...plotLayout.xaxis, type: "category" }, yaxis: { ...plotLayout.yaxis, title: "" } }, { responsive: true });
        if (plotReady) draw(); else loadPlotly(() => { plotReady = true; draw(); });
      } catch (e) {
        curveChart.innerHTML = `<div style="color:${C.red};padding:20px;">Error: ${e.message}</div>`;
      }
    }

    async function searchCurves() {
      const q = curveInput.value.trim();
      curveList.innerHTML = `<span style="color:${C.muted};font-size:12px;">Searching…</span>`;
      try {
        const j = await plattsFetch(`/api/platts/curve-search?q=${encodeURIComponent(q)}&page_size=20`);
        const rows = (j.results || []).filter(r => r.curve_code);
        if (!rows.length) { curveList.innerHTML = `<span style="color:${C.muted};font-size:12px;">No curves found.</span>`; return; }
        curveList.innerHTML = "";
        rows.forEach((r, i) => {
          const chip = el("button", { style: { padding: "5px 12px", borderRadius: "999px", fontSize: "11px", fontWeight: "600", cursor: "pointer", background: C.card, border: `1px solid ${C.border}`, color: C.text } }, r.curve_name || r.curve_code);
          chip.addEventListener("click", () => { Array.from(curveList.children).forEach(c => { c.style.background = C.card; c.style.borderColor = C.border; }); chip.style.background = C.purple + "33"; chip.style.borderColor = C.purple; drawCurve(r.curve_code, r.curve_name || r.curve_code); });
          curveList.appendChild(chip);
          if (i === 0) chip.click();
        });
      } catch (e) {
        curveList.innerHTML = `<span style="color:${C.red};font-size:12px;">Error: ${e.message}</span>`;
      }
    }
    curveBtn.addEventListener("click", searchCurves);
    curveInput.addEventListener("keydown", e => { if (e.key === "Enter") searchCurves(); });
    searchCurves();

    // ══ News ══
    const newsSec = plattsSection(box, "📰 Platts Market Commentary & News", "Latest headlines from Platts news & insights");
    const newsRow = el("div", { style: { display: "flex", gap: "8px", marginBottom: "10px" } });
    const newsInput = el("input", { placeholder: "Filter news (e.g. 'gasoline', 'OPEC')…", style: { flex: "1", padding: "8px 12px", background: C.card, border: `1px solid ${C.border}`, borderRadius: "6px", color: C.text, fontSize: "13px" } });
    const newsBtn = el("button", { style: { padding: "8px 18px", background: C.amber, color: "#04121c", border: "none", borderRadius: "6px", fontWeight: "700", cursor: "pointer", fontSize: "13px" } }, "Search");
    newsRow.appendChild(newsInput); newsRow.appendChild(newsBtn);
    newsSec.appendChild(newsRow);
    const newsOut = el("div", {});
    newsSec.appendChild(newsOut);

    async function loadNews() {
      const q = newsInput.value.trim();
      newsOut.innerHTML = `<div style="color:${C.muted};padding:12px;font-size:12px;">Loading…</div>`;
      try {
        const j = await plattsFetch(`/api/platts/news?page_size=25${q ? "&q=" + encodeURIComponent(q) : ""}`);
        const rows = j.results || [];
        if (!rows.length) { newsOut.innerHTML = `<div style="color:${C.muted};padding:12px;font-size:12px;">No headlines.</div>`; return; }
        newsOut.innerHTML = "";
        rows.forEach(r => {
          const item = el("div", { style: { padding: "8px 12px", borderBottom: `1px solid ${C.border}22`, display: "flex", justifyContent: "space-between", gap: "12px" } });
          const link = el("a", { href: r.documentUrl || "#", target: "_blank", style: { color: C.text, fontSize: "12.5px", textDecoration: "none", flex: "1", lineHeight: "1.4" } }, r.headline || "(untitled)");
          link.addEventListener("mouseenter", () => link.style.color = C.amber);
          link.addEventListener("mouseleave", () => link.style.color = C.text);
          item.appendChild(link);
          item.appendChild(el("span", { style: { color: C.muted, fontSize: "10.5px", whiteSpace: "nowrap" } }, (r.updatedDate || "").slice(0, 16).replace("T", " ")));
          newsOut.appendChild(item);
        });
      } catch (e) {
        newsOut.innerHTML = `<div style="color:${C.red};padding:12px;font-size:12px;">Error: ${e.message}</div>`;
      }
    }
    newsBtn.addEventListener("click", loadNews);
    newsInput.addEventListener("keydown", e => { if (e.key === "Enter") loadNews(); });
    loadNews();
  }

  function eaChipBar(options, active, onPick) {
    const bar = el("div", { style: { display: "flex", flexWrap: "wrap", gap: "6px", marginBottom: "12px" } });
    options.forEach(o => {
      const isOn = o.value === active;
      bar.appendChild(el("button", {
        style: {
          padding: "5px 12px", borderRadius: "999px", fontSize: "11px", fontWeight: "700", cursor: "pointer",
          border: `1px solid ${isOn ? C.amber : C.border}`, color: isOn ? "#000" : C.muted,
          background: isOn ? C.amber : "#0b1220",
        },
        onClick: () => onPick(o.value),
      }, o.label));
    });
    return bar;
  }

  // Weekly US/PADD gasoline balance table + trend predictions (shared by the
  // Local Balances tab and the Gasoline Stocks tab).
  function usWeeklyForecastBlock(container) {
    let area = "US";
    const wrap = el("div", {});
    container.appendChild(wrap);

    async function load() {
      wrap.innerHTML = '<div style="color:#94a3b8;padding:20px;">Loading weekly balance forecast…</div>';
      let d;
      try { const r = await fetch(`/api/localbal/usweekly?area=${encodeURIComponent(area)}`); if (!r.ok) throw new Error((await r.json()).detail || r.statusText); d = await r.json(); }
      catch (e) { wrap.innerHTML = `<div style="color:${C.red};padding:12px;">Weekly forecast unavailable: ${e.message}</div>`; return; }
      wrap.innerHTML = "";

      const asOf = d.as_of, a = d.data, dates = a.dates;
      const lastActualIdx = (() => { let k = -1; for (let i = 0; i < dates.length; i++) if (dates[i] <= asOf) k = i; return k; })();
      const startIdx = Math.max(0, lastActualIdx - 7);

      wrap.appendChild(eaChipBar((d.areas || []).map(x => ({ value: x, label: x })), area, v => { area = v; load(); }));

      const isUS = area === "US";
      const cols = isUS
        ? [["production", "Production kb/d"], ["imports", "Imports kb/d"], ["exports", "Exports kb/d"], ["net_imports", "Net imports kb/d"], ["product_supplied", "Product supplied kb/d"], ["stock_change", "Stock chg kb/d"], ["stocks", "Stocks mb"]]
        : [["production", "Production kb/d"], ["demand", "Demand kb/d"], ["net_imports", "Net imports kb/d"], ["stock_change", "Stock chg kb/d"], ["stocks", "Stocks mb"]];

      const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11.5px" } });
      const thr = el("tr", {});
      thr.appendChild(el("th", { style: { textAlign: "left", padding: "6px 8px", color: C.amber, borderBottom: `1px solid ${C.border}` } }, "Week ending"));
      cols.forEach(c => thr.appendChild(el("th", { style: { textAlign: "right", padding: "6px 8px", color: C.amber, borderBottom: `1px solid ${C.border}` } }, c[1])));
      thr.appendChild(el("th", { style: { textAlign: "center", padding: "6px 8px", color: C.amber, borderBottom: `1px solid ${C.border}` } }, ""));
      tbl.appendChild(thr);

      for (let i = startIdx; i < dates.length; i++) {
        const isFcst = dates[i] > asOf;
        const tr = el("tr", { style: { background: isFcst ? "rgba(245,185,15,0.06)" : "transparent" } });
        tr.appendChild(el("td", { style: { padding: "5px 8px", color: C.text, borderBottom: "1px solid #131c30", fontWeight: i === lastActualIdx ? "800" : "400" } }, dates[i]));
        cols.forEach(c => {
          let v = (a[c[0]] || [])[i];
          if (c[0] === "stocks" && v != null) v = v / 1000;
          const color = c[0] === "stock_change" ? (v > 0 ? C.green : v < 0 ? C.red : C.muted) : C.text;
          tr.appendChild(el("td", { style: { padding: "5px 8px", textAlign: "right", color, borderBottom: "1px solid #131c30" } },
            c[0] === "stocks" ? eaFmt(v, 1) : (c[0] === "stock_change" ? eaSign(v, 0) : eaFmt(v, 0))));
        });
        tr.appendChild(el("td", { style: { padding: "5px 8px", textAlign: "center", borderBottom: "1px solid #131c30" } },
          isFcst ? "FCST" : (i === lastActualIdx ? "LATEST" : "")));
        const tag = tr.lastChild; tag.style.fontSize = "9px"; tag.style.fontWeight = "800";
        tag.style.color = isFcst ? C.gold : (i === lastActualIdx ? C.cyan : C.muted);
        tbl.appendChild(tr);
      }
      wrap.appendChild(card(`${area} — Weekly gasoline balance & forecast (as of ${asOf})`, el("div", { style: { overflowX: "auto" } }, tbl)));

      // Stocks chart: history solid, forecast dashed
      const chartDiv = el("div", { style: { width: "100%", height: "380px" } });
      wrap.appendChild(card(`${area} — Gasoline stocks: history vs forecast`, chartDiv));

      // Trend read / predictions
      const st = a.stocks || [], sc = a.stock_change || [];
      const li = lastActualIdx;
      const avg = (arr, i0, i1) => { const xs = arr.slice(Math.max(0, i0), i1).filter(v => v != null); return xs.length ? xs.reduce((p, q) => p + q, 0) / xs.length : null; };
      const prod4 = avg(a.production || [], li - 3, li + 1), prod4p = avg(a.production || [], li - 7, li - 3);
      const demKey = isUS ? "product_supplied" : "demand";
      const dem4 = avg(a[demKey] || [], li - 3, li + 1), dem4p = avg(a[demKey] || [], li - 7, li - 3);
      const fcstChg = sc.slice(li + 1).filter(v => v != null);
      const cumFcst = fcstChg.length ? fcstChg.reduce((p, q) => p + q, 0) * 7 / 1000 : null;
      const endStock = st[st.length - 1], nowStock = st[li];
      const yrAgo = li >= 52 ? st[li - 52] : null;
      const lines = [];
      if (nowStock != null) lines.push(`Current ${area} gasoline stocks: ${eaFmt(nowStock / 1000, 1)} mb (week ending ${dates[li]})${yrAgo != null ? `, ${eaSign((nowStock - yrAgo) / 1000, 1)} mb vs a year ago` : ""}.`);
      if (prod4 != null && prod4p != null) lines.push(`Production trend: 4-week avg ${eaFmt(prod4, 0)} kb/d, ${eaSign(prod4 - prod4p, 0)} kb/d vs the prior 4 weeks — ${prod4 > prod4p ? "runs/blending ramping up" : "output easing"}.`);
      if (dem4 != null && dem4p != null) lines.push(`Demand trend: 4-week avg ${eaFmt(dem4, 0)} kb/d, ${eaSign(dem4 - dem4p, 0)} kb/d vs the prior 4 weeks — ${dem4 > dem4p ? "seasonal driving demand still building" : "demand momentum fading"}.`);
      if (cumFcst != null && endStock != null) lines.push(`Forecast (${fcstChg.length} weeks ahead): cumulative ${cumFcst < 0 ? "DRAW" : "BUILD"} of ${eaFmt(Math.abs(cumFcst), 1)} mb, taking stocks to ${eaFmt(endStock / 1000, 1)} mb by ${dates[dates.length - 1]}.`);
      if (cumFcst != null) lines.push(cumFcst < 0
        ? "Read: balances tighten into late summer — draws support prompt gasoline cracks and backwardation; upside risk to RBOB spreads if demand holds."
        : "Read: balances loosen — builds cap prompt gasoline cracks; watch for crack weakness and softer prompt spreads.");
      const txt = el("div", { style: { color: C.text, fontSize: "12.5px", lineHeight: "1.8" } });
      lines.forEach(l => txt.appendChild(el("div", {}, "• " + l)));
      txt.appendChild(el("div", { style: { color: C.muted, fontSize: "10.5px", marginTop: "8px" } }, `Source: weekly product stock forecast (release ${d.release_date}); weeks after ${asOf} are forecast. Trend read is model-derived from the series above.`));
      wrap.appendChild(card("Trend read & predictions", txt));

      loadPlotly(() => {
        const histD = dates.slice(0, li + 1), fcstD = dates.slice(li);
        const histS = st.slice(0, li + 1).map(v => v == null ? null : v / 1000);
        const fcstS = st.slice(li).map(v => v == null ? null : v / 1000);
        Plotly.newPlot(chartDiv, [
          { x: histD, y: histS, name: "Actual/nowcast", line: { color: C.cyan, width: 2 } },
          { x: fcstD, y: fcstS, name: "forecast", line: { color: C.gold, width: 2, dash: "dash" } },
        ], { ...plotLayout, yaxis: { ...plotLayout.yaxis, title: "mb" }, shapes: [{ type: "line", x0: asOf, x1: asOf, y0: 0, y1: 1, yref: "paper", line: { color: C.muted, width: 1, dash: "dot" } }] }, { responsive: true, displayModeBar: false });
      });
    }
    load();
    return wrap;
  }

  async function renderEABal(box) {
    box.innerHTML = '<div style="color:#94a3b8;padding:40px;text-align:center;">Loading Local Balances…</div>';
    let meta, summary;
    try {
      const [r1, r2] = await Promise.all([fetch("/api/localbal/regions"), fetch("/api/localbal/summary")]);
      if (!r1.ok) throw new Error((await r1.json()).detail || r1.statusText);
      meta = await r1.json(); summary = await r2.json();
    } catch (e) { box.innerHTML = `<div style="color:${C.red};padding:20px;">Error: ${e.message}</div>`; return; }
    box.innerHTML = "";

    const hdr = el("div", { style: { marginBottom: "14px" } });
    hdr.appendChild(el("div", { style: { fontSize: "15px", fontWeight: "700", color: C.amber } }, "🌐 LOCAL BALANCES — Global & US Gasoline"));
    hdr.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, marginTop: "4px" } }, `As of ${meta.as_of} · release ${meta.release_date} · Monthly regional/country balances + weekly US/PADD stock forecast`));
    box.appendChild(hdr);

    // ── Main things (takeaways) ──
    const world = (summary.regions || []).find(r => r.code === "WORLD");
    const mt = el("div", { style: { color: C.text, fontSize: "12.5px", lineHeight: "1.8" } });
    if (world) {
      mt.appendChild(el("div", {}, `• World: demand ${eaFmt(world.demand / 1000, 1)} mb/d vs supply ${eaFmt(world.supply / 1000, 1)} mb/d in July — balance ${eaSign(world.balance, 0)} kb/d (${world.balance < 0 ? "global DEFICIT, stock-draw regime" : "global SURPLUS, stock-build regime"}); next 3 months avg ${eaSign(world.balance_next3m, 0)} kb/d.`));
      if (world.demand_yoy != null) mt.appendChild(el("div", {}, `• Global demand is ${world.demand_yoy > 0 ? "up" : "down"} ${eaFmt(Math.abs(world.demand_yoy), 0)} kb/d YoY.`));
    }
    if ((summary.tightening_most || []).length) mt.appendChild(el("div", {}, `• Tightening most vs last year: ${summary.tightening_most.join(", ")}.`));
    if ((summary.loosening_most || []).length) mt.appendChild(el("div", {}, `• Loosening most vs last year: ${summary.loosening_most.join(", ")}.`));
    const us = summary.us || {};
    if (us.stocks_mb != null) mt.appendChild(el("div", {}, `• US gasoline stocks ${eaFmt(us.stocks_mb, 1)} mb (${us.stocks_yoy_mb != null ? eaSign(us.stocks_yoy_mb, 1) + " mb YoY" : ""}); forecast avg ${eaSign(us.fcst_stock_change_kbd, 0)} kb/d over the next ${us.fcst_weeks} weeks — ${us.fcst_stock_change_kbd < 0 ? "draws ahead, constructive for RBOB cracks" : "builds ahead, bearish crack pressure"}.`));
    box.appendChild(card("Main things — what's changing (as of " + meta.as_of + ")", mt));

    // Region snapshot table
    const snap = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11.5px" } });
    const hRow = el("tr", {});
    ["Region", "Demand kb/d", "Supply kb/d", "Balance kb/d", "Demand YoY", "Bal next 3m", "Bal vs yr-ago"].forEach((h, i) =>
      hRow.appendChild(el("th", { style: { textAlign: i === 0 ? "left" : "right", padding: "6px 8px", color: C.amber, borderBottom: `1px solid ${C.border}` } }, h)));
    snap.appendChild(hRow);
    (summary.regions || []).forEach(r => {
      const tr = el("tr", { style: r.code === "WORLD" ? { background: "rgba(56,189,248,0.06)" } : {} });
      tr.appendChild(el("td", { style: { padding: "5px 8px", color: C.text, fontWeight: r.code === "WORLD" ? "800" : "400", borderBottom: "1px solid #131c30" } }, r.name));
      [[r.demand, 0, C.text], [r.supply, 0, C.text], [r.balance, 0, r.balance < 0 ? C.red : C.green],
       [r.demand_yoy, 0, r.demand_yoy > 0 ? C.green : C.red], [r.balance_next3m, 0, r.balance_next3m < 0 ? C.red : C.green],
       [r.balance_vs_yr_ago, 0, r.balance_vs_yr_ago < 0 ? C.red : C.green]].forEach(([v, dec, col], i) =>
        tr.appendChild(el("td", { style: { padding: "5px 8px", textAlign: "right", color: v == null ? C.muted : col, borderBottom: "1px solid #131c30" } }, i >= 2 ? eaSign(v, dec) : eaFmt(v, dec))));
      snap.appendChild(tr);
    });
    box.appendChild(card("Regional snapshot — July 2026 (negative balance = deficit / stock draw)", el("div", { style: { overflowX: "auto" } }, snap)));

    // ── Region explorer with filters ──
    let regionCode = "WORLD", countryName = "";
    const explorer = el("div", {});
    box.appendChild(explorer);

    async function loadRegion() {
      explorer.innerHTML = '<div style="color:#94a3b8;padding:20px;">Loading region…</div>';
      let d;
      try {
        const q = `/api/localbal/region?code=${regionCode}` + (countryName ? `&country=${encodeURIComponent(countryName)}` : "");
        const r = await fetch(q); if (!r.ok) throw new Error((await r.json()).detail || r.statusText); d = await r.json();
      } catch (e) { explorer.innerHTML = `<div style="color:${C.red};padding:12px;">${e.message}</div>`; return; }
      explorer.innerHTML = "";

      explorer.appendChild(eaChipBar(meta.regions.map(r => ({ value: r.code, label: r.name })), regionCode, v => { regionCode = v; countryName = ""; loadRegion(); }));

      const clist = (meta.countries || {})[regionCode] || [];
      if (clist.length) {
        const selWrap = el("div", { style: { marginBottom: "12px", display: "flex", alignItems: "center", gap: "8px" } });
        selWrap.appendChild(el("span", { style: { fontSize: "11px", color: C.muted } }, "Country filter:"));
        const sel = el("select", {
          style: { background: "#0b1220", color: C.text, border: `1px solid ${C.border}`, borderRadius: "6px", padding: "5px 8px", fontSize: "12px" },
          onChange: ev => { countryName = ev.target.value; loadRegion(); },
        });
        sel.appendChild(el("option", { value: "" }, `All ${d.name}`));
        clist.forEach(c => { const o = el("option", { value: c }, c); if (c === countryName) o.selected = true; sel.appendChild(o); });
        selWrap.appendChild(sel);
        explorer.appendChild(selWrap);
      }

      const src = d.country || d;
      const title = d.country ? `${d.country.name} (${d.name})` : d.name;
      const ch1 = el("div", { style: { width: "100%", height: "400px" } });
      explorer.appendChild(card(`${title} — Gasoline demand vs supply (kb/d, monthly; forecast beyond mid-2026)`, ch1));
      const ch2 = el("div", { style: { width: "100%", height: "340px" } });
      explorer.appendChild(card(`${title} — Balance (supply − demand, kb/d): negative = deficit`, ch2));

      // Monthly 2026 table
      const dts = src.dates || [], dem = src.demand || [], sup = src.supply || [], bal = src.balance || [];
      const idx26 = dts.map((dt, i) => [dt, i]).filter(([dt]) => dt.startsWith("2026"));
      if (idx26.length) {
        const t = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11.5px" } });
        const tr0 = el("tr", {});
        ["Month", "Supply kb/d", "Demand kb/d", "Balance kb/d", ""].forEach((h, i) =>
          tr0.appendChild(el("th", { style: { textAlign: i === 0 ? "left" : "right", padding: "6px 8px", color: C.amber, borderBottom: `1px solid ${C.border}` } }, h)));
        t.appendChild(tr0);
        idx26.forEach(([dt, i]) => {
          const isF = dt > d.as_of;
          const tr = el("tr", { style: { background: isF ? "rgba(245,185,15,0.06)" : "transparent" } });
          tr.appendChild(el("td", { style: { padding: "5px 8px", color: C.text, borderBottom: "1px solid #131c30" } }, dt.slice(0, 7)));
          [[sup[i], C.text], [dem[i], C.text], [bal[i], bal[i] < 0 ? C.red : C.green]].forEach(([v, col], k) =>
            tr.appendChild(el("td", { style: { padding: "5px 8px", textAlign: "right", color: v == null ? C.muted : col, borderBottom: "1px solid #131c30" } }, k === 2 ? eaSign(v, 0) : eaFmt(v, 0))));
          tr.appendChild(el("td", { style: { padding: "5px 8px", textAlign: "right", fontSize: "9px", fontWeight: "800", color: isF ? C.gold : C.muted, borderBottom: "1px solid #131c30" } }, isF ? "FCST" : ""));
          t.appendChild(tr);
        });
        explorer.appendChild(card(`${title} — 2026 monthly balance table`, el("div", { style: { overflowX: "auto" } }, t)));
      }

      loadPlotly(() => {
        Plotly.newPlot(ch1, [
          { x: dts, y: dem, name: "Demand", line: { color: C.cyan, width: 2 } },
          { x: dts, y: sup, name: "Supply", line: { color: C.gold, width: 2 } },
        ], { ...plotLayout, yaxis: { ...plotLayout.yaxis, title: "kb/d" }, shapes: [{ type: "line", x0: d.as_of, x1: d.as_of, y0: 0, y1: 1, yref: "paper", line: { color: C.muted, width: 1, dash: "dot" } }] }, { responsive: true, displayModeBar: false });
        Plotly.newPlot(ch2, [
          { x: dts, y: bal, name: "Balance", type: "bar", marker: { color: (bal || []).map(v => (v == null || v >= 0) ? C.green : C.red) } },
        ], { ...plotLayout, showlegend: false, yaxis: { ...plotLayout.yaxis, title: "kb/d" }, shapes: [{ type: "line", x0: d.as_of, x1: d.as_of, y0: 0, y1: 1, yref: "paper", line: { color: C.muted, width: 1, dash: "dot" } }] }, { responsive: true, displayModeBar: false });
      });
    }
    loadRegion();

    // ── US weekly forecast section ──
    box.appendChild(el("div", { style: { fontSize: "14px", fontWeight: "700", color: C.amber, margin: "18px 0 10px" } }, "🇺🇸 US WEEKLY GASOLINE BALANCE — actual + forecast by PADD"));
    usWeeklyForecastBlock(box);
  }

  async function renderKTF(box) {
    box.innerHTML = "";
    const uid = "ktf-" + Date.now() + "-";
    let curProduct = "Gasoline", curDirection = "export", curRegion = "US", curGran = "monthly";
    let curMode = "region";
    const regions = {
      "US": "United States", "NWE": "NW Europe", "MED": "Mediterranean",
      "Asia": "East Asia", "India": "India", "Middle East": "Middle East",
      "West Africa": "W. Africa", "Latin America": "Latin America",
      "Canada": "Canada", "Southeast Asia": "SE Asia", "Russia/FSU": "Russia/FSU",
    };
    const products = ["Gasoline","Naphtha","Crude","Gasoil","Diesel","Jet","Kerosene","Fuel Oil"];
    const ly = (yTitle, opts = {}) => ({
      paper_bgcolor: "transparent", plot_bgcolor: "transparent",
      font: { color: C.text, size: 11 }, margin: { l: 65, r: opts.r || 20, t: 30, b: 50 },
      xaxis: { gridcolor: "#1e293b", linecolor: "#334155", tickfont: { size: 10 } },
      yaxis: { title: yTitle, gridcolor: "#1e293b", linecolor: "#334155", tickfont: { size: 10 }, zeroline: true, zerolinecolor: "#334155" },
      ...(opts.yaxis2 ? { yaxis2: opts.yaxis2 } : {}),
      legend: { orientation: "h", x: 0, y: -0.15, font: { size: 10 } }, hovermode: "x unified",
    });
    const cfg = { responsive: true, displayModeBar: false };
    const colors = ["#f59e0b","#6366f1","#10b981","#ef4444","#06b6d4","#8b5cf6","#f97316","#ec4899","#14b8a6","#eab308","#a855f7","#84cc16","#0ea5e9","#d946ef","#64748b","#fb923c","#22d3ee","#a78bfa","#fbbf24","#4ade80","#f43e5e","#38bdf8","#c084fc","#facc15","#34d399"];

    // Mode toggle (Region View vs Refinery Explorer)
    const modeRow = el("div", { style: { display: "flex", gap: "4px", marginBottom: "12px" } });
    const modeRegBtn = el("button", { style: { padding: "8px 20px", background: C.amber, color: "#000", border: "none", borderRadius: "4px 0 0 4px", fontSize: "12px", fontWeight: "700", cursor: "pointer" } }, "📊 Region View");
    const modeExpBtn = el("button", { style: { padding: "8px 20px", background: C.card, color: C.muted, border: "1px solid " + C.border, borderRadius: "0 4px 4px 0", fontSize: "12px", fontWeight: "600", cursor: "pointer" } }, "🔍 Refinery Explorer");
    modeRow.appendChild(modeRegBtn); modeRow.appendChild(modeExpBtn);
    box.appendChild(modeRow);

    // Region mode container
    const regionModeBox = el("div", {});
    // Explorer mode container
    const explorerModeBox = el("div", { style: { display: "none" } });
    box.appendChild(regionModeBox);
    box.appendChild(explorerModeBox);

    modeRegBtn.onclick = () => { curMode = "region"; regionModeBox.style.display = "block"; explorerModeBox.style.display = "none"; modeRegBtn.style.background = C.amber; modeRegBtn.style.color = "#000"; modeExpBtn.style.background = C.card; modeExpBtn.style.color = C.muted; };
    modeExpBtn.onclick = () => { curMode = "explorer"; regionModeBox.style.display = "none"; explorerModeBox.style.display = "block"; modeExpBtn.style.background = C.amber; modeExpBtn.style.color = "#000"; modeRegBtn.style.background = C.card; modeRegBtn.style.color = C.muted; if (!explorerModeBox._loaded) { explorerModeBox._loaded = true; initExplorer(); } };

    // === REFINERY EXPLORER ===
    function initExplorer() {
      explorerModeBox.innerHTML = "";
      const searchRow = el("div", { style: { display: "flex", gap: "10px", alignItems: "center", marginBottom: "16px", flexWrap: "wrap" } });
      searchRow.appendChild(el("span", { style: { fontSize: "12px", color: C.amber, fontWeight: "700" } }, "🔍 Search any refinery/installation:"));
      const searchInput = el("input", { type: "text", placeholder: "Type refinery name (e.g. Jamnagar, ExxonMobil Beaumont, Valero...)", style: { background: C.card, color: C.text, border: "1px solid " + C.border, borderRadius: "4px", padding: "8px 12px", fontSize: "13px", width: "400px" } });
      searchRow.appendChild(searchInput);
      const searchBtn = el("button", { style: { background: C.amber, color: "#000", border: "none", borderRadius: "4px", padding: "8px 16px", fontWeight: "700", fontSize: "12px", cursor: "pointer" } }, "EXPLORE");
      searchRow.appendChild(searchBtn);
      explorerModeBox.appendChild(searchRow);

      const suggestBox = el("div", { style: { position: "relative" } });
      const suggestList = el("div", { style: { position: "absolute", top: "0", left: "0", zIndex: "100", background: "#1e293b", border: "1px solid " + C.border, borderRadius: "4px", maxHeight: "200px", overflowY: "auto", width: "400px", display: "none" } });
      suggestBox.appendChild(suggestList);
      explorerModeBox.appendChild(suggestBox);

      const explorerContent = el("div", {});
      explorerModeBox.appendChild(explorerContent);

      let searchTimer;
      searchInput.addEventListener("input", () => {
        clearTimeout(searchTimer);
        const q = searchInput.value.trim();
        if (q.length < 2) { suggestList.style.display = "none"; return; }
        searchTimer = setTimeout(async () => {
          try {
            const r = await fetch("/api/kpler/refinery_search?q=" + encodeURIComponent(q));
            const d = await r.json();
            suggestList.innerHTML = "";
            if (d.results && d.results.length > 0) {
              d.results.forEach(name => {
                const item = el("div", { style: { padding: "8px 12px", cursor: "pointer", fontSize: "12px", color: C.text, borderBottom: "1px solid " + C.border + "40" } }, name);
                item.onmouseenter = () => item.style.background = "rgba(245,158,11,0.15)";
                item.onmouseleave = () => item.style.background = "transparent";
                item.onclick = () => { searchInput.value = name; suggestList.style.display = "none"; loadExplorer(name); };
                suggestList.appendChild(item);
              });
              suggestList.style.display = "block";
            } else { suggestList.style.display = "none"; }
          } catch (e) { suggestList.style.display = "none"; }
        }, 300);
      });

      searchBtn.onclick = () => { suggestList.style.display = "none"; if (searchInput.value.trim()) loadExplorer(searchInput.value.trim()); };
      searchInput.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { suggestList.style.display = "none"; if (searchInput.value.trim()) loadExplorer(searchInput.value.trim()); } });

      async function loadExplorer(instName) {
        explorerContent.innerHTML = '<div style="text-align:center;padding:40px;color:' + C.muted + '">Loading data for ' + instName + '...</div>';
        try {
          const resp = await fetch("/api/kpler/refinery_explorer?installation=" + encodeURIComponent(instName) + "&start_date=2023-01-01&end_date=2026-12-31");
          if (!resp.ok) throw new Error("HTTP " + resp.status);
          const data = await resp.json();
          explorerContent.innerHTML = "";

          explorerContent.appendChild(el("h2", { style: { fontSize: "18px", fontWeight: "700", color: C.amber, margin: "0 0 16px 0" } }, "🏭 " + instName));

          const expProd = data.data.exports_by_product;
          const impProd = data.data.imports_by_product;
          const expDest = data.data.exports_by_destination;
          const impOrig = data.data.imports_by_origin;

          // Summary badges
          const badges = el("div", { style: { display: "flex", gap: "12px", flexWrap: "wrap", marginBottom: "16px" } });
          const expProds = (expProd && !expProd.error) ? Object.keys(expProd) : [];
          const impProds = (impProd && !impProd.error) ? Object.keys(impProd) : [];
          const totalExp = expProds.reduce((s, p) => s + (expProd[p].total || 0), 0);
          const totalImp = impProds.reduce((s, p) => s + (impProd[p].total || 0), 0);
          if (totalExp > 0) badges.appendChild(el("span", { style: { background: "rgba(16,185,129,0.15)", color: "#10b981", padding: "4px 12px", borderRadius: "20px", fontSize: "12px", fontWeight: "600" } }, "Exports: " + expProds.length + " products, " + totalExp.toFixed(0) + " kbd cumul."));
          if (totalImp > 0) badges.appendChild(el("span", { style: { background: "rgba(99,102,241,0.15)", color: "#6366f1", padding: "4px 12px", borderRadius: "20px", fontSize: "12px", fontWeight: "600" } }, "Imports: " + impProds.length + " products, " + totalImp.toFixed(0) + " kbd cumul."));
          explorerContent.appendChild(badges);

          // Exports by product chart
          if (expProds.length > 0) {
            const ch1 = el("div", { id: uid + "exp", style: { width: "100%", height: "380px", marginBottom: "16px" } });
            explorerContent.appendChild(card("Exports by Product (kbd) — Monthly since 2023", ch1));
            try {
              const traces = expProds.map((p, i) => ({ x: expProd[p].dates, y: expProd[p].values, name: p, stackgroup: "one", line: { color: colors[i], width: 0 }, fillcolor: colors[i] + "40" }));
              Plotly.newPlot(uid + "exp", traces, ly("kbd"), cfg);
            } catch (e) {}

            // Export product totals table
            const etbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "12px", marginBottom: "16px" } });
            const eh = el("tr"); ["Product", "Total (kbd)", "Share %"].forEach(h => eh.appendChild(el("th", { style: { textAlign: h === "Product" ? "left" : "right", padding: "8px", borderBottom: "1px solid " + C.border, color: C.muted, fontSize: "10px" } }, h)));
            etbl.appendChild(el("thead", {}, eh));
            const ebody = el("tbody");
            expProds.forEach(p => { const tr = el("tr", { style: { borderBottom: "1px solid " + C.border + "40" } }); tr.appendChild(el("td", { style: { padding: "6px 8px", color: C.text } }, p)); tr.appendChild(el("td", { style: { textAlign: "right", padding: "6px 8px", color: C.text } }, expProd[p].total.toFixed(1))); tr.appendChild(el("td", { style: { textAlign: "right", padding: "6px 8px", color: C.muted } }, (totalExp > 0 ? (expProd[p].total / totalExp * 100).toFixed(1) : "0") + "%")); ebody.appendChild(tr); });
            etbl.appendChild(ebody);
            explorerContent.appendChild(card("Export Product Breakdown", etbl));
          }

          // Exports by destination chart
          if (expDest && !expDest.error && Object.keys(expDest).length > 0) {
            const dests = Object.keys(expDest);
            const ch2 = el("div", { id: uid + "exdest", style: { width: "100%", height: "380px", marginBottom: "16px" } });
            explorerContent.appendChild(card("Export Destinations (kbd) — Where product goes", ch2));
            try {
              const traces = dests.slice(0, 10).map((d, i) => ({ x: expDest[d].dates, y: expDest[d].values, name: d, stackgroup: "one", line: { color: colors[i], width: 0 }, fillcolor: colors[i] + "40" }));
              Plotly.newPlot(uid + "exdest", traces, ly("kbd"), cfg);
            } catch (e) {}
            // Destination pie
            const ch2p = el("div", { id: uid + "exdpie", style: { width: "100%", height: "350px", marginBottom: "16px" } });
            explorerContent.appendChild(card("Export Destination Share", ch2p));
            try {
              Plotly.newPlot(uid + "exdpie", [{ labels: dests, values: dests.map(d => expDest[d].total), type: "pie", hole: 0.45, textinfo: "label+percent", textfont: { size: 10, color: "#fff" }, marker: { colors: colors } }], { paper_bgcolor: "transparent", plot_bgcolor: "transparent", font: { color: C.text }, margin: { l: 20, r: 20, t: 25, b: 25 }, legend: { font: { size: 10 } } }, cfg);
            } catch (e) {}
          }

          // Imports by product chart
          if (impProds.length > 0) {
            const ch3 = el("div", { id: uid + "imp", style: { width: "100%", height: "380px", marginBottom: "16px" } });
            explorerContent.appendChild(card("Imports / Feedstock by Product (kbd) — What the refinery receives", ch3));
            try {
              const traces = impProds.map((p, i) => ({ x: impProd[p].dates, y: impProd[p].values, name: p, stackgroup: "one", line: { color: colors[i], width: 0 }, fillcolor: colors[i] + "40" }));
              Plotly.newPlot(uid + "imp", traces, ly("kbd"), cfg);
            } catch (e) {}
          }

          // Imports by origin country chart
          if (impOrig && !impOrig.error && Object.keys(impOrig).length > 0) {
            const origins = Object.keys(impOrig);
            const ch4 = el("div", { id: uid + "imporig", style: { width: "100%", height: "380px", marginBottom: "16px" } });
            explorerContent.appendChild(card("Import Origins (kbd) — Which countries supply this refinery", ch4));
            try {
              const traces = origins.slice(0, 12).map((o, i) => ({ x: impOrig[o].dates, y: impOrig[o].values, name: o, stackgroup: "one", line: { color: colors[i], width: 0 }, fillcolor: colors[i] + "40" }));
              Plotly.newPlot(uid + "imporig", traces, ly("kbd"), cfg);
            } catch (e) {}
            // Origin pie
            const ch4p = el("div", { id: uid + "impopie", style: { width: "100%", height: "350px", marginBottom: "16px" } });
            explorerContent.appendChild(card("Import Origin Share", ch4p));
            try {
              Plotly.newPlot(uid + "impopie", [{ labels: origins, values: origins.map(o => impOrig[o].total), type: "pie", hole: 0.45, textinfo: "label+percent", textfont: { size: 10, color: "#fff" }, marker: { colors: colors } }], { paper_bgcolor: "transparent", plot_bgcolor: "transparent", font: { color: C.text }, margin: { l: 20, r: 20, t: 25, b: 25 }, legend: { font: { size: 10 } } }, cfg);
            } catch (e) {}
            // Origin table
            const otbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "12px" } });
            const oh = el("tr"); ["Country", "Total (kbd)", "Share %"].forEach(h => oh.appendChild(el("th", { style: { textAlign: h === "Country" ? "left" : "right", padding: "8px", borderBottom: "1px solid " + C.border, color: C.muted, fontSize: "10px" } }, h)));
            otbl.appendChild(el("thead", {}, oh));
            const obody = el("tbody");
            origins.forEach(o => { const tr = el("tr", { style: { borderBottom: "1px solid " + C.border + "40" } }); tr.appendChild(el("td", { style: { padding: "6px 8px", color: C.text } }, o)); tr.appendChild(el("td", { style: { textAlign: "right", padding: "6px 8px", color: C.text } }, impOrig[o].total.toFixed(1))); tr.appendChild(el("td", { style: { textAlign: "right", padding: "6px 8px", color: C.muted } }, impOrig[o].share_pct.toFixed(1) + "%")); obody.appendChild(tr); });
            otbl.appendChild(obody);
            explorerContent.appendChild(card("Import Origin Breakdown", otbl));
          }

          if (totalExp === 0 && totalImp === 0) {
            explorerContent.appendChild(el("div", { style: { textAlign: "center", padding: "40px", color: C.muted } }, "No trade flow data found for this installation. Try searching for a different name (e.g. add 'Refinery' suffix)."));
          }

        } catch (err) {
          explorerContent.innerHTML = '<div style="text-align:center;padding:40px;color:#ef4444">Error: ' + err.message + '</div>';
        }
      }
    }

    // === REGION VIEW (existing) ===
    // Controls
    const controls = el("div", { style: { display: "flex", alignItems: "center", gap: "10px", marginBottom: "16px", flexWrap: "wrap" } });
    const selStyle = { background: C.card, color: C.text, border: "1px solid " + C.border, borderRadius: "4px", padding: "5px 8px", fontSize: "12px" };

    controls.appendChild(el("span", { style: { fontSize: "11px", color: C.muted } }, "Product:"));
    const prodSel = el("select", { style: selStyle });
    products.forEach(p => { const o = el("option", { value: p }, p); if (p === curProduct) o.selected = true; prodSel.appendChild(o); });
    controls.appendChild(prodSel);

    controls.appendChild(el("span", { style: { fontSize: "11px", color: C.muted, marginLeft: "6px" } }, "Direction:"));
    const dirSel = el("select", { style: selStyle });
    [["export","Exports"],["import","Imports"]].forEach(([v,l]) => { const o = el("option", { value: v }, l); if (v === curDirection) o.selected = true; dirSel.appendChild(o); });
    controls.appendChild(dirSel);

    controls.appendChild(el("span", { style: { fontSize: "11px", color: C.muted, marginLeft: "6px" } }, "Region:"));
    const regSel = el("select", { style: selStyle });
    Object.entries(regions).forEach(([k,v]) => { const o = el("option", { value: k }, v); if (k === curRegion) o.selected = true; regSel.appendChild(o); });
    controls.appendChild(regSel);

    controls.appendChild(el("span", { style: { fontSize: "11px", color: C.muted, marginLeft: "6px" } }, "Period:"));
    const granSel = el("select", { style: selStyle });
    [["monthly","Monthly"],["weekly","Weekly"]].forEach(([v,l]) => { const o = el("option", { value: v }, l); if (v === curGran) o.selected = true; granSel.appendChild(o); });
    controls.appendChild(granSel);

    const loadBtn = el("button", { style: { background: C.amber, color: "#000", border: "none", borderRadius: "4px", padding: "6px 16px", fontWeight: "700", fontSize: "12px", cursor: "pointer", marginLeft: "8px" } }, "LOAD DATA");
    controls.appendChild(loadBtn);
    regionModeBox.appendChild(controls);

    // Content area
    const content = el("div", { id: uid + "content" });
    regionModeBox.appendChild(content);

    // Detail overlay for single installation
    const detailOverlay = el("div", { id: uid + "detail", style: { display: "none" } });
    regionModeBox.appendChild(detailOverlay);

    async function loadData() {
      curProduct = prodSel.value; curDirection = dirSel.value; curRegion = regSel.value; curGran = granSel.value;
      content.innerHTML = '<div style="text-align:center;padding:40px;color:' + C.muted + '">Loading ' + curProduct + ' ' + curDirection + 's from ' + (regions[curRegion] || curRegion) + '...</div>';
      detailOverlay.style.display = "none";
      detailOverlay.innerHTML = "";

      try {
        const resp = await fetch("/api/kpler/refinery_flows?product=" + encodeURIComponent(curProduct) + "&direction=" + curDirection + "&region=" + encodeURIComponent(curRegion) + "&granularity=" + curGran + "&start_date=2024-01-01&end_date=2026-12-31");
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        content.innerHTML = "";

        if (!data.installations || data.installations.length === 0) {
          content.innerHTML = '<div style="text-align:center;padding:40px;color:' + C.muted + '">No data available for this selection.</div>';
          return;
        }

        // Briefing header
        const dirLabel = curDirection === "export" ? "Exports" : "Imports";
        const instLabel = curDirection === "export" ? "Exporting Installations" : "Source Installations (foreign refineries)";
        const totalLatest = data.summary.reduce((s, r) => s + (r.latest || 0), 0);
        const totalAvg = data.summary.reduce((s, r) => s + (r.avg || 0), 0);
        const latestDate = data.latest_date || "N/A";
        const hdr = el("div", { style: { marginBottom: "16px" } });
        hdr.appendChild(el("h2", { style: { fontSize: "16px", fontWeight: "700", color: C.amber, margin: "0 0 8px 0" } }, "🚢 " + curProduct + " " + dirLabel + " — " + (regions[curRegion] || curRegion)));
        const badges = el("div", { style: { display: "flex", gap: "12px", flexWrap: "wrap", marginBottom: "12px" } });
        badges.appendChild(el("span", { style: { background: "rgba(245,158,11,0.15)", color: C.amber, padding: "4px 12px", borderRadius: "20px", fontSize: "12px", fontWeight: "600" } }, data.installations.length + " installations"));
        badges.appendChild(el("span", { style: { background: "rgba(16,185,129,0.15)", color: "#10b981", padding: "4px 12px", borderRadius: "20px", fontSize: "12px", fontWeight: "600" } }, "Latest actual: " + totalLatest.toFixed(0) + " kbd (" + latestDate + ")"));
        badges.appendChild(el("span", { style: { background: "rgba(99,102,241,0.15)", color: "#6366f1", padding: "4px 12px", borderRadius: "20px", fontSize: "12px", fontWeight: "600" } }, "Avg: " + totalAvg.toFixed(0) + " kbd"));
        hdr.appendChild(badges);
        content.appendChild(hdr);

        // Chart 1: Top installations bar chart (latest month)
        const ch1 = el("div", { id: uid + "bar", style: { width: "100%", height: "400px", marginBottom: "16px" } });
        content.appendChild(card("Top " + instLabel + " — " + latestDate + " (kbd)", ch1));
        const top15 = data.summary.slice(0, 15);
        try {
          Plotly.newPlot(uid + "bar", [{
            x: top15.map(r => r.installation),
            y: top15.map(r => r.latest),
            type: "bar",
            marker: { color: top15.map((r, i) => colors[i % colors.length]) },
            text: top15.map(r => r.latest.toFixed(1)),
            textposition: "outside",
            textfont: { size: 10, color: C.text },
            hovertemplate: "%{x}<br>%{y:.1f} kbd<extra></extra>",
          }], { ...ly("kbd"), xaxis: { ...ly("").xaxis, tickangle: -35, tickfont: { size: 9 } }, margin: { l: 55, r: 20, t: 25, b: 120 } }, cfg);
        } catch (e) {}

        // Chart 2: Time series — stacked area for top 10
        const ch2 = el("div", { id: uid + "ts", style: { width: "100%", height: "420px", marginBottom: "16px" } });
        content.appendChild(card("Monthly " + dirLabel + " by Installation (kbd)", ch2));
        const top10 = data.installations.slice(0, 10);
        try {
          const traces = top10.map((inst, i) => ({
            x: data.series[inst].dates, y: data.series[inst].values,
            name: inst.length > 25 ? inst.slice(0, 23) + "…" : inst,
            stackgroup: "one", line: { color: colors[i], width: 0 },
            fillcolor: colors[i] + "40",
            hovertemplate: inst + "<br>%{y:.1f} kbd<extra></extra>",
          }));
          Plotly.newPlot(uid + "ts", traces, ly("kbd"), cfg);
        } catch (e) {}

        // Chart 3: Seasonal overlay (total)
        if (data.seasonal && Object.keys(data.seasonal).length > 0) {
          const ch3 = el("div", { id: uid + "seas", style: { width: "100%", height: "380px", marginBottom: "16px" } });
          content.appendChild(card("Seasonal Overlay — Total " + dirLabel + " (kbd)", ch3));
          try {
            const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
            const yrs = Object.keys(data.seasonal).sort();
            const sTraces = yrs.map((yr, i) => ({
              x: data.seasonal[yr].months.map(m => months[m - 1]),
              y: data.seasonal[yr].values,
              name: yr, mode: "lines+markers",
              line: { color: colors[i % colors.length], width: yr === String(new Date().getFullYear()) ? 3 : 1.5, dash: yr === String(new Date().getFullYear()) ? "solid" : "dot" },
              marker: { size: yr === String(new Date().getFullYear()) ? 6 : 3 },
            }));
            Plotly.newPlot(uid + "seas", sTraces, ly("kbd"), cfg);
          } catch (e) {}
        }

        // Chart 4: M/M change for top 10
        const ch4 = el("div", { id: uid + "chg", style: { width: "100%", height: "350px", marginBottom: "16px" } });
        content.appendChild(card("Month-over-Month Change (kbd)", ch4));
        try {
          const chgData = top15.filter(r => r.change !== 0);
          Plotly.newPlot(uid + "chg", [{
            x: chgData.map(r => r.installation),
            y: chgData.map(r => r.change),
            type: "bar",
            marker: { color: chgData.map(r => r.change >= 0 ? "#10b981" : "#ef4444") },
            text: chgData.map(r => (r.change >= 0 ? "+" : "") + r.change.toFixed(1)),
            textposition: "outside",
            textfont: { size: 10, color: C.text },
          }], { ...ly("Change (kbd)"), xaxis: { ...ly("").xaxis, tickangle: -35, tickfont: { size: 9 } }, margin: { l: 55, r: 20, t: 25, b: 120 } }, cfg);
        } catch (e) {}

        // Summary table
        const tblWrap = el("div", { style: { overflowX: "auto", marginBottom: "16px" } });
        const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "12px" } });
        const thead = el("thead");
        const headRow = el("tr");
        ["#", "Installation", "Latest (kbd)", "Average", "Max", "M/M Change", "M/M %", "Total"].forEach(h => {
          headRow.appendChild(el("th", { style: { textAlign: h === "Installation" ? "left" : "right", padding: "8px 10px", borderBottom: "1px solid " + C.border, color: C.muted, fontSize: "10px", fontWeight: "700" } }, h));
        });
        thead.appendChild(headRow); tbl.appendChild(thead);
        const tbody = el("tbody");
        data.summary.forEach((r, i) => {
          const tr = el("tr", { style: { cursor: "pointer", borderBottom: "1px solid " + C.border + "40" }, onClick: () => loadDetail(r.installation) });
          tr.onmouseenter = () => tr.style.background = "rgba(245,158,11,0.08)";
          tr.onmouseleave = () => tr.style.background = "transparent";
          const chColor = r.change >= 0 ? "#10b981" : "#ef4444";
          [
            String(i + 1),
            r.installation,
            r.latest.toFixed(1),
            r.avg.toFixed(1),
            r.max.toFixed(1),
            (r.change >= 0 ? "+" : "") + r.change.toFixed(1),
            (r.change_pct >= 0 ? "+" : "") + r.change_pct.toFixed(1) + "%",
            r.total.toFixed(0),
          ].forEach((v, ci) => {
            const td = el("td", { style: { textAlign: ci === 1 ? "left" : "right", padding: "7px 10px", color: (ci === 5 || ci === 6) ? chColor : C.text, fontSize: "12px" } }, v);
            tr.appendChild(td);
          });
          tbody.appendChild(tr);
        });
        tbl.appendChild(tbody);
        tblWrap.appendChild(tbl);
        content.appendChild(card(instLabel + " Summary (" + latestDate + ") — Click a row for detail", tblWrap));

        // Destination breakdown (only for exports — where the product goes)
        if (curDirection === "export") try {
          const destResp = await fetch("/api/kpler/refinery_destinations?product=" + encodeURIComponent(curProduct) + "&region=" + encodeURIComponent(curRegion) + "&start_date=2024-01-01&end_date=2026-12-31&split_by=DestinationTradingRegions");
          if (destResp.ok) {
            const destData = await destResp.json();
            if (destData.destinations && destData.destinations.length > 0) {
              // Pie chart of destinations
              const ch5 = el("div", { id: uid + "pie", style: { width: "100%", height: "400px", marginBottom: "16px" } });
              content.appendChild(card("Where Do " + (regions[curRegion] || curRegion) + " " + curProduct + " " + dirLabel + " Go? (excl. intra-region)", ch5));
              try {
                Plotly.newPlot(uid + "pie", [{
                  labels: destData.summary.map(r => r.destination),
                  values: destData.summary.map(r => r.total),
                  type: "pie",
                  hole: 0.45,
                  textinfo: "label+percent",
                  textfont: { size: 10, color: "#fff" },
                  marker: { colors: colors },
                  hovertemplate: "%{label}<br>%{value:.0f} kbd total<br>%{percent}<extra></extra>",
                }], { paper_bgcolor: "transparent", plot_bgcolor: "transparent", font: { color: C.text, size: 11 }, margin: { l: 20, r: 20, t: 25, b: 25 }, legend: { font: { size: 10 } }, showlegend: true }, cfg);
              } catch (e) {}

              // Stacked area of destination time series
              const ch6 = el("div", { id: uid + "destts", style: { width: "100%", height: "400px", marginBottom: "16px" } });
              content.appendChild(card(curProduct + " " + dirLabel + " by Destination Region (kbd)", ch6));
              try {
                const dTraces = destData.destinations.slice(0, 8).map((dest, i) => ({
                  x: destData.series[dest].dates, y: destData.series[dest].values,
                  name: dest, stackgroup: "one",
                  line: { color: colors[i], width: 0 },
                  fillcolor: colors[i] + "40",
                }));
                Plotly.newPlot(uid + "destts", dTraces, ly("kbd"), cfg);
              } catch (e) {}

              // Destination table
              const dtWrap = el("div", { style: { overflowX: "auto" } });
              const dtbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "12px" } });
              const dhead = el("thead");
              const dhRow = el("tr");
              ["Destination", "Latest (kbd)", "Average", "Total", "Share %"].forEach(h => {
                dhRow.appendChild(el("th", { style: { textAlign: h === "Destination" ? "left" : "right", padding: "8px 10px", borderBottom: "1px solid " + C.border, color: C.muted, fontSize: "10px", fontWeight: "700" } }, h));
              });
              dhead.appendChild(dhRow); dtbl.appendChild(dhead);
              const dbody = el("tbody");
              destData.summary.forEach(r => {
                const tr = el("tr", { style: { borderBottom: "1px solid " + C.border + "40" } });
                [r.destination, r.latest.toFixed(1), r.avg.toFixed(1), r.total.toFixed(0), r.share_pct.toFixed(1) + "%"].forEach((v, ci) => {
                  tr.appendChild(el("td", { style: { textAlign: ci === 0 ? "left" : "right", padding: "7px 10px", color: C.text, fontSize: "12px" } }, v));
                });
                dbody.appendChild(tr);
              });
              dtbl.appendChild(dbody);
              dtWrap.appendChild(dtbl);
              content.appendChild(card("Destination Breakdown", dtWrap));
            }
          }
        } catch (e) {}

      } catch (err) {
        content.innerHTML = '<div style="text-align:center;padding:40px;color:#ef4444">Error: ' + err.message + '</div>';
      }
    }

    async function loadDetail(installation) {
      detailOverlay.style.display = "block";
      detailOverlay.innerHTML = '<div style="text-align:center;padding:30px;color:' + C.muted + '">Loading detail for ' + installation + '...</div>';
      content.style.display = "none";

      try {
        const resp = await fetch("/api/kpler/refinery_detail?installation=" + encodeURIComponent(installation) + "&start_date=2024-01-01&end_date=2026-12-31");
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const detail = await resp.json();
        detailOverlay.innerHTML = "";

        const backBtn = el("button", { style: { background: C.card, color: C.amber, border: "1px solid " + C.border, borderRadius: "4px", padding: "6px 14px", fontSize: "12px", fontWeight: "600", cursor: "pointer", marginBottom: "16px" }, onClick: () => { detailOverlay.style.display = "none"; detailOverlay.innerHTML = ""; content.style.display = "block"; } }, "← Back to Overview");
        detailOverlay.appendChild(backBtn);
        detailOverlay.appendChild(el("h2", { style: { fontSize: "16px", fontWeight: "700", color: C.amber, margin: "0 0 16px 0" } }, "🏭 " + installation));

        // Exports by product
        const expProd = detail.data.exports_by_product;
        if (expProd && !expProd.error) {
          const prods = Object.keys(expProd);
          if (prods.length > 0) {
            const ch = el("div", { id: uid + "dp", style: { width: "100%", height: "380px", marginBottom: "16px" } });
            detailOverlay.appendChild(card("Exports by Product (kbd)", ch));
            try {
              const traces = prods.map((p, i) => ({
                x: expProd[p].dates, y: expProd[p].values,
                name: p, stackgroup: "one",
                line: { color: colors[i], width: 0 }, fillcolor: colors[i] + "40",
              }));
              Plotly.newPlot(uid + "dp", traces, ly("kbd"), cfg);
            } catch (e) {}

            // Product pie
            const pie = el("div", { id: uid + "dpp", style: { width: "100%", height: "350px", marginBottom: "16px" } });
            detailOverlay.appendChild(card("Export Product Mix", pie));
            try {
              Plotly.newPlot(uid + "dpp", [{
                labels: prods, values: prods.map(p => expProd[p].total),
                type: "pie", hole: 0.45, textinfo: "label+percent",
                marker: { colors: colors },
                textfont: { size: 10, color: "#fff" },
              }], { paper_bgcolor: "transparent", plot_bgcolor: "transparent", font: { color: C.text }, margin: { l: 20, r: 20, t: 25, b: 25 }, legend: { font: { size: 10 } } }, cfg);
            } catch (e) {}
          }
        }

        // Exports by destination
        const expDest = detail.data.exports_by_destination;
        if (expDest && !expDest.error) {
          const dests = Object.keys(expDest);
          if (dests.length > 0) {
            const ch = el("div", { id: uid + "dd", style: { width: "100%", height: "380px", marginBottom: "16px" } });
            detailOverlay.appendChild(card("Export Destinations (kbd)", ch));
            try {
              const traces = dests.slice(0, 10).map((d, i) => ({
                x: expDest[d].dates, y: expDest[d].values,
                name: d, stackgroup: "one",
                line: { color: colors[i], width: 0 }, fillcolor: colors[i] + "40",
              }));
              Plotly.newPlot(uid + "dd", traces, ly("kbd"), cfg);
            } catch (e) {}

            // Destination table
            const dtWrap = el("div", { style: { overflowX: "auto" } });
            const dtbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "12px" } });
            const dh = el("tr");
            ["Country", "Total (kbd)", "Share %"].forEach(h => {
              dh.appendChild(el("th", { style: { textAlign: h === "Country" ? "left" : "right", padding: "8px 10px", borderBottom: "1px solid " + C.border, color: C.muted, fontSize: "10px", fontWeight: "700" } }, h));
            });
            dtbl.appendChild(el("thead", {}, dh));
            const dbody = el("tbody");
            dests.forEach(d => {
              const tr = el("tr", { style: { borderBottom: "1px solid " + C.border + "40" } });
              tr.appendChild(el("td", { style: { padding: "7px 10px", color: C.text, fontSize: "12px" } }, d));
              tr.appendChild(el("td", { style: { textAlign: "right", padding: "7px 10px", color: C.text, fontSize: "12px" } }, expDest[d].total.toFixed(0)));
              tr.appendChild(el("td", { style: { textAlign: "right", padding: "7px 10px", color: C.text, fontSize: "12px" } }, expDest[d].share_pct.toFixed(1) + "%"));
              dbody.appendChild(tr);
            });
            dtbl.appendChild(dbody);
            dtWrap.appendChild(dtbl);
            detailOverlay.appendChild(card("Destination Breakdown", dtWrap));
          }
        }

        // Imports by product
        const impProd = detail.data.imports_by_product;
        if (impProd && !impProd.error) {
          const prods = Object.keys(impProd);
          if (prods.length > 0) {
            const ch = el("div", { id: uid + "di", style: { width: "100%", height: "380px", marginBottom: "16px" } });
            detailOverlay.appendChild(card("Imports / Feedstock by Product (kbd)", ch));
            try {
              const traces = prods.map((p, i) => ({
                x: impProd[p].dates, y: impProd[p].values,
                name: p, stackgroup: "one",
                line: { color: colors[i], width: 0 }, fillcolor: colors[i] + "40",
              }));
              Plotly.newPlot(uid + "di", traces, ly("kbd"), cfg);
            } catch (e) {}
          }
        }

      } catch (err) {
        detailOverlay.innerHTML = '<div style="text-align:center;padding:40px;color:#ef4444">Error loading detail: ' + err.message + '</div>';
      }
    }

    loadBtn.onclick = loadData;
    loadData();
  }


  // ==========================================================================
  // Kpler Inventories Tab
  // ==========================================================================
  async function renderKINV(box) {
    box.innerHTML = "";
    const uid = "kinv-" + Date.now() + "-";
    const ly = (yTitle, opts = {}) => ({
      paper_bgcolor: "transparent", plot_bgcolor: "transparent",
      font: { color: C.text, size: 11 }, margin: { l: 70, r: opts.r || 20, t: 30, b: 50 },
      xaxis: { gridcolor: "#1e293b", linecolor: "#334155", tickfont: { size: 10 } },
      yaxis: { title: yTitle, gridcolor: "#1e293b", linecolor: "#334155", tickfont: { size: 10 }, zeroline: true, zerolinecolor: "#334155" },
      ...(opts.yaxis2 ? { yaxis2: opts.yaxis2 } : {}),
      legend: { orientation: "h", x: 0, y: -0.15, font: { size: 10 } }, hovermode: "x unified",
    });
    const cfg = { responsive: true, displayModeBar: false };
    const colors = ["#f59e0b","#6366f1","#10b981","#ef4444","#06b6d4","#8b5cf6","#f97316","#ec4899","#14b8a6","#eab308","#a855f7","#84cc16"];

    const defaultZones = ["United States", "China", "Singapore Republic", "Greater ARA", "Japan", "India", "South Korea", "Fujairah"];

    box.appendChild(el("h2", { style: { fontSize: "16px", fontWeight: "700", color: C.amber, margin: "0 0 12px 0" } }, "🛢️ Global Inventories"));
    box.appendChild(el("p", { style: { fontSize: "12px", color: C.muted, margin: "0 0 16px 0" } }, "Crude: Kpler satellite-tracked storage. Gasoline: EIA weekly stocks (US) + global hub data."));

    // Product toggle
    let curInvProduct = "crude";
    const prodRow = el("div", { style: { display: "flex", gap: "4px", marginBottom: "12px" } });
    const crdBtn = el("button", { style: { padding: "8px 20px", background: C.amber, color: "#000", border: "none", borderRadius: "4px 0 0 4px", fontSize: "12px", fontWeight: "700", cursor: "pointer" } }, "🛢️ Crude Oil");
    const gasBtn = el("button", { style: { padding: "8px 20px", background: C.card, color: C.muted, border: "1px solid " + C.border, borderRadius: "0 4px 4px 0", fontSize: "12px", fontWeight: "600", cursor: "pointer" } }, "⛽ Gasoline");
    prodRow.appendChild(crdBtn); prodRow.appendChild(gasBtn);
    box.appendChild(prodRow);

    crdBtn.onclick = () => { curInvProduct = "crude"; crdBtn.style.background = C.amber; crdBtn.style.color = "#000"; gasBtn.style.background = C.card; gasBtn.style.color = C.muted; loadInventories(); };
    gasBtn.onclick = () => { curInvProduct = "gasoline"; gasBtn.style.background = C.amber; gasBtn.style.color = "#000"; crdBtn.style.background = C.card; crdBtn.style.color = C.muted; loadGasolineStocks(); };

    // Controls
    const controls = el("div", { style: { display: "flex", alignItems: "center", gap: "10px", marginBottom: "16px", flexWrap: "wrap" } });
    const selStyle = { background: C.card, color: C.text, border: "1px solid " + C.border, borderRadius: "4px", padding: "5px 8px", fontSize: "12px" };
    controls.appendChild(el("span", { style: { fontSize: "11px", color: C.muted } }, "Period:"));
    const periodSel = el("select", { style: selStyle });
    [["weekly","Weekly"],["daily","Daily"],["monthly","Monthly"]].forEach(([v,l]) => { const o = el("option", { value: v }, l); if (v === "weekly") o.selected = true; periodSel.appendChild(o); });
    controls.appendChild(periodSel);
    controls.appendChild(el("span", { style: { fontSize: "11px", color: C.muted, marginLeft: "8px" } }, "Start:"));
    const startInput = el("input", { type: "date", value: "2025-01-01", style: { ...selStyle, padding: "4px 6px" } });
    controls.appendChild(startInput);
    const loadBtn = el("button", { style: { background: C.amber, color: "#000", border: "none", borderRadius: "4px", padding: "6px 16px", fontWeight: "700", fontSize: "12px", cursor: "pointer", marginLeft: "8px" } }, "LOAD");
    controls.appendChild(loadBtn);
    box.appendChild(controls);

    const content = el("div", {});
    box.appendChild(content);

    async function loadInventories() {
      content.innerHTML = '<div style="text-align:center;padding:40px;color:' + C.muted + '">Loading inventories from Kpler satellite data...</div>';
      const period = periodSel.value;
      const sd = startInput.value || "2025-01-01";
      try {
        // Load multi-zone comparison
        const resp = await fetch("/api/kpler/inventories_multi?zones=" + encodeURIComponent(defaultZones.join(",")) + "&period=" + period + "&start_date=" + sd);
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        content.innerHTML = "";

        // Summary cards
        const cardsRow = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "12px", marginBottom: "16px" } });
        const zoneNames = Object.keys(data.zones);
        zoneNames.forEach((zone, i) => {
          const z = data.zones[zone];
          const cardEl = el("div", { style: { background: C.card, border: "1px solid " + C.border, borderRadius: "8px", padding: "12px", cursor: "pointer" }, onClick: () => loadZoneDetail(zone) });
          cardEl.onmouseenter = () => cardEl.style.borderColor = C.amber;
          cardEl.onmouseleave = () => cardEl.style.borderColor = C.border;
          cardEl.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, marginBottom: "4px" } }, zone));
          cardEl.appendChild(el("div", { style: { fontSize: "18px", fontWeight: "700", color: colors[i % colors.length] } }, (z.latest_level / 1000).toFixed(1) + " mb"));
          const fillColor = z.latest_fill > 70 ? "#ef4444" : z.latest_fill > 50 ? "#f59e0b" : "#10b981";
          cardEl.appendChild(el("div", { style: { fontSize: "11px", color: fillColor, marginTop: "2px" } }, "Fill: " + z.latest_fill.toFixed(1) + "% | Cap: " + (z.latest_capacity / 1000).toFixed(1) + " mb"));
          // Mini fill bar
          const bar = el("div", { style: { height: "4px", background: "#1e293b", borderRadius: "2px", marginTop: "6px" } });
          bar.appendChild(el("div", { style: { height: "100%", width: z.latest_fill + "%", background: fillColor, borderRadius: "2px" } }));
          cardEl.appendChild(bar);
          cardsRow.appendChild(cardEl);
        });
        content.appendChild(cardsRow);

        // Chart 1: All zones inventory levels
        const ch1 = el("div", { id: uid + "levels", style: { width: "100%", height: "420px", marginBottom: "16px" } });
        content.appendChild(card("Crude Oil Inventory Levels by Hub (mb)", ch1));
        try {
          const traces = zoneNames.map((zone, i) => ({
            x: data.zones[zone].dates,
            y: data.zones[zone].levels.map(v => v / 1000),
            name: zone.replace(" Republic", "").replace("Greater ", ""),
            mode: "lines",
            line: { color: colors[i % colors.length], width: 2 },
          }));
          Plotly.newPlot(uid + "levels", traces, { ...ly("Level (mb)"), legend: { orientation: "h", x: 0, y: 1.1, font: { size: 10 } } }, cfg);
        } catch (e) {}

        // Chart 2: Fill % comparison
        const ch2 = el("div", { id: uid + "fill", style: { width: "100%", height: "380px", marginBottom: "16px" } });
        content.appendChild(card("Capacity Utilization (%) — All Hubs", ch2));
        try {
          const traces = zoneNames.map((zone, i) => ({
            x: data.zones[zone].dates,
            y: data.zones[zone].fill_pcts,
            name: zone.replace(" Republic", "").replace("Greater ", ""),
            mode: "lines",
            line: { color: colors[i % colors.length], width: 2 },
          }));
          Plotly.newPlot(uid + "fill", traces, { ...ly("Fill %"), shapes: [{ type: "line", x0: 0, x1: 1, xref: "paper", y0: 60, y1: 60, line: { color: "#f59e0b", width: 1, dash: "dot" } }] }, cfg);
        } catch (e) {}

        // Chart 3: Latest snapshot bar chart
        const ch3 = el("div", { id: uid + "snap", style: { width: "100%", height: "350px", marginBottom: "16px" } });
        content.appendChild(card("Latest Inventory Snapshot (mb) — Click a bar for detail", ch3));
        try {
          Plotly.newPlot(uid + "snap", [{
            x: zoneNames.map(z => z.replace(" Republic", "").replace("Greater ", "")),
            y: zoneNames.map(z => data.zones[z].latest_level / 1000),
            type: "bar",
            marker: { color: zoneNames.map((_, i) => colors[i % colors.length]) },
            text: zoneNames.map(z => (data.zones[z].latest_level / 1000).toFixed(1)),
            textposition: "outside",
            textfont: { size: 10, color: C.text },
          }], { ...ly("Level (mb)"), margin: { l: 55, r: 20, t: 25, b: 100 }, xaxis: { tickangle: -25, tickfont: { size: 10 }, gridcolor: "#1e293b" } }, cfg);
        } catch (e) {}

        // Cushing drone data
        try {
          const cushResp = await fetch("/api/kpler/cushing_drone?start_date=" + sd);
          if (cushResp.ok) {
            const cushData = await cushResp.json();
            if (cushData.data && cushData.data.length > 0) {
              const ch4 = el("div", { id: uid + "cushing", style: { width: "100%", height: "350px", marginBottom: "16px" } });
              content.appendChild(card("Cushing, OK — Drone Survey (Weekly)", ch4));
              try {
                Plotly.newPlot(uid + "cushing", [
                  { x: cushData.data.map(r => r.date), y: cushData.data.map(r => r.level_kb / 1000), name: "Level (mb)", type: "scatter", mode: "lines", line: { color: "#f59e0b", width: 2 }, fill: "tozeroy", fillcolor: "rgba(245,158,11,0.1)" },
                  { x: cushData.data.map(r => r.date), y: cushData.data.map(r => r.capacity_kb / 1000), name: "Capacity (mb)", type: "scatter", mode: "lines", line: { color: "#64748b", width: 1, dash: "dot" }, yaxis: "y" },
                ], { ...ly("mb"), legend: { orientation: "h", x: 0, y: 1.05, font: { size: 10 } } }, cfg);
              } catch (e) {}
            }
          }
        } catch (e) {}

        // Summary table
        const tblWrap = el("div", { style: { overflowX: "auto" } });
        const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "12px" } });
        const thead = el("thead");
        const headRow = el("tr");
        ["Hub", "Level (mb)", "Capacity (mb)", "Fill %", "Local Supply (kbd)", "Local Demand (kbd)", "Cargoes (kbd)"].forEach(h => {
          headRow.appendChild(el("th", { style: { textAlign: h === "Hub" ? "left" : "right", padding: "8px 10px", borderBottom: "1px solid " + C.border, color: C.muted, fontSize: "10px", fontWeight: "700" } }, h));
        });
        thead.appendChild(headRow); tbl.appendChild(thead);
        const tbody = el("tbody");
        // For table data, load each zone individually to get flow metrics
        for (const zone of zoneNames) {
          const tr = el("tr", { style: { cursor: "pointer", borderBottom: "1px solid " + C.border + "40" }, onClick: () => loadZoneDetail(zone) });
          tr.onmouseenter = () => tr.style.background = "rgba(245,158,11,0.08)";
          tr.onmouseleave = () => tr.style.background = "transparent";
          const zd = data.zones[zone];
          const lvl = (zd.latest_level / 1000).toFixed(1);
          const cap = (zd.latest_capacity / 1000).toFixed(1);
          const fill = zd.latest_fill.toFixed(1) + "%";
          [zone, lvl, cap, fill, "—", "—", "—"].forEach((v, ci) => {
            tr.appendChild(el("td", { style: { textAlign: ci === 0 ? "left" : "right", padding: "7px 10px", color: C.text, fontSize: "12px" } }, v));
          });
          tbody.appendChild(tr);
        }
        tbl.appendChild(tbody);
        tblWrap.appendChild(tbl);
        content.appendChild(card("Global Inventory Summary — Click row for detail", tblWrap));

      } catch (err) {
        content.innerHTML = '<div style="text-align:center;padding:40px;color:#ef4444">Error: ' + err.message + '</div>';
      }
    }

    async function loadZoneDetail(zone) {
      content.innerHTML = '<div style="text-align:center;padding:40px;color:' + C.muted + '">Loading detail for ' + zone + '...</div>';
      const period = periodSel.value;
      const sd = startInput.value || "2025-01-01";
      try {
        const resp = await fetch("/api/kpler/inventories?zone=" + encodeURIComponent(zone) + "&period=" + period + "&start_date=" + sd + "&split=total");
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        content.innerHTML = "";

        // Back button
        const backBtn = el("button", { style: { background: C.card, color: C.amber, border: "1px solid " + C.border, borderRadius: "4px", padding: "6px 14px", fontSize: "12px", fontWeight: "600", cursor: "pointer", marginBottom: "16px" }, onClick: loadInventories }, "← Back to Overview");
        content.appendChild(backBtn);
        content.appendChild(el("h2", { style: { fontSize: "16px", fontWeight: "700", color: C.amber, margin: "0 0 16px 0" } }, "🛢️ " + zone + " — Inventory Detail"));

        // Summary badges
        if (data.data && data.data.length > 0) {
          const latest = data.data[data.data.length - 1];
          const badges = el("div", { style: { display: "flex", gap: "12px", flexWrap: "wrap", marginBottom: "16px" } });
          badges.appendChild(el("span", { style: { background: "rgba(245,158,11,0.15)", color: C.amber, padding: "4px 12px", borderRadius: "20px", fontSize: "12px", fontWeight: "600" } }, "Level: " + (latest.level_kb / 1000).toFixed(1) + " mb"));
          badges.appendChild(el("span", { style: { background: "rgba(99,102,241,0.15)", color: "#6366f1", padding: "4px 12px", borderRadius: "20px", fontSize: "12px", fontWeight: "600" } }, "Capacity: " + (latest.capacity_kb / 1000).toFixed(1) + " mb"));
          const fillColor = latest.fill_pct > 70 ? "#ef4444" : latest.fill_pct > 50 ? "#f59e0b" : "#10b981";
          badges.appendChild(el("span", { style: { background: `rgba(${fillColor === "#ef4444" ? "239,68,68" : fillColor === "#f59e0b" ? "245,158,11" : "16,185,129"},0.15)`, color: fillColor, padding: "4px 12px", borderRadius: "20px", fontSize: "12px", fontWeight: "600" } }, "Fill: " + latest.fill_pct.toFixed(1) + "%"));
          if (latest.cargoes_kbd) badges.appendChild(el("span", { style: { background: "rgba(6,182,212,0.15)", color: "#06b6d4", padding: "4px 12px", borderRadius: "20px", fontSize: "12px", fontWeight: "600" } }, "Cargoes: " + latest.cargoes_kbd.toFixed(1) + " kbd"));
          content.appendChild(badges);

          // Level chart
          const ch1 = el("div", { id: uid + "zl", style: { width: "100%", height: "380px", marginBottom: "16px" } });
          content.appendChild(card(zone + " — Inventory Level (mb)", ch1));
          try {
            Plotly.newPlot(uid + "zl", [
              { x: data.data.map(r => r.date), y: data.data.map(r => r.level_kb / 1000), name: "Level", type: "scatter", mode: "lines", line: { color: "#f59e0b", width: 2 }, fill: "tozeroy", fillcolor: "rgba(245,158,11,0.1)" },
              { x: data.data.map(r => r.date), y: data.data.map(r => r.capacity_kb / 1000), name: "Capacity", type: "scatter", mode: "lines", line: { color: "#64748b", width: 1, dash: "dot" } },
            ], ly("mb"), cfg);
          } catch (e) {}

          // Fill % chart
          const ch2 = el("div", { id: uid + "zf", style: { width: "100%", height: "320px", marginBottom: "16px" } });
          content.appendChild(card(zone + " — Utilization (%)", ch2));
          try {
            Plotly.newPlot(uid + "zf", [{
              x: data.data.map(r => r.date), y: data.data.map(r => r.fill_pct),
              type: "scatter", mode: "lines", line: { color: "#10b981", width: 2 },
              fill: "tozeroy", fillcolor: "rgba(16,185,129,0.1)",
            }], { ...ly("Fill %"), shapes: [{ type: "line", x0: 0, x1: 1, xref: "paper", y0: 60, y1: 60, line: { color: "#f59e0b", width: 1, dash: "dot" } }] }, cfg);
          } catch (e) {}

          // Flows chart (supply, demand, cargoes)
          const hasFlows = data.data.some(r => r.local_supply_kbd || r.local_demand_kbd || r.cargoes_kbd);
          if (hasFlows) {
            const ch3 = el("div", { id: uid + "zfl", style: { width: "100%", height: "350px", marginBottom: "16px" } });
            content.appendChild(card(zone + " — Flow Metrics (kbd)", ch3));
            try {
              Plotly.newPlot(uid + "zfl", [
                { x: data.data.map(r => r.date), y: data.data.map(r => r.local_supply_kbd), name: "Local Supply", type: "scatter", mode: "lines", line: { color: "#10b981", width: 2 } },
                { x: data.data.map(r => r.date), y: data.data.map(r => r.local_demand_kbd), name: "Local Demand", type: "scatter", mode: "lines", line: { color: "#ef4444", width: 2 } },
                { x: data.data.map(r => r.date), y: data.data.map(r => r.cargoes_kbd), name: "Net Cargoes", type: "bar", marker: { color: data.data.map(r => r.cargoes_kbd >= 0 ? "rgba(6,182,212,0.6)" : "rgba(239,68,68,0.6)") } },
              ], ly("kbd"), cfg);
            } catch (e) {}
          }

          // Data table
          const tblWrap = el("div", { style: { overflowX: "auto", maxHeight: "400px", overflowY: "auto" } });
          const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px" } });
          const th = el("tr");
          ["Date", "Level (mb)", "Capacity (mb)", "Fill %", "Supply (kbd)", "Demand (kbd)", "Cargoes (kbd)"].forEach(h => th.appendChild(el("th", { style: { textAlign: h === "Date" ? "left" : "right", padding: "6px 8px", borderBottom: "1px solid " + C.border, color: C.muted, fontSize: "10px", position: "sticky", top: 0, background: "#0f172a" } }, h)));
          tbl.appendChild(el("thead", {}, th));
          const tbody = el("tbody");
          data.data.slice().reverse().forEach(r => {
            const tr = el("tr", { style: { borderBottom: "1px solid " + C.border + "20" } });
            [r.date, (r.level_kb/1000).toFixed(1), (r.capacity_kb/1000).toFixed(1), r.fill_pct.toFixed(1)+"%", r.local_supply_kbd.toFixed(1), r.local_demand_kbd.toFixed(1), r.cargoes_kbd.toFixed(1)].forEach((v, ci) => {
              tr.appendChild(el("td", { style: { textAlign: ci === 0 ? "left" : "right", padding: "5px 8px", color: C.text, fontSize: "11px" } }, v));
            });
            tbody.appendChild(tr);
          });
          tbl.appendChild(tbody);
          tblWrap.appendChild(tbl);
          content.appendChild(card("Historical Data", tblWrap));
        }
      } catch (err) {
        content.innerHTML = '<div style="text-align:center;padding:40px;color:#ef4444">Error: ' + err.message + '</div>';
      }
    }

    async function loadGasolineStocks() {
      content.innerHTML = '<div style="text-align:center;padding:40px;color:' + C.muted + '">Loading EIA weekly gasoline stocks...</div>';
      const sd = startInput.value || "2020-01-01";
      try {
        const resp = await fetch("/api/eia_gasoline_stocks?start=" + sd);
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        content.innerHTML = "";

        content.appendChild(el("h3", { style: { fontSize: "14px", fontWeight: "700", color: "#10b981", margin: "0 0 12px 0" } }, "⛽ US Gasoline Stocks — EIA Weekly"));

        const products = data.products || {};
        const summary = data.summary || {};
        const paddData = data.padd_data || {};
        const latestDate = data.latest_date || "";

        // EPM0 = Total Motor Gasoline in products dict
        const totalProd = products["EPM0"];

        // Summary cards: US total + PADD breakdown
        const cardsRow = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "12px", marginBottom: "16px" } });
        const paddNames = { "U.S.": "🇺🇸 Total US", "PADD 1": "East Coast", "PADD 2": "Midwest", "PADD 3": "Gulf Coast", "PADD 4": "Rocky Mountain", "PADD 5": "West Coast" };
        const paddColorsMap = { "U.S.": "#f59e0b", "PADD 1": "#6366f1", "PADD 2": "#10b981", "PADD 3": "#ef4444", "PADD 4": "#06b6d4", "PADD 5": "#8b5cf6" };
        // US total card
        if (summary["EPM0"]) {
          const sm = summary["EPM0"];
          const cardEl = el("div", { style: { background: C.card, border: "1px solid " + C.border, borderRadius: "8px", padding: "12px" } });
          cardEl.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, marginBottom: "4px" } }, "🇺🇸 Total US (" + latestDate + ")"));
          cardEl.appendChild(el("div", { style: { fontSize: "18px", fontWeight: "700", color: "#f59e0b" } }, (sm.latest / 1000).toFixed(1) + " mb"));
          const chgColor = sm.change >= 0 ? "#10b981" : "#ef4444";
          cardEl.appendChild(el("div", { style: { fontSize: "11px", color: chgColor, marginTop: "2px" } }, (sm.change >= 0 ? "▲ +" : "▼ ") + (sm.change / 1000).toFixed(2) + " mb w/w"));
          const avgColor = sm.diff_from_avg >= 0 ? "#10b981" : "#ef4444";
          cardEl.appendChild(el("div", { style: { fontSize: "10px", color: avgColor, marginTop: "2px" } }, "vs 5yr avg: " + (sm.diff_from_avg >= 0 ? "+" : "") + (sm.diff_from_avg / 1000).toFixed(1) + " mb (" + (sm.pct_diff_from_avg >= 0 ? "+" : "") + sm.pct_diff_from_avg.toFixed(1) + "%)"));
          cardsRow.appendChild(cardEl);
        }
        // PADD cards
        Object.keys(paddData).forEach((area, i) => {
          const pd = paddData[area];
          const cardEl = el("div", { style: { background: C.card, border: "1px solid " + C.border, borderRadius: "8px", padding: "12px" } });
          cardEl.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, marginBottom: "4px" } }, paddNames[area] || area));
          cardEl.appendChild(el("div", { style: { fontSize: "18px", fontWeight: "700", color: paddColorsMap[area] || colors[i] } }, (pd.latest / 1000).toFixed(1) + " mb"));
          if (pd.change !== null) {
            const chgColor = pd.change >= 0 ? "#10b981" : "#ef4444";
            cardEl.appendChild(el("div", { style: { fontSize: "11px", color: chgColor, marginTop: "2px" } }, (pd.change >= 0 ? "▲ +" : "▼ ") + (pd.change / 1000).toFixed(2) + " mb w/w"));
          }
          cardsRow.appendChild(cardEl);
        });
        content.appendChild(cardsRow);

        // Chart 1: Total US Gasoline Stocks time series
        if (totalProd) {
          const ch1 = el("div", { id: uid + "gastot", style: { width: "100%", height: "380px", marginBottom: "16px" } });
          content.appendChild(card("Total US Motor Gasoline Stocks (mb)", ch1));
          try {
            Plotly.newPlot(uid + "gastot", [{
              x: totalProd.dates, y: totalProd.values.map(v => v !== null ? v / 1000 : null), name: "Total Gasoline",
              type: "scatter", mode: "lines", line: { color: "#f59e0b", width: 2 },
              fill: "tozeroy", fillcolor: "rgba(245,158,11,0.1)",
            }], ly("Stocks (mb)"), cfg);
          } catch (e) {}
        }

        // Chart 2: PADD breakdown
        const paddTraces = [];
        const paddAreas = Object.keys(paddData);
        paddAreas.forEach((area, i) => {
          const pd = paddData[area];
          if (!pd.values) return;
          paddTraces.push({
            x: pd.dates, y: pd.values.map(v => v !== null ? v / 1000 : null), name: paddNames[area] || area,
            stackgroup: "one", line: { color: paddColorsMap[area] || colors[i], width: 0 },
            fillcolor: (paddColorsMap[area] || colors[i]) + "40",
          });
        });
        if (paddTraces.length > 0) {
          const ch2 = el("div", { id: uid + "gaspadd", style: { width: "100%", height: "380px", marginBottom: "16px" } });
          content.appendChild(card("Gasoline Stocks by PADD Region (mb)", ch2));
          try { Plotly.newPlot(uid + "gaspadd", paddTraces, ly("Stocks (mb)"), cfg); } catch (e) {}
        }

        // Chart 3: Seasonal overlay (year over year)
        if (totalProd) {
          const ch3 = el("div", { id: uid + "gasseas", style: { width: "100%", height: "380px", marginBottom: "16px" } });
          content.appendChild(card("Seasonal Overlay — Total US Gasoline Stocks (mb)", ch3));
          try {
            const byYear = {};
            totalProd.dates.forEach((d, i) => {
              if (!d || totalProd.values[i] === null) return;
              const yr = d.substring(0, 4);
              if (!byYear[yr]) byYear[yr] = { dates: [], vals: [] };
              byYear[yr].dates.push(d.substring(5));
              byYear[yr].vals.push(totalProd.values[i] / 1000);
            });
            const years = Object.keys(byYear).sort();
            const traces = years.map((yr, i) => ({
              x: byYear[yr].dates, y: byYear[yr].vals, name: yr,
              mode: "lines", line: { color: colors[i % colors.length], width: yr === years[years.length - 1] ? 3 : 1.5, dash: yr === years[years.length - 1] ? "solid" : "dot" },
            }));
            Plotly.newPlot(uid + "gasseas", traces, { ...ly("Stocks (mb)"), xaxis: { title: "Week", gridcolor: "#1e293b", tickfont: { size: 10 } } }, cfg);
          } catch (e) {}
        }

        // Chart 4: Finished vs Blending Components
        const finProd = products["EPM0F"];
        const blendProd = products["EPOBG"];
        if (finProd && blendProd) {
          const ch4 = el("div", { id: uid + "gasfb", style: { width: "100%", height: "350px", marginBottom: "16px" } });
          content.appendChild(card("Finished Gasoline vs Blending Components (mb)", ch4));
          try {
            Plotly.newPlot(uid + "gasfb", [
              { x: finProd.dates, y: finProd.values.map(v => v !== null ? v / 1000 : null), name: "Finished Gasoline", type: "scatter", mode: "lines", line: { color: "#10b981", width: 2 } },
              { x: blendProd.dates, y: blendProd.values.map(v => v !== null ? v / 1000 : null), name: "Blending Components", type: "scatter", mode: "lines", line: { color: "#6366f1", width: 2 } },
            ], ly("Stocks (mb)"), cfg);
          } catch (e) {}
        }

        // Weekly change table
        if (totalProd) {
          const tblWrap = el("div", { style: { overflowX: "auto", maxHeight: "400px", overflowY: "auto" } });
          const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "11px" } });
          const th = el("tr");
          ["Date", "Total (mb)", "W/W Change (mb)", "W/W %"].forEach(h => th.appendChild(el("th", { style: { textAlign: h === "Date" ? "left" : "right", padding: "6px 8px", borderBottom: "1px solid " + C.border, color: C.muted, fontSize: "10px", position: "sticky", top: 0, background: "#0f172a" } }, h)));
          tbl.appendChild(el("thead", {}, th));
          const tbody = el("tbody");
          const vls = totalProd.values.filter(v => v !== null);
          const dts = totalProd.dates.filter((d, i) => totalProd.values[i] !== null);
          for (let i = vls.length - 1; i >= Math.max(0, vls.length - 52); i--) {
            const val = vls[i] / 1000;
            const prev = i > 0 ? vls[i - 1] / 1000 : val;
            const chg = val - prev;
            const pct = prev > 0 ? (chg / prev * 100) : 0;
            const chgColor = chg >= 0 ? "#10b981" : "#ef4444";
            const tr = el("tr", { style: { borderBottom: "1px solid " + C.border + "20" } });
            tr.appendChild(el("td", { style: { padding: "5px 8px", color: C.text } }, dts[i]));
            tr.appendChild(el("td", { style: { textAlign: "right", padding: "5px 8px", color: C.text } }, val.toFixed(1)));
            tr.appendChild(el("td", { style: { textAlign: "right", padding: "5px 8px", color: chgColor } }, (chg >= 0 ? "+" : "") + chg.toFixed(2)));
            tr.appendChild(el("td", { style: { textAlign: "right", padding: "5px 8px", color: chgColor } }, (pct >= 0 ? "+" : "") + pct.toFixed(2) + "%"));
            tbody.appendChild(tr);
          }
          tbl.appendChild(tbody);
          tblWrap.appendChild(tbl);
          content.appendChild(card("Weekly Changes (Last 52 Weeks)", tblWrap));
        }

      } catch (err) {
        content.innerHTML = '<div style="text-align:center;padding:40px;color:#ef4444">Error: ' + err.message + '</div>';
      }
    }

    loadBtn.onclick = () => { if (curInvProduct === "crude") loadInventories(); else loadGasolineStocks(); };
    loadInventories();
  }


  // ====================================================================
  // Kpler SQL Sync Tab
  // ====================================================================
  function renderKSQL(container) {
    container.innerHTML = "";

    const C2 = C; // alias

    // Header
    const hdr = el("div", { style: { marginBottom: "20px" } });
    hdr.innerHTML = `
      <h2 style="color:${C2.amber};margin:0 0 8px">🔄 Kpler → Azure SQL Sync</h2>
      <p style="color:${C2.muted};font-size:13px;margin:0">
        Push Kpler API data to your Azure SQL database (<b>SQL-D-sd027-Analytical-Data</b>). 
        Click the button below to pull fresh data from all Kpler resources and write to 20 <code>dbo.Kpler_*</code> tables.
      </p>
    `;
    container.appendChild(hdr);

    // Status section
    const statusBox = el("div", { style: { background: C2.card, border: "1px solid " + C2.border, borderRadius: "8px", padding: "16px", marginBottom: "20px" } });
    statusBox.innerHTML = '<p style="color:' + C2.muted + ';margin:0">Loading sync status...</p>';
    container.appendChild(statusBox);

    // Sync button
    const syncBtnRow = el("div", { style: { display: "flex", gap: "12px", marginBottom: "20px", flexWrap: "wrap" } });

    const syncAllBtn = el("button", {
      style: { background: "linear-gradient(135deg, #059669, #10b981)", color: "#fff", border: "none", borderRadius: "8px", padding: "14px 28px", cursor: "pointer", fontWeight: "700", fontSize: "14px", display: "flex", alignItems: "center", gap: "8px" },
      onClick: () => runSync(null)
    });
    syncAllBtn.textContent = "🔄 Sync ALL Kpler Tables to SQL";
    syncBtnRow.appendChild(syncAllBtn);

    // Individual table buttons
    const tableGroups = [
      { name: "Kpler_Flows", label: "Flows" },
      { name: "Kpler_Trades", label: "Trades" },
      { name: "Kpler_Inventories", label: "Inventories" },
      { name: "Kpler_Fixtures", label: "Fixtures" },
      { name: "Kpler_PortCalls", label: "Port Calls" },
      { name: "Kpler_STS", label: "STS" },
      { name: "Kpler_CongestionSeries", label: "Congestion" },
      { name: "Kpler_FleetMetrics", label: "Fleet" },
      { name: "Kpler_CushingDrone", label: "Cushing" },
      { name: "Kpler_TankLevels", label: "Tanks" },
      { name: "Kpler_Ref", label: "Reference" },
    ];

    tableGroups.forEach(tg => {
      const btn = el("button", {
        style: { background: C2.card, color: C2.text, border: "1px solid " + C2.border, borderRadius: "6px", padding: "8px 16px", cursor: "pointer", fontSize: "12px" },
        onClick: () => runSync(tg.name)
      });
      btn.textContent = "↻ " + tg.label;
      syncBtnRow.appendChild(btn);
    });

    container.appendChild(syncBtnRow);

    // Log / results area
    const logArea = el("div", { style: { background: "#0d1117", border: "1px solid " + C2.border, borderRadius: "8px", padding: "16px", fontFamily: "monospace", fontSize: "12px", color: "#c9d1d9", maxHeight: "400px", overflowY: "auto", whiteSpace: "pre-wrap" } });
    logArea.textContent = "Ready. Click a sync button to start.\n";
    container.appendChild(logArea);

    // Tables reference
    const refBox = el("div", { style: { background: C2.card, border: "1px solid " + C2.border, borderRadius: "8px", padding: "16px", marginTop: "20px" } });
    refBox.innerHTML = `
      <h3 style="color:${C2.amber};margin:0 0 12px;font-size:14px">📋 Tables Created in Azure SQL</h3>
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <tr style="border-bottom:1px solid ${C2.border}">
          <th style="text-align:left;padding:6px;color:${C2.muted}">Table</th>
          <th style="text-align:left;padding:6px;color:${C2.muted}">Source</th>
          <th style="text-align:left;padding:6px;color:${C2.muted}">Description</th>
          <th style="text-align:left;padding:6px;color:${C2.muted}">Update</th>
        </tr>
        <tr style="border-bottom:1px solid ${C2.border}"><td style="padding:6px;color:${C2.text}">Kpler_Flows</td><td style="padding:6px;color:${C2.muted}">Flows API</td><td style="padding:6px;color:${C2.muted}">Weekly product flows by country pair (Crude, Gasoline, Naphtha, Gasoil)</td><td style="padding:6px;color:${C2.muted}">Weekly</td></tr>
        <tr style="border-bottom:1px solid ${C2.border}"><td style="padding:6px;color:${C2.text}">Kpler_Trades</td><td style="padding:6px;color:${C2.muted}">Trades API</td><td style="padding:6px;color:${C2.muted}">Individual cargo movements with vessel, buyer/seller, grade, price</td><td style="padding:6px;color:${C2.muted}">Daily</td></tr>
        <tr style="border-bottom:1px solid ${C2.border}"><td style="padding:6px;color:${C2.text}">Kpler_Inventories</td><td style="padding:6px;color:${C2.muted}">Inventories API</td><td style="padding:6px;color:${C2.muted}">Satellite-tracked crude storage (US, China, ARA, Japan, India, etc.)</td><td style="padding:6px;color:${C2.muted}">Weekly</td></tr>
        <tr style="border-bottom:1px solid ${C2.border}"><td style="padding:6px;color:${C2.text}">Kpler_FleetMetrics</td><td style="padding:6px;color:${C2.muted}">Fleet API</td><td style="padding:6px;color:${C2.muted}">Floating storage + loaded vessels by zone</td><td style="padding:6px;color:${C2.muted}">Weekly</td></tr>
        <tr style="border-bottom:1px solid ${C2.border}"><td style="padding:6px;color:${C2.text}">Kpler_PortCalls</td><td style="padding:6px;color:${C2.muted}">PortCalls API</td><td style="padding:6px;color:${C2.muted}">Vessel arrivals/departures at key ports</td><td style="padding:6px;color:${C2.muted}">Daily</td></tr>
        <tr style="border-bottom:1px solid ${C2.border}"><td style="padding:6px;color:${C2.text}">Kpler_CongestionSeries</td><td style="padding:6px;color:${C2.muted}">Congestion API</td><td style="padding:6px;color:${C2.muted}">Vessel waiting counts, DWT, duration by port</td><td style="padding:6px;color:${C2.muted}">Weekly</td></tr>
        <tr style="border-bottom:1px solid ${C2.border}"><td style="padding:6px;color:${C2.text}">Kpler_Fixtures</td><td style="padding:6px;color:${C2.muted}">Fixtures API</td><td style="padding:6px;color:${C2.muted}">Chartering fixtures with rates, charterer, owner</td><td style="padding:6px;color:${C2.muted}">Daily</td></tr>
        <tr style="border-bottom:1px solid ${C2.border}"><td style="padding:6px;color:${C2.text}">Kpler_STS</td><td style="padding:6px;color:${C2.muted}">STS API</td><td style="padding:6px;color:${C2.muted}">Ship-to-ship transfer events</td><td style="padding:6px;color:${C2.muted}">Weekly</td></tr>
        <tr style="border-bottom:1px solid ${C2.border}"><td style="padding:6px;color:${C2.text}">Kpler_CushingDrone</td><td style="padding:6px;color:${C2.muted}">Drone API</td><td style="padding:6px;color:${C2.muted}">Cushing OK weekly drone/satellite survey</td><td style="padding:6px;color:${C2.muted}">Weekly</td></tr>
        <tr style="border-bottom:1px solid ${C2.border}"><td style="padding:6px;color:${C2.text}">Kpler_TankLevels</td><td style="padding:6px;color:${C2.muted}">Tank API</td><td style="padding:6px;color:${C2.muted}">Individual tank fill levels (US, last 30 days)</td><td style="padding:6px;color:${C2.muted}">Monthly</td></tr>
        <tr><td style="padding:6px;color:${C2.text}">Kpler_Zones/Products/Vessels/Players</td><td style="padding:6px;color:${C2.muted}">Reference</td><td style="padding:6px;color:${C2.muted}">Reference data: zones, products, vessels, traders</td><td style="padding:6px;color:${C2.muted}">Monthly</td></tr>
      </table>
    `;
    container.appendChild(refBox);

    // Load status
    async function loadStatus() {
      try {
        const r = await fetch("/api/kpler/sync_status");
        const d = await r.json();
        if (d.error) {
          statusBox.innerHTML = '<p style="color:#ef4444;margin:0">⚠️ ' + d.error + '</p>';
          return;
        }
        if (!d.configured) {
          statusBox.innerHTML = '<p style="color:#f59e0b;margin:0">⚠️ Azure SQL not configured. Set env vars: AZURE_SQL_SERVER, AZURE_SQL_DATABASE, AZURE_SQL_USERNAME, AZURE_SQL_PASSWORD</p>';
          return;
        }
        let html = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px"><span style="color:' + C2.text + ';font-weight:600">📡 Connected to: ' + d.server + '</span><span style="color:#10b981;font-size:12px">● Connected</span></div>';
        if (d.last_syncs && d.last_syncs.length > 0) {
          html += '<table style="width:100%;border-collapse:collapse;font-size:11px">';
          html += '<tr style="border-bottom:1px solid ' + C2.border + '"><th style="text-align:left;padding:4px;color:' + C2.muted + '">Table</th><th style="padding:4px;color:' + C2.muted + '">Rows</th><th style="padding:4px;color:' + C2.muted + '">Status</th><th style="padding:4px;color:' + C2.muted + '">Last Sync</th></tr>';
          d.last_syncs.forEach(s => {
            const color = s.status === "success" ? "#10b981" : "#ef4444";
            html += '<tr style="border-bottom:1px solid ' + C2.border + '"><td style="padding:4px;color:' + C2.text + '">' + s.table + '</td><td style="padding:4px;color:' + C2.muted + ';text-align:center">' + (s.rows || 0) + '</td><td style="padding:4px;color:' + color + ';text-align:center">' + s.status + '</td><td style="padding:4px;color:' + C2.muted + '">' + (s.sync_end || '-') + '</td></tr>';
          });
          html += '</table>';
        } else {
          html += '<p style="color:' + C2.muted + ';margin:0;font-size:12px">No sync history yet. Click "Sync ALL" to start.</p>';
        }
        statusBox.innerHTML = html;
      } catch (e) {
        statusBox.innerHTML = '<p style="color:#ef4444;margin:0">Error checking status: ' + e.message + '</p>';
      }
    }

    async function runSync(tableName) {
      logArea.textContent = "";
      const label = tableName ? tableName : "ALL TABLES";
      logArea.textContent += "⏳ Starting sync: " + label + "...\n";
      logArea.textContent += "   This may take 2-5 minutes. Pulling from Kpler API and writing to Azure SQL...\n\n";

      syncAllBtn.disabled = true;
      syncAllBtn.style.opacity = "0.5";
      syncAllBtn.textContent = "⏳ Syncing...";

      try {
        const url = tableName
          ? "/api/kpler/sync_sql?tables=" + encodeURIComponent(tableName)
          : "/api/kpler/sync_sql";
        const r = await fetch(url, { method: "POST" });
        const d = await r.json();

        if (d.error) {
          logArea.textContent += "❌ ERROR: " + d.error + "\n";
          if (d.traceback) logArea.textContent += "\n" + d.traceback + "\n";
        } else {
          logArea.textContent += "✅ Sync completed: " + d.status + "\n";
          logArea.textContent += "   Synced at: " + d.synced_at + "\n\n";
          if (d.tables) {
            Object.entries(d.tables).forEach(([table, info]) => {
              const icon = info.status === "success" ? "✅" : "❌";
              logArea.textContent += "   " + icon + " " + table + ": " + info.status;
              if (info.rows !== undefined) logArea.textContent += " (" + info.rows + " rows)";
              if (info.error) logArea.textContent += " — " + info.error;
              logArea.textContent += "\n";
            });
          }
        }
      } catch (e) {
        logArea.textContent += "❌ Network error: " + e.message + "\n";
      }

      syncAllBtn.disabled = false;
      syncAllBtn.style.opacity = "1";
      syncAllBtn.textContent = "🔄 Sync ALL Kpler Tables to SQL";
      loadStatus();
    }

    loadStatus();
  }


  // ========== REFINERY MARGINS (seasonal %rank method) ==========
  async function renderMargins(box) {
    box.innerHTML = '<div style="color:#94a3b8;padding:40px;text-align:center;">Loading refinery margins…</div>';
    let data;
    try {
      const r = await fetch("/api/margins");
      data = await r.json();
      if (data.error) throw new Error(data.error);
    } catch (e) {
      box.innerHTML = `<div style="color:#ef4444;padding:30px;">Failed to load margins: ${e.message}</div>`;
      return;
    }
    await new Promise(res => loadPlotly(res));
    box.innerHTML = "";

    const rankColor = (r) => {
      if (r == null) return C.muted;
      if (r >= 90) return C.red;
      if (r <= 10) return C.green;
      if (r >= 75) return "#fb923c";
      if (r <= 25) return "#4ade80";
      return C.text;
    };
    const sigColor = (s) => s === "BUY" ? C.green : s === "SELL" ? C.red : C.muted;
    const seasonBadge = (s) => s === "WINTER"
      ? el("span", { style: { color: C.cyan, fontSize: "10px", fontWeight: "700" } }, "❄ WINTER")
      : el("span", { style: { color: C.amber, fontSize: "10px", fontWeight: "700" } }, "☀ SUMMER");

    // Header
    box.appendChild(el("div", { style: { fontSize: "16px", fontWeight: "800", color: C.amber, marginBottom: "3px" } },
      "📈 REFINERY MARGINS — Seasonal %Rank Model"));
    box.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, marginBottom: "4px" } },
      `Weekly cracking/hydroskimming/coking margins ($/bbl) · ${data.start_date} → ${data.as_of} · ${data.n_weeks} weeks · 4 regions`));
    box.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, marginBottom: "14px" } },
      `Method: ${data.season_definition}. Seasonal %Rank compares the latest margin only against the same grade-season history. Signal: BUY < 10th pctile, SELL > 90th pctile.`));

    // Signal summary
    const buys = data.margins.filter(m => m.signal === "BUY").length;
    const sells = data.margins.filter(m => m.signal === "SELL").length;
    const neutrals = data.margins.filter(m => m.signal === "NEUTRAL").length;
    box.appendChild(card("Signal Summary", statRow([
      ["Total Margins", data.margins.length, C.text],
      ["🟢 BUY (cheap)", buys, C.green],
      ["🔴 SELL (rich)", sells, C.red],
      ["⚪ Neutral", neutrals, C.muted],
      ["Current Season", data.margins[0] ? data.margins[0].season : "-", C.amber],
    ])));

    // Dashboard table
    const tbl = el("table", { style: { width: "100%", borderCollapse: "collapse", fontSize: "12px" } });
    const thead = el("thead");
    const hr = el("tr", { style: { borderBottom: `2px solid ${C.border}` } });
    ["Region", "Margin", "Latest $/bbl", "Season", "%Rank Seasonal", "%Rank All-Time", "Signal", "Trend", "Z-Score", "Winter Med", "Summer Med"].forEach((h, i) => {
      hr.appendChild(el("th", { style: { textAlign: i < 2 ? "left" : "right", padding: "8px 10px", color: C.amber, fontSize: "10px", textTransform: "uppercase", whiteSpace: "nowrap" } }, h));
    });
    thead.appendChild(hr);
    tbl.appendChild(thead);
    const tbody = el("tbody");
    let lastRegion = null;
    data.margins.forEach(m => {
      const tr = el("tr", { style: { borderBottom: `1px solid ${C.border}`, cursor: "pointer" }, onClick: () => showDetail(m.key) });
      tr.addEventListener("mouseenter", () => tr.style.background = "#1e293b");
      tr.addEventListener("mouseleave", () => tr.style.background = "transparent");
      const regCell = el("td", { style: { padding: "7px 10px", color: C.muted, fontSize: "11px", whiteSpace: "nowrap" } }, m.region === lastRegion ? "" : m.region);
      lastRegion = m.region;
      tr.appendChild(regCell);
      tr.appendChild(el("td", { style: { padding: "7px 10px", color: C.text, fontWeight: "600", whiteSpace: "nowrap" } }, m.name));
      tr.appendChild(el("td", { style: { padding: "7px 10px", textAlign: "right", color: C.text, fontWeight: "700" } }, m.latest.toFixed(2)));
      const sc = el("td", { style: { padding: "7px 10px", textAlign: "right" } }); sc.appendChild(seasonBadge(m.season)); tr.appendChild(sc);
      tr.appendChild(el("td", { style: { padding: "7px 10px", textAlign: "right", color: rankColor(m.rank_seasonal), fontWeight: "700" } }, m.rank_seasonal == null ? "—" : m.rank_seasonal + "%"));
      tr.appendChild(el("td", { style: { padding: "7px 10px", textAlign: "right", color: rankColor(m.rank_all) } }, m.rank_all == null ? "—" : m.rank_all + "%"));
      tr.appendChild(el("td", { style: { padding: "7px 10px", textAlign: "right", color: sigColor(m.signal), fontWeight: "800" } }, m.signal));
      tr.appendChild(el("td", { style: { padding: "7px 10px", textAlign: "right", color: m.trend === "RISING" ? C.green : C.red } }, m.trend === "RISING" ? "▲ RISING" : "▼ FALLING"));
      tr.appendChild(el("td", { style: { padding: "7px 10px", textAlign: "right", color: Math.abs(m.zscore || 0) >= 2 ? C.amber : C.text } }, m.zscore == null ? "—" : m.zscore.toFixed(2)));
      tr.appendChild(el("td", { style: { padding: "7px 10px", textAlign: "right", color: C.muted } }, m.winter_median == null ? "—" : m.winter_median.toFixed(1)));
      tr.appendChild(el("td", { style: { padding: "7px 10px", textAlign: "right", color: C.muted } }, m.summer_median == null ? "—" : m.summer_median.toFixed(1)));
      tbody.appendChild(tr);
    });
    tbl.appendChild(tbody);
    box.appendChild(card("Margins Dashboard — click a row for detail charts", tbl));

    // Detail area
    const detail = el("div", { id: "margins-detail" });
    box.appendChild(detail);

    function showDetail(key) {
      const m = data.margins.find(x => x.key === key);
      if (!m) return;
      detail.innerHTML = "";
      detail.appendChild(el("div", { style: { fontSize: "14px", fontWeight: "800", color: C.amber, margin: "10px 0 6px" } },
        `${m.region} — ${m.name}`));

      // Stats row
      detail.appendChild(card(null, statRow([
        ["Latest", m.latest.toFixed(2) + " $/bbl", C.text],
        ["Seasonal %Rank", (m.rank_seasonal ?? "—") + "%", rankColor(m.rank_seasonal)],
        ["Signal", m.signal, sigColor(m.signal)],
        ["4wk MA", m.ma4.toFixed(2), C.text],
        ["13wk MA", m.ma13.toFixed(2), C.text],
        ["52wk MA", m.ma52.toFixed(2), C.text],
      ])));
      detail.appendChild(card(null, statRow([
        ["Min", m.stats.min.toFixed(2), C.red],
        ["Median", m.stats.median.toFixed(2), C.text],
        ["Avg", m.stats.avg.toFixed(2), C.text],
        ["Max", m.stats.max.toFixed(2), C.green],
        ["Std Dev", m.stats.stdev.toFixed(2), C.muted],
        ["Z-Score", (m.zscore ?? "—"), C.amber],
      ])));

      // Chart 1: time series + MAs
      const c1 = el("div", { id: "mg-ts", style: { width: "100%", height: "420px" } });
      detail.appendChild(card("Margin History with Moving Averages ($/bbl)", c1));
      const dts = m.series_dates, vs = m.series_values;
      const roll = (n) => vs.map((_, i) => {
        const s = Math.max(0, i - n + 1); const seg = vs.slice(s, i + 1);
        return seg.reduce((a, b) => a + b, 0) / seg.length;
      });
      Plotly.newPlot("mg-ts", [
        { x: dts, y: vs, name: "Weekly Margin", line: { color: C.cyan, width: 1.5 } },
        { x: dts, y: roll(4), name: "4-Week MA", line: { color: C.amber, width: 2 } },
        { x: dts, y: roll(13), name: "13-Week MA", line: { color: C.purple, width: 2 } },
      ], { ...plotLayout, height: 420,
        yaxis: { ...plotLayout.yaxis, title: { text: "$/bbl", font: { size: 12 } } },
        shapes: [
          { type: "line", x0: dts[0], x1: dts[dts.length - 1], y0: m.winter_median, y1: m.winter_median, line: { color: C.blue, width: 1, dash: "dot" } },
          { type: "line", x0: dts[0], x1: dts[dts.length - 1], y0: m.summer_median, y1: m.summer_median, line: { color: "#f97316", width: 1, dash: "dot" } },
        ],
      }, { responsive: true });

      // Chart 2: seasonal distribution (winter vs summer) with current marker
      const c2 = el("div", { id: "mg-dist", style: { width: "100%", height: "380px" } });
      detail.appendChild(card(`Seasonal Distribution — where the latest margin sits (current season: ${m.season})`, c2));
      const winterVals = [], summerVals = [];
      m.series_values.forEach((v, i) => { (m.series_seasons[i] === "WINTER" ? winterVals : summerVals).push(v); });
      Plotly.newPlot("mg-dist", [
        { x: winterVals, type: "histogram", name: "❄ Winter (Sep–Feb)", opacity: 0.6, marker: { color: C.blue }, nbinsx: 40 },
        { x: summerVals, type: "histogram", name: "☀ Summer (Mar–Aug)", opacity: 0.6, marker: { color: "#f97316" }, nbinsx: 40 },
      ], { ...plotLayout, height: 380, barmode: "overlay",
        xaxis: { ...plotLayout.xaxis, title: { text: "Margin $/bbl", font: { size: 12 } } },
        yaxis: { ...plotLayout.yaxis, title: { text: "Weeks (count)", font: { size: 12 } } },
        shapes: [{ type: "line", x0: m.latest, x1: m.latest, y0: 0, y1: 1, yref: "paper", line: { color: C.green, width: 2.5 } }],
        annotations: [{ x: m.latest, y: 1, yref: "paper", text: `Latest ${m.latest.toFixed(1)}`, showarrow: false, font: { color: C.green, size: 11 }, bgcolor: "rgba(0,0,0,0.5)" }],
      }, { responsive: true });

      detail.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    // Auto-open first margin
    if (data.margins.length) showDetail(data.margins[0].key);
  }


  function inject() {
    if (injected) return;
    injected = true;

    // ─── SIGNAL OCEAN TAB (/api/signal/*) — DPP Aframax/Suezmax/VLCC strait passages ───
    async function renderSignal(box) {
      box.innerHTML = "";
      const CLASS_COL = { VLCC: C.purple, Suezmax: C.cyan, Aframax: C.gold, All: C.amber, Unknown: C.muted };
      const PAL = ["#38bdf8", "#8b5cf6", "#22d3ee", "#f5b90f", "#10b981", "#ef4444", "#f472b6", "#a3e635", "#fb923c", "#60a5fa", "#c084fc", "#34d399"];
      const state = { days: 90, cls: "All", load: "All", scope: "key", strait: "ALL", data: null, status: null, view: "passages" };
      const LOAD_COL = { All: C.amber, Laden: C.green, Ballast: C.muted };
      const VIEWS = [["passages", "⛵ Strait passages"], ["fleet", "📍 Fleet tracker"], ["flows", "🛢 Crude flows"], ["tonnage", "⚓ Tonnage lists"]];
      const TITLES = { passages: "Tanker Strait Passages", fleet: "Fleet Tracker (live AIS)", flows: "Dirty Crude Flows (voyages)", tonnage: "Available Tonnage (supply)" };
      const SUBS = { passages: "daily vessel crossings of straits & waypoints (AIS), laden vs ballast", fleet: "latest AIS position, voyage status, destination & ETA for every DPP VLCC / Suezmax / Aframax", flows: "weekly dirty loadings by load region, load→discharge matrix and cargo currently on the water (Signal voyage estimates, barrels)", tonnage: "vessels that can reach each configured load port within N days · open/fixed status, ETA buckets, history" };

      const hdr = el("div", { style: { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "14px", flexWrap: "wrap", gap: "10px" } });
      const hl = el("div", {});
      const titleEl = el("div", { style: { fontSize: "20px", fontWeight: "800", color: C.amber } }, "📡 Signal — " + TITLES.passages);
      const subEl = el("div", { style: { fontSize: "12px", color: C.muted, marginTop: "3px" } }, "Signal Ocean enterprise feed · Dirty (DPP) Aframax / Suezmax / VLCC · " + SUBS.passages);
      hl.appendChild(titleEl); hl.appendChild(subEl);
      hdr.appendChild(hl);
      const statusPill = el("span", { style: { fontSize: "10.5px", fontWeight: "800", letterSpacing: ".05em", borderRadius: "999px", padding: "4px 12px", border: `1px solid ${C.border}`, color: C.muted, background: "#0b1220" } }, "○ CONNECTING…");
      hdr.appendChild(statusPill);
      box.appendChild(hdr);

      const subnav = el("div", { style: { display: "flex", gap: "4px", borderBottom: `1px solid ${C.border}`, marginBottom: "14px" } });
      box.appendChild(subnav);
      const ctrl = el("div", { style: { display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center", marginBottom: "14px" } });
      const body = el("div", {});
      box.appendChild(ctrl); box.appendChild(body);
      const vstate = { fleet: { cls: "All", load: "All", status: "All", q: "", region: "All", data: null }, flows: { days: 365, src: "ALL", data: null }, tonnage: { days: 90, port: null, data: null } };
      const AXB = { gridcolor: "#1e293b", tickfont: { size: 11 } }; // fresh axis objects: Plotly mutates the layout it is given, so never share plotLayout.xaxis
      function renderSubnav() {
        subnav.innerHTML = "";
        VIEWS.forEach(([id, label]) => {
          const active = state.view === id;
          subnav.appendChild(el("button", { style: { background: "transparent", border: "none", borderBottom: active ? `2px solid ${C.amber}` : "2px solid transparent", color: active ? C.amber : C.muted, padding: "8px 14px", cursor: "pointer", fontSize: "12.5px", fontWeight: "700", marginBottom: "-1px" }, onClick: () => { if (state.view === id) return; state.view = id; titleEl.textContent = "📡 Signal — " + TITLES[id]; subEl.textContent = "Signal Ocean enterprise feed · Dirty (DPP) Aframax / Suezmax / VLCC · " + SUBS[id]; renderSubnav(); showView(); } }, label));
        });
      }
      function showView() {
        if (state.view === "passages") { ctrl.style.display = "flex"; if (state.data) draw(); else load(true); return; }
        ctrl.style.display = "none";
        if (state.status && !state.status.connected) { renderNotConnected(state.status); return; }
        if (state.view === "fleet") loadFleet(false);
        else if (state.view === "flows") loadFlows(false);
        else loadTonnage(false);
      }

      function pill(label, active, onClick, color) {
        return el("button", { style: { background: active ? (color || C.amber) : "transparent", color: active ? "#05070e" : (color || C.text), border: `1px solid ${color || C.border}`, borderRadius: "999px", padding: "5px 13px", cursor: "pointer", fontSize: "11.5px", fontWeight: "700" }, onClick }, label);
      }
      function setPill(txt, col) { statusPill.textContent = txt; statusPill.style.color = col; statusPill.style.borderColor = col; }

      function renderControls() {
        ctrl.innerHTML = "";
        ctrl.appendChild(el("span", { style: { fontSize: "10.5px", color: C.muted, fontWeight: "700", letterSpacing: "1px" } }, "WINDOW"));
        [30, 90, 180, 365, 730].forEach(d => ctrl.appendChild(pill(d >= 365 ? (d / 365) + "y" : d + "d", state.days === d, () => { state.days = d; load(true); })));
        ctrl.appendChild(el("span", { style: { width: "14px" } }));
        ctrl.appendChild(el("span", { style: { fontSize: "10.5px", color: C.muted, fontWeight: "700", letterSpacing: "1px" } }, "CLASS"));
        const classes = ["All"].concat((state.data && state.data.classes) || ["VLCC", "Suezmax", "Aframax"]);
        classes.forEach(c => ctrl.appendChild(pill(c, state.cls === c, () => { state.cls = c; draw(); }, CLASS_COL[c])));
        if (isWp()) {
          ctrl.appendChild(el("span", { style: { width: "14px" } }));
          ctrl.appendChild(el("span", { style: { fontSize: "10.5px", color: C.muted, fontWeight: "700", letterSpacing: "1px" } }, "LOAD"));
          ["All", "Laden", "Ballast"].forEach(l => ctrl.appendChild(pill(l, state.load === l, () => { state.load = l; draw(); }, LOAD_COL[l])));
          ctrl.appendChild(el("span", { style: { width: "14px" } }));
          ctrl.appendChild(el("span", { style: { fontSize: "10.5px", color: C.muted, fontWeight: "700", letterSpacing: "1px" } }, "SCOPE"));
          ctrl.appendChild(pill("Key straits", state.scope === "key", () => { state.scope = "key"; state.strait = "ALL"; draw(); }));
          ctrl.appendChild(pill("All waypoints", state.scope === "all", () => { state.scope = "all"; state.strait = "ALL"; draw(); }));
        }
        const refreshBtn = el("button", { style: { marginLeft: "auto", background: "transparent", color: C.muted, border: `1px solid ${C.border}`, borderRadius: "8px", padding: "5px 12px", cursor: "pointer", fontSize: "11.5px" }, onClick: () => load(true, true) }, "↻ Refresh from Signal");
        ctrl.appendChild(refreshBtn);
      }

      function isWp() { return !!(state.data && state.data.source && state.data.source.mode === "waypoints"); }
      // cells: [dayIdx, classIdx, dirCode, laden(0/1), n] — lets any class × load × direction slice be built client-side
      function cellsFor(st, dir) {
        const n = state.data.dates.length, out = new Array(n).fill(0);
        const ci = state.cls === "All" ? -1 : state.data.classes.indexOf(state.cls);
        const li = state.load === "All" ? -1 : (state.load === "Laden" ? 1 : 0);
        for (const c of st.cells) {
          if (ci >= 0 && c[1] !== ci) continue;
          if (li >= 0 && c[3] !== li) continue;
          if (dir && c[2] !== dir) continue;
          out[c[0]] += c[4];
        }
        return out;
      }
      function sumCells(sel, dir) {
        const out = new Array(state.data.dates.length).fill(0);
        sel.forEach(st => cellsFor(st, dir).forEach((v, i) => { out[i] += v; }));
        return out;
      }
      function seriesFor(st) {
        if (isWp()) {
          if (state.load === "All") return state.cls === "All" ? st.total : (st.by_class[state.cls] || st.total.map(() => 0));
          return cellsFor(st, null);
        }
        if (state.cls === "All") return st.total;
        return st.by_class[state.cls] || st.total.map(() => 0);
      }
      function lySeriesFor(st) {
        if (!isWp() || state.load !== "All") return null;
        return state.cls === "All" ? st.ly_total : (st.ly_by_class[state.cls] || null);
      }
      function dirLabel(code) { return (state.data.direction_labels || {})[code] || code; }
      function movAvg(arr, n) { return arr.map((_, i) => { const s = arr.slice(Math.max(0, i - n + 1), i + 1); return s.reduce((a, b) => a + b, 0) / s.length; }); }

      function renderNotConnected(status) {
        body.innerHTML = "";
        const c = card("Connection", null);
        const msg = el("div", { style: { color: C.text, fontSize: "13px", lineHeight: "1.7" } });
        if (!status || !status.configured) {
          msg.innerHTML = `Signal SQL credentials are not configured on the server. Set <code>SIGNAL_SQL_SERVER</code>, <code>SIGNAL_SQL_USERNAME</code>, <code>SIGNAL_SQL_PASSWORD</code> (and optional <code>SIGNAL_SQL_DATABASE</code>) as Fly secrets.`;
        } else {
          msg.innerHTML = `<div style="color:${C.red};font-weight:700;margin-bottom:6px">Login to Signal SQL Server failed</div>
            <div><span style="color:${C.muted}">Server:</span> <code>${status.server}</code>${status.database ? ` · <span style="color:${C.muted}">DB:</span> <code>${status.database}</code>` : ""}</div>
            <div style="margin-top:6px;color:${C.muted};font-family:monospace;font-size:11.5px;white-space:pre-wrap">${(status.error || "").replace(/</g, "&lt;")}</div>
            <div style="margin-top:10px;color:${C.muted}">The server is reachable and is rejecting the SQL login (error 18456). Ask the Signal team to confirm the login <b>Socar_user</b> is active on this instance, the password, and the database name. This tab will populate automatically once the login is accepted.</div>`;
        }
        c.appendChild(msg);
        body.appendChild(c);
      }

      async function renderSchemaExplorer(reason) {
        const c = card("Data explorer", null);
        c.appendChild(el("div", { style: { color: C.muted, fontSize: "12.5px", marginBottom: "10px" } }, reason || "Browse the tables exposed by the Signal login."));
        const wrap = el("div", { style: { display: "grid", gridTemplateColumns: "260px 1fr", gap: "14px" } });
        const list = el("div", { style: { maxHeight: "520px", overflowY: "auto", borderRight: `1px solid ${C.border}`, paddingRight: "8px" } });
        const view = el("div", { style: { overflowX: "auto", minHeight: "120px" } });
        view.appendChild(el("div", { style: { color: C.muted, fontSize: "12px" } }, "Select a table to preview its latest rows."));
        wrap.appendChild(list); wrap.appendChild(view); c.appendChild(wrap); body.appendChild(c);
        try {
          const r = await fetch("/api/signal/schema"); const sc = await r.json();
          if (sc.error) { list.appendChild(el("div", { style: { color: C.red, fontSize: "12px" } }, sc.error)); return; }
          if (!sc.tables.length) list.appendChild(el("div", { style: { color: C.muted, fontSize: "12px" } }, "No tables visible to this login."));
          sc.tables.forEach(t => {
            const key = t.schema + "." + t.name;
            const b = el("button", { style: { display: "block", width: "100%", textAlign: "left", background: "transparent", border: "none", color: C.text, padding: "6px 8px", cursor: "pointer", fontSize: "12px", borderRadius: "6px" }, onClick: async () => {
              view.innerHTML = `<div style="color:${C.muted};font-size:12px">Loading ${key}…</div>`;
              const pr = await (await fetch(`/api/signal/preview?table=${encodeURIComponent(key)}&limit=50`)).json();
              if (pr.error) { view.innerHTML = `<div style="color:${C.red};font-size:12px">${pr.error}</div>`; return; }
              let h = `<div style="color:${C.muted};font-size:11.5px;margin-bottom:6px">${key} · ${pr.row_count != null ? pr.row_count.toLocaleString() + " rows · " : ""}showing ${pr.rows.length}</div>`;
              h += `<table style="border-collapse:collapse;font-size:11px;white-space:nowrap"><thead><tr>` + pr.columns.map(cn => `<th style="padding:5px 8px;text-align:left;color:${C.amber};border-bottom:1px solid ${C.border}">${cn}</th>`).join("") + `</tr></thead><tbody>`;
              pr.rows.forEach(row => { h += "<tr>" + pr.columns.map(cn => `<td style="padding:4px 8px;border-bottom:1px solid #111827;color:${C.text}">${row[cn] == null ? "" : String(row[cn]).slice(0, 60)}</td>`).join("") + "</tr>"; });
              view.innerHTML = h + "</tbody></table>";
            } }, `${t.name}`);
            b.appendChild(el("span", { style: { color: C.muted, fontSize: "10px", marginLeft: "6px" } }, `${t.columns.length} cols`));
            list.appendChild(b);
          });
        } catch (e) { list.appendChild(el("div", { style: { color: C.red, fontSize: "12px" } }, e.message)); }
      }

      function draw() {
        renderControls();
        const d = state.data;
        body.innerHTML = "";
        if (!d || !d.available) return;
        let straits = d.straits.filter(st => (isWp() && state.scope === "key") ? st.key : true);
        if (!isWp() || state.scope === "all") straits = straits.filter(st => seriesFor(st).some(v => v > 0));
        if (!straits.length) { body.appendChild(card(null, `No ${state.cls} passages in the last ${d.days} days.`)); return; }

        // KPI strip: 7d avg vs prior-30d avg and vs same week last year, per strait
        const kpi = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))", gap: "10px", marginBottom: "14px" } });
        straits.forEach((st, i) => {
          const s = seriesFor(st); const a7 = s.slice(-7).reduce((a, b) => a + b, 0) / Math.min(7, s.length);
          const p30 = s.slice(-37, -7); const a30 = p30.length ? p30.reduce((a, b) => a + b, 0) / p30.length : null;
          const dpct = a30 ? (a7 - a30) / a30 * 100 : null;
          const ly = lySeriesFor(st); const ly7 = ly ? ly.slice(-7).reduce((a, b) => a + b, 0) / Math.min(7, ly.length) : null;
          const ypct = ly7 ? (a7 - ly7) / ly7 * 100 : null;
          const k = el("div", { style: { background: C.card, border: `1px solid ${C.border}`, borderLeft: `3px solid ${PAL[i % PAL.length]}`, borderRadius: "10px", padding: "10px 12px" } });
          k.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, fontWeight: "700", letterSpacing: ".5px", textTransform: "uppercase" } }, st.strait));
          const row = el("div", { style: { display: "flex", alignItems: "baseline", gap: "8px", marginTop: "4px" } });
          row.appendChild(el("span", { style: { fontSize: "20px", fontWeight: "800", color: C.text } }, a7.toFixed(1)));
          row.appendChild(el("span", { style: { fontSize: "10.5px", color: C.muted } }, `/day (7d avg) · latest ${s[s.length - 1]}`));
          k.appendChild(row);
          k.appendChild(el("div", { style: { fontSize: "11px", color: dpct == null ? C.muted : dpct >= 0 ? C.green : C.red, marginTop: "2px" } }, dpct == null ? `no prior-30d base` : `${dpct >= 0 ? "▲" : "▼"} ${Math.abs(dpct).toFixed(0)}% vs prior 30d (${a30.toFixed(1)}/day)`));
          if (ypct != null) k.appendChild(el("div", { style: { fontSize: "11px", color: ypct >= 0 ? C.green : C.red, marginTop: "1px" } }, `${ypct >= 0 ? "▲" : "▼"} ${Math.abs(ypct).toFixed(0)}% y/y (same week 2025: ${ly7.toFixed(1)}/day)`));
          else if (ly && ly7 === 0 && a7 > 0) k.appendChild(el("div", { style: { fontSize: "11px", color: C.green, marginTop: "1px" } }, "y/y: none last year"));
          kpi.appendChild(k);
        });
        body.appendChild(kpi);

        // Main chart: all straits, 7d moving average, stacked bars toggle
        const mainDiv = el("div", { style: { height: "380px" } });
        const mainCard = card(`Daily passages by strait — ${state.cls}${isWp() && state.load !== "All" ? " · " + state.load : ""} (7-day moving average, hover for daily)`, mainDiv);
        body.appendChild(mainCard);
        loadPlotly(() => {
          const traces = straits.map((st, i) => ({ x: d.dates, y: movAvg(seriesFor(st), 7), name: st.strait, mode: "lines", line: { color: PAL[i % PAL.length], width: 2 }, customdata: seriesFor(st), hovertemplate: "%{fullData.name}<br>7d avg %{y:.1f} · day %{customdata}<extra></extra>" }));
          Plotly.newPlot(mainDiv, traces, { ...plotLayout, xaxis: { ...AXB }, yaxis: { ...AXB }, yaxis: { ...AXB, title: { text: "transits / day", font: { size: 10, color: C.muted } } }, margin: { t: 10, b: 60, l: 50, r: 20 } }, { responsive: true, displayModeBar: false });
        });

        // Class mix (stacked) for the selected strait or all
        const straitSel = el("select", { style: { background: "#0b1220", color: C.text, border: `1px solid ${C.border}`, borderRadius: "6px", padding: "4px 8px", fontSize: "12px" } });
        ["ALL"].concat(straits.map(s => s.strait)).forEach(sname => { const o = el("option", { value: sname }, sname === "ALL" ? (state.scope === "key" ? "All key straits" : "All waypoints") : sname); if (sname === state.strait) o.selected = true; straitSel.appendChild(o); });
        straitSel.addEventListener("change", () => { state.strait = straitSel.value; draw(); });
        const mixDiv = el("div", { style: { height: "300px" } });
        const mixWrap = el("div", {}, [el("div", { style: { marginBottom: "8px" } }, straitSel), mixDiv]);
        body.appendChild(card(`Vessel-class mix — daily passages (stacked${isWp() && state.load !== "All" ? ", " + state.load.toLowerCase() + " only" : ""})`, mixWrap));
        loadPlotly(() => {
          const sel = state.strait === "ALL" ? straits : straits.filter(s => s.strait === state.strait);
          const saveCls = state.cls;
          const traces = d.classes.map(cl => {
            let y;
            if (isWp() && state.load !== "All") { state.cls = cl; y = sumCells(sel, null); state.cls = saveCls; }
            else y = d.dates.map((_, i) => sel.reduce((a, st) => a + ((st.by_class[cl] || [])[i] || 0), 0));
            return { x: d.dates, y, name: cl, type: "bar", marker: { color: CLASS_COL[cl] || C.muted } };
          });
          Plotly.newPlot(mixDiv, traces, { ...plotLayout, xaxis: { ...AXB }, yaxis: { ...AXB }, barmode: "stack", yaxis: { ...AXB, title: { text: "transits / day", font: { size: 10, color: C.muted } } }, margin: { t: 10, b: 60, l: 50, r: 20 } }, { responsive: true, displayModeBar: false });
        });

        // Laden vs ballast split (crude on the water vs repositioning) for the selected scope
        if (isWp() && state.load === "All") {
          const ldDiv = el("div", { style: { height: "280px" } });
          body.appendChild(card(`Laden vs ballast — ${state.strait === "ALL" ? (state.scope === "key" ? "all key straits" : "all waypoints") : state.strait} · ${state.cls}`, ldDiv));
          loadPlotly(() => {
            const sel = state.strait === "ALL" ? straits : straits.filter(s => s.strait === state.strait);
            const saveLoad = state.load;
            const traces = ["Laden", "Ballast"].map(l => { state.load = l; const y = sumCells(sel, null); state.load = saveLoad; return { x: d.dates, y, name: l, type: "bar", marker: { color: LOAD_COL[l] } }; });
            Plotly.newPlot(ldDiv, traces, { ...plotLayout, xaxis: { ...AXB }, yaxis: { ...AXB }, barmode: "stack", yaxis: { ...AXB, title: { text: "transits / day", font: { size: 10, color: C.muted } } }, margin: { t: 10, b: 60, l: 50, r: 20 } }, { responsive: true, displayModeBar: false });
          });
        }

        // Small multiples per strait, with direction split when available
        const grid = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(420px, 1fr))", gap: "12px" } });
        straits.forEach((st, i) => {
          const dv = el("div", { style: { height: "220px" } });
          grid.appendChild(card(st.strait, dv, { marginBottom: "0" }));
          loadPlotly(() => {
            const dirs = Object.keys(st.by_direction || {}).sort();
            let traces;
            if (dirs.length && isWp()) traces = dirs.map((dn, j) => ({ x: d.dates, y: cellsFor(st, dn), name: dirLabel(dn), type: "bar", marker: { color: PAL[(i + j * 3) % PAL.length] } }));
            else if (dirs.length && state.cls === "All") traces = dirs.map((dn, j) => ({ x: d.dates, y: st.by_direction[dn], name: dn, type: "bar", marker: { color: PAL[(i + j * 3) % PAL.length] } }));
            else traces = [{ x: d.dates, y: seriesFor(st), name: "daily", type: "bar", marker: { color: PAL[i % PAL.length], opacity: 0.55 } }];
            traces.push({ x: d.dates, y: movAvg(seriesFor(st), 7), name: "7d avg", mode: "lines", line: { color: "#e8edf8", width: 1.5 } });
            const ly = lySeriesFor(st);
            if (ly) traces.push({ x: d.dates, y: movAvg(ly, 7), name: "7d avg, year ago", mode: "lines", line: { color: C.muted, width: 1.2, dash: "dot" } });
            Plotly.newPlot(dv, traces, { ...plotLayout, xaxis: { ...AXB }, yaxis: { ...AXB }, barmode: "stack", showlegend: true, margin: { t: 8, b: 40, l: 36, r: 10 }, legend: { ...plotLayout.legend, y: -0.3 } }, { responsive: true, displayModeBar: false });
          });
        });
        body.appendChild(grid);

        // Source footnote
        const src = d.source || {};
        body.appendChild(el("div", { style: { color: C.muted, fontSize: "11px", marginTop: "12px" } },
          src.mode === "waypoints"
            ? `Source: Signal Ocean · ${src.table_key} (AIS waypoint crossings, one row per vessel per day) · ${src.class} · direction=${src.direction}, laden/ballast=${src.loading} · data through ${d.dates[d.dates.length - 1]} · fetched ${d.fetched_at.slice(0, 16).replace("T", " ")} UTC · cached 15 min · dotted line = same period one year earlier`
            : `Source: Signal Ocean SQL · ${src.mode === "auto" ? `${src.table_key} (date=${src.date}, strait=${src.strait}${src.class ? ", class=" + src.class : ""}${src.vessel ? ", vessel=" + src.vessel : ""})` : "custom SQL"} · ${d.rows.toLocaleString()} grouped rows · fetched ${d.fetched_at.slice(0, 16).replace("T", " ")} UTC · cached 15 min`));
      }

      // ── shared helpers for the fleet / flows / tonnage views ──
      function lbl(t) { return el("span", { style: { fontSize: "10.5px", color: C.muted, fontWeight: "700", letterSpacing: "1px" } }, t); }
      function gap() { return el("span", { style: { width: "14px" } }); }
      function kpiCard(title, value, sub, color) {
        const k = el("div", { style: { background: C.card, border: `1px solid ${C.border}`, borderLeft: `3px solid ${color || C.amber}`, borderRadius: "10px", padding: "10px 12px" } });
        k.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, fontWeight: "700", letterSpacing: ".5px", textTransform: "uppercase" } }, title));
        k.appendChild(el("div", { style: { fontSize: "20px", fontWeight: "800", color: C.text, marginTop: "4px" } }, value));
        if (sub) k.appendChild(el("div", { style: { fontSize: "11px", color: C.muted, marginTop: "2px" } }, sub));
        return k;
      }
      function table(cols, rows, opts) {
        opts = opts || {};
        let h = `<table style="border-collapse:collapse;font-size:11.5px;white-space:nowrap;width:100%"><thead><tr>` + cols.map(c => `<th style="padding:6px 8px;text-align:${c.num ? "right" : "left"};color:${C.amber};border-bottom:1px solid ${C.border};position:sticky;top:0;background:${C.card}">${c.h}</th>`).join("") + `</tr></thead><tbody>`;
        rows.forEach(r => { h += `<tr>` + cols.map(c => { const v = c.f(r); return `<td style="padding:4px 8px;border-bottom:1px solid #111827;color:${c.color ? c.color(r) : C.text};text-align:${c.num ? "right" : "left"}">${v == null || v === "" ? "<span style='color:#334155'>—</span>" : v}</td>`; }).join("") + `</tr>`; });
        const w = el("div", { style: { overflow: "auto", maxHeight: (opts.maxH || 420) + "px" } });
        w.innerHTML = h + "</tbody></table>";
        return w;
      }
      const esc = s => String(s == null ? "" : s).replace(/</g, "&lt;");
      const failBox = (what, d) => { body.innerHTML = ""; body.appendChild(card(null, `Error reading ${what}: ${d.error || d.reason}`)); };
      const stamp = (d, extra) => el("div", { style: { color: C.muted, fontSize: "11px", marginTop: "12px" } }, `Source: Signal Ocean · ${d.source.table_key}${extra ? " · " + extra : ""} · fetched ${d.fetched_at.slice(0, 16).replace("T", " ")} UTC · cached 15 min`);
      function refreshBtn(fn) { return el("button", { style: { marginLeft: "auto", background: "transparent", color: C.muted, border: `1px solid ${C.border}`, borderRadius: "8px", padding: "5px 12px", cursor: "pointer", fontSize: "11.5px" }, onClick: fn }, "↻ Refresh from Signal"); }

      // ── FLEET TRACKER ──
      const STATUS_ORDER = ["Laden", "Ballast", "Loading", "WaitToLoad", "Discharging", "WaitToDischarge", "Repairs", "Unknown"];
      const STATUS_COL = { Laden: C.green, Ballast: C.muted, Loading: C.gold, WaitToLoad: "#fb923c", Discharging: C.cyan, WaitToDischarge: "#60a5fa", Repairs: C.red, Unknown: "#475569" };
      async function loadFleet(force) {
        const fs = vstate.fleet;
        if (!fs.data || force) {
          body.innerHTML = `<div style="color:${C.muted};padding:30px;text-align:center">Loading fleet positions from Signal…</div>`;
          try { fs.data = await (await fetch(`/api/signal/fleet${force ? "?refresh=1" : ""}`)).json(); }
          catch (e) { body.innerHTML = `<div style="color:${C.red};padding:30px">${e.message}</div>`; return; }
        }
        if (!fs.data.available) return failBox("fleet", fs.data);
        drawFleet();
      }
      function drawFleet() {
        const fs = vstate.fleet, d = fs.data;
        body.innerHTML = "";
        const c = el("div", { style: { display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center", marginBottom: "14px" } });
        c.appendChild(lbl("CLASS"));
        ["All"].concat(d.classes).forEach(cl => c.appendChild(pill(cl, fs.cls === cl, () => { fs.cls = cl; drawFleet(); }, CLASS_COL[cl])));
        c.appendChild(gap()); c.appendChild(lbl("LOAD"));
        ["All", "Laden", "Ballast"].forEach(l => c.appendChild(pill(l, fs.load === l, () => { fs.load = l; drawFleet(); }, LOAD_COL[l])));
        c.appendChild(gap()); c.appendChild(lbl("STATUS"));
        const stSel = el("select", { style: { background: "#0b1220", color: C.text, border: `1px solid ${C.border}`, borderRadius: "6px", padding: "4px 8px", fontSize: "12px" } });
        ["All"].concat(STATUS_ORDER.filter(s => d.vessels.some(v => v.status === s))).forEach(s => { const o = el("option", { value: s }, s); if (s === fs.status) o.selected = true; stSel.appendChild(o); });
        stSel.addEventListener("change", () => { fs.status = stSel.value; drawFleet(); }); c.appendChild(stSel);
        c.appendChild(gap()); c.appendChild(lbl("REGION"));
        const rgSel = el("select", { style: { background: "#0b1220", color: C.text, border: `1px solid ${C.border}`, borderRadius: "6px", padding: "4px 8px", fontSize: "12px" } });
        ["All"].concat(d.by_region.map(r => r.region)).forEach(s => { const o = el("option", { value: s }, s); if (s === fs.region) o.selected = true; rgSel.appendChild(o); });
        rgSel.addEventListener("change", () => { fs.region = rgSel.value; drawFleet(); }); c.appendChild(rgSel);
        c.appendChild(gap());
        const q = el("input", { placeholder: "🔍 vessel name / IMO / operator / destination", value: fs.q, style: { background: "#0b1220", color: C.text, border: `1px solid ${C.border}`, borderRadius: "6px", padding: "5px 10px", fontSize: "12px", width: "300px" } });
        let qt; q.addEventListener("input", () => { clearTimeout(qt); qt = setTimeout(() => { fs.q = q.value; drawFleet(); const nq = body.querySelector("input"); if (nq) { nq.focus(); nq.setSelectionRange(nq.value.length, nq.value.length); } }, 250); });
        c.appendChild(q);
        c.appendChild(refreshBtn(() => loadFleet(true)));
        body.appendChild(c);

        const ql = fs.q.trim().toLowerCase();
        const vs = d.vessels.filter(v => (fs.cls === "All" || v.cls === fs.cls) && (fs.load === "All" || (fs.load === "Laden") === v.laden) && (fs.status === "All" || v.status === fs.status) && (fs.region === "All" || v.region === fs.region)
          && (!ql || [v.name, v.imo, v.op, v.dest, v.dest_area, v.area, v.port, v.next_port].some(x => x != null && String(x).toLowerCase().includes(ql))));
        const laden = vs.filter(v => v.laden).length, moving = vs.filter(v => v.spd != null && v.spd >= 3).length, repairs = vs.filter(v => v.status === "Repairs").length;
        const ladenDwt = vs.filter(v => v.laden).reduce((a, v) => a + (v.dwt || 0), 0);
        const kpi = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))", gap: "10px", marginBottom: "14px" } });
        kpi.appendChild(kpiCard("Vessels tracked", vs.length.toLocaleString(), `of ${d.count.toLocaleString()} DPP ${fs.cls === "All" ? "VLCC/Suez/Afra" : fs.cls} · AIS as of ${(d.as_of || "").replace("T", " ")} UTC`, C.amber));
        kpi.appendChild(kpiCard("Laden", `${laden} · ${vs.length ? (laden / vs.length * 100).toFixed(0) : 0}%`, `≈ ${(ladenDwt / 1e6).toFixed(1)} m dwt laden · ${vs.length - laden} ballast`, C.green));
        kpi.appendChild(kpiCard("Under way (≥3 kn)", moving.toLocaleString(), `${vs.length - moving} stationary / at berth / anchorage`, C.cyan));
        kpi.appendChild(kpiCard("In repairs / yard", repairs.toLocaleString(), `${vs.filter(v => v.status === "WaitToLoad").length} waiting to load · ${vs.filter(v => v.status === "WaitToDischarge").length} waiting to discharge`, C.red));
        body.appendChild(kpi);

        // world map
        const mapDiv = el("div", { style: { height: "560px" } });
        body.appendChild(card(`Live positions — ${vs.length.toLocaleString()} vessels (● laden, ◇ ballast; colour = class; hover for details, drag to pan, toolbar to zoom)`, mapDiv));
        loadPlotly(() => {
          const traces = [];
          d.classes.forEach(cl => [true, false].forEach(ld => {
            const sub = vs.filter(v => v.cls === cl && v.laden === ld);
            if (!sub.length) return;
            traces.push({ type: "scattergeo", mode: "markers", name: `${cl} ${ld ? "laden" : "ballast"}`, lat: sub.map(v => v.lat), lon: sub.map(v => v.lon),
              marker: { size: cl === "VLCC" ? 8 : cl === "Suezmax" ? 6.5 : 5.5, color: CLASS_COL[cl], symbol: ld ? "circle" : "diamond-open", opacity: ld ? 0.9 : 0.75, line: { width: ld ? 0 : 1.2, color: CLASS_COL[cl] } },
              customdata: sub.map(v => [v.name || v.imo, v.status, v.spd, v.dest || "—", v.eta ? v.eta.replace("T", " ") : "—", v.area || "—", v.dwt ? v.dwt.toLocaleString() : "—", v.op || "—", v.imo]),
              hovertemplate: `<b>%{customdata[0]}</b> · ${cl} · %{customdata[6]} dwt<br>%{customdata[1]} · %{customdata[2]} kn · %{customdata[5]}<br>→ %{customdata[3]} ETA %{customdata[4]}<br>%{customdata[7]} · IMO %{customdata[8]}<extra></extra>` });
          }));
          Plotly.newPlot(mapDiv, traces, { ...plotLayout, xaxis: { ...AXB }, yaxis: { ...AXB }, margin: { t: 0, b: 0, l: 0, r: 0 }, legend: { ...plotLayout.legend, orientation: "h", y: 0.02, x: 0.5, xanchor: "center", bgcolor: "rgba(5,7,14,.6)" }, dragmode: "pan",
            geo: { projection: { type: "natural earth" }, showland: true, landcolor: "#0f172a", showocean: true, oceancolor: "#060a14", showcountries: true, countrycolor: "#1e293b", coastlinecolor: "#334155", showlakes: false, bgcolor: "rgba(0,0,0,0)", showframe: false, lataxis: { range: [-58, 75] }, lonaxis: { range: [-180, 180] } } }, { responsive: true, displayModeBar: true, displaylogo: false, modeBarButtonsToRemove: ["toImage", "select2d", "lasso2d"], scrollZoom: false });
        });

        // status by class + region distribution
        const two = el("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" } });
        const stDiv = el("div", { style: { height: "280px" } }); two.appendChild(card("Voyage status by class (all tracked vessels)", stDiv, { marginBottom: "0" }));
        const rgDiv = el("div", { style: { height: "280px" } }); two.appendChild(card("Where the fleet is — laden vs ballast by region", rgDiv, { marginBottom: "0" }));
        body.appendChild(two);
        loadPlotly(() => {
          const sts = STATUS_ORDER.filter(s => d.classes.some(cl => (d.by_status[cl] || {})[s]));
          Plotly.newPlot(stDiv, sts.map(s => ({ type: "bar", name: s, x: d.classes, y: d.classes.map(cl => (d.by_status[cl] || {})[s] || 0), marker: { color: STATUS_COL[s] } })), { ...plotLayout, xaxis: { ...AXB }, yaxis: { ...AXB }, barmode: "stack", margin: { t: 10, b: 40, l: 40, r: 10 } }, { responsive: true, displayModeBar: false });
          const rg = d.by_region.slice(0, 16);
          Plotly.newPlot(rgDiv, [{ type: "bar", name: "Laden", orientation: "h", y: rg.map(r => r.region), x: rg.map(r => r.Laden), marker: { color: C.green } }, { type: "bar", name: "Ballast", orientation: "h", y: rg.map(r => r.region), x: rg.map(r => r.Ballast), marker: { color: C.muted } }],
            { ...plotLayout, xaxis: { ...AXB }, yaxis: { ...AXB }, barmode: "stack", margin: { t: 10, b: 30, l: 150, r: 10 }, yaxis: { ...AXB, autorange: "reversed", tickfont: { size: 10 } } }, { responsive: true, displayModeBar: false });
        });

        // vessel table
        const sorted = vs.slice().sort((a, b) => (b.ts || "").localeCompare(a.ts || "") || (b.dwt || 0) - (a.dwt || 0)).slice(0, 400);
        const tw = table([
          { h: "Vessel", f: v => `<b>${esc(v.name || v.imo)}</b>` }, { h: "IMO", f: v => v.imo }, { h: "Class", f: v => v.cls, color: v => CLASS_COL[v.cls] }, { h: "DWT", num: true, f: v => v.dwt ? v.dwt.toLocaleString() : null }, { h: "Built", f: v => v.built },
          { h: "Status", f: v => v.status, color: v => STATUS_COL[v.status] || C.text }, { h: "Kn", num: true, f: v => v.spd }, { h: "Draught", num: true, f: v => v.draught }, { h: "Area", f: v => esc(v.area) }, { h: "Nearest port", f: v => esc(v.port) },
          { h: "AIS destination", f: v => esc(v.dest) }, { h: "Next port (Signal)", f: v => v.next_port ? esc(v.next_port) + (v.dest_area ? ` <span style="color:${C.muted}">${esc(v.dest_area)}</span>` : "") : null }, { h: "ETA", f: v => v.eta ? v.eta.replace("T", " ") : null },
          { h: "Operator", f: v => esc(v.op) }, { h: "Lat / Lon", f: v => `${v.lat}, ${v.lon}` }, { h: "AIS (UTC)", f: v => v.ts ? v.ts.replace("T", " ") : null, color: () => C.muted },
        ], sorted, { maxH: 480 });
        body.appendChild(card(`Vessel list — ${sorted.length.toLocaleString()}${vs.length > 400 ? ` of ${vs.length.toLocaleString()} (narrow with filters/search)` : ""} · newest AIS first`, tw));
        body.appendChild(stamp(d, `${d.source.laden_def} · positions older than 30 days excluded`));
      }

      // ── CRUDE FLOWS (voyages) ──
      async function loadFlows(force) {
        const fs = vstate.flows;
        if (!fs.data || force || fs.data.days !== fs.days) {
          body.innerHTML = `<div style="color:${C.muted};padding:30px;text-align:center">Loading ${fs.days}-day voyage flows from Signal…</div>`;
          try { fs.data = await (await fetch(`/api/signal/flows?days=${fs.days}${force ? "&refresh=1" : ""}`)).json(); }
          catch (e) { body.innerHTML = `<div style="color:${C.red};padding:30px">${e.message}</div>`; return; }
        }
        if (!fs.data.available) return failBox("voyages", fs.data);
        drawFlows();
      }
      function drawFlows() {
        const fs = vstate.flows, d = fs.data;
        body.innerHTML = "";
        const c = el("div", { style: { display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center", marginBottom: "14px" } });
        c.appendChild(lbl("WINDOW"));
        [90, 180, 365, 730].forEach(n => c.appendChild(pill(n >= 365 ? (n / 365) + "y" : n + "d", fs.days === n, () => { fs.days = n; loadFlows(false); })));
        c.appendChild(gap()); c.appendChild(lbl("LOAD REGION"));
        const srcSel = el("select", { style: { background: "#0b1220", color: C.text, border: `1px solid ${C.border}`, borderRadius: "6px", padding: "4px 8px", fontSize: "12px" } });
        const srcs = Object.keys(d.by_source).filter(s => s !== "Other").concat(["Other"]);
        ["ALL"].concat(srcs).forEach(s => { const o = el("option", { value: s }, s === "ALL" ? "All load regions" : s); if (s === fs.src) o.selected = true; srcSel.appendChild(o); });
        srcSel.addEventListener("change", () => { fs.src = srcSel.value; drawFlows(); }); c.appendChild(srcSel);
        c.appendChild(refreshBtn(() => loadFlows(true)));
        body.appendChild(c);

        const W = d.weeks.length, full = W - 1; // last week is partial
        const tot = fs.src === "ALL" ? d.total_bbl : (d.by_source[fs.src] || { bbl: [] }).bbl;
        const last4 = tot.slice(Math.max(0, full - 4), full), prev4 = tot.slice(Math.max(0, full - 8), full - 4);
        const avg = a => a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0;
        const l4 = avg(last4) / 7 / 1e3, p4 = avg(prev4) / 7 / 1e3;
        const ly = tot.slice(Math.max(0, full - 56), full - 48); const lyv = ly.length === 8 ? avg(ly.slice(0, 4)) / 7 / 1e3 : null;
        const onw = d.on_water.reduce((a, r) => a + r.bbl, 0), onwN = d.on_water.reduce((a, r) => a + r.n, 0), sanc = d.on_water.reduce((a, r) => a + r.sanctioned, 0);
        const kpi = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "10px", marginBottom: "14px" } });
        kpi.appendChild(kpiCard(`Dirty loadings · 4-wk avg${fs.src === "ALL" ? "" : " · " + fs.src}`, `${(l4/1000).toFixed(2)} mb/d`, `prior 4 wks ${(p4/1000).toFixed(2)} mb/d (${p4 ? ((l4 - p4) / p4 * 100 >= 0 ? "▲" : "▼") + Math.abs((l4 - p4) / p4 * 100).toFixed(0) + "%" : "—"})${lyv ? ` · yr-ago ${(lyv/1000).toFixed(2)}` : ""}`, C.amber));
        kpi.appendChild(kpiCard("Last full week", `${(tot[full - 1] / 1e6).toFixed(1)} mb`, `w/c ${d.weeks[full - 1]} · partial current wk ${(tot[W - 1] / 1e6).toFixed(1)} mb`, C.cyan));
        kpi.appendChild(kpiCard("Dirty cargo on the water", `${(onw / 1e6).toFixed(0)} mb`, `${onwN.toLocaleString()} laden voyages en route · VLCC ${((d.on_water_by_class.VLCC || {}).bbl / 1e6 || 0).toFixed(0)} / Suez ${((d.on_water_by_class.Suezmax || {}).bbl / 1e6 || 0).toFixed(0)} / Afra ${((d.on_water_by_class.Aframax || {}).bbl / 1e6 || 0).toFixed(0)} mb`, C.green));
        kpi.appendChild(kpiCard("On sanctioned vessels", `${onwN ? (sanc / onwN * 100).toFixed(0) : 0}%`, `${sanc} of ${onwN} en-route voyages flagged EU / OFAC / OFSI`, C.red));
        body.appendChild(kpi);

        const wkDiv = el("div", { style: { height: "360px" } });
        body.appendChild(card(`Weekly dirty loadings by load region — ${fs.src === "ALL" ? "top 12 regions, stacked" : fs.src + " by vessel class"} (mb / week; last bar is the partial current week)`, wkDiv));
        loadPlotly(() => {
          let traces;
          if (fs.src === "ALL") traces = srcs.map((s, i) => ({ type: "bar", name: s, x: d.weeks, y: d.by_source[s].bbl.map(v => v / 1e6), marker: { color: s === "Other" ? "#334155" : PAL[i % PAL.length] }, customdata: d.by_source[s].n, hovertemplate: "%{fullData.name}<br>%{y:.1f} mb · %{customdata} voyages<extra></extra>" }));
          else traces = [{ type: "bar", name: fs.src, x: d.weeks, y: d.by_source[fs.src].bbl.map(v => v / 1e6), marker: { color: C.amber }, customdata: d.by_source[fs.src].n, hovertemplate: "%{y:.1f} mb · %{customdata} voyages<extra></extra>" }];
          traces.push({ type: "scatter", mode: "lines", name: "4-wk avg (total)", x: d.weeks.slice(0, full), y: movAvg(tot.slice(0, full), 4).map(v => v / 1e6), line: { color: "#e8edf8", width: 1.5 } });
          Plotly.newPlot(wkDiv, traces, { ...plotLayout, xaxis: { ...AXB }, yaxis: { ...AXB }, barmode: "stack", yaxis: { ...AXB, title: { text: "mb / week", font: { size: 10, color: C.muted } } }, margin: { t: 10, b: 60, l: 50, r: 20 }, legend: { ...plotLayout.legend, font: { size: 10 } } }, { responsive: true, displayModeBar: false });
        });

        const clsDiv = el("div", { style: { height: "260px" } });
        const two = el("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginBottom: "14px" } });
        two.appendChild(card("Weekly loadings by vessel class (all regions, mb)", clsDiv, { marginBottom: "0" }));
        const cgDiv = el("div", { style: { height: "260px" } });
        two.appendChild(card("Dirty cargo mix — last 90 days of loadings", cgDiv, { marginBottom: "0" }));
        body.appendChild(two);
        loadPlotly(() => {
          Plotly.newPlot(clsDiv, d.classes.map(cl => ({ type: "bar", name: cl, x: d.weeks, y: d.by_class_bbl[cl].map(v => v / 1e6), marker: { color: CLASS_COL[cl] } })), { ...plotLayout, xaxis: { ...AXB }, yaxis: { ...AXB }, barmode: "stack", margin: { t: 10, b: 50, l: 45, r: 10 } }, { responsive: true, displayModeBar: false });
          const cg = d.cargo_90d.slice(0, 8);
          Plotly.newPlot(cgDiv, [{ type: "pie", hole: 0.55, labels: cg.map(x => x.cargo), values: cg.map(x => x.bbl), marker: { colors: PAL }, textinfo: "label+percent", textposition: "inside", insidetextorientation: "horizontal", textfont: { size: 10 }, hovertemplate: "%{label}<br>%{value:,.0f} bbl · %{percent}<extra></extra>" }], { ...plotLayout, xaxis: { ...AXB }, yaxis: { ...AXB }, showlegend: false, margin: { t: 10, b: 10, l: 10, r: 10 } }, { responsive: true, displayModeBar: false });
        });

        // origin→destination heatmap (90d)
        const mx = fs.src === "ALL" ? d.matrix_90d : d.matrix_90d.filter(r => r.src === fs.src);
        const srcTot = {}, dstTot = {}; mx.forEach(r => { srcTot[r.src] = (srcTot[r.src] || 0) + r.bbl; dstTot[r.dst] = (dstTot[r.dst] || 0) + r.bbl; });
        const S = Object.keys(srcTot).sort((a, b) => srcTot[b] - srcTot[a]).slice(0, 14), D = Object.keys(dstTot).sort((a, b) => dstTot[b] - dstTot[a]).slice(0, 16);
        const z = S.map(s => D.map(dd => { const r = mx.find(x => x.src === s && x.dst === dd); return r ? r.bbl / 1e6 : 0; }));
        const hmDiv = el("div", { style: { height: Math.max(300, 34 * S.length + 120) + "px" } });
        body.appendChild(card(`Load region → discharge region — last 90 days of loadings (mb; "Unknown / in transit" = discharge not yet declared)`, hmDiv));
        loadPlotly(() => {
          Plotly.newPlot(hmDiv, [{ type: "heatmap", z, x: D, y: S, colorscale: [[0, "#0b1220"], [0.25, "#1e3a5f"], [0.6, "#0e7490"], [1, "#f5b90f"]], showscale: true, colorbar: { thickness: 8, tickfont: { color: C.muted, size: 9 } }, hovertemplate: "%{y} → %{x}<br>%{z:.1f} mb<extra></extra>", text: z.map(r => r.map(v => v >= 1 ? v.toFixed(0) : "")), texttemplate: "%{text}", textfont: { size: 9, color: "#e8edf8" } }],
            { ...plotLayout, xaxis: { ...AXB }, yaxis: { ...AXB }, margin: { t: 10, b: 120, l: 160, r: 20 }, xaxis: { ...AXB, tickangle: -40, tickfont: { size: 10 } }, yaxis: { ...AXB, autorange: "reversed", tickfont: { size: 10 } } }, { responsive: true, displayModeBar: false });
        });

        const ow = table([{ h: "Discharge region (declared / estimated)", f: r => esc(r.dst) }, { h: "Voyages", num: true, f: r => r.n }, { h: "mb", num: true, f: r => (r.bbl / 1e6).toFixed(1) }, { h: "Share", num: true, f: r => (r.bbl / onw * 100).toFixed(1) + "%" }, { h: "Sanctioned vessels", num: true, f: r => r.sanctioned || null, color: () => C.red }], d.on_water.slice(0, 30), { maxH: 380 });
        body.appendChild(card(`Dirty cargo currently on the water by destination — ${(onw / 1e6).toFixed(0)} mb on ${onwN.toLocaleString()} laden voyages (sailed from load port, not yet arrived)`, ow));
        body.appendChild(stamp(d, `${d.source.filter} · week = ${d.source.date} · quantity = ${d.source.qty}`));
      }

      // ── TONNAGE LISTS ──
      const OPS_COL = { "Ballast Unfixed": C.green, "Ballast Fixed": C.cyan, "Discharging": "#60a5fa", "Waiting to Discharge": "#818cf8", "Laden": C.muted, "Loading": C.gold, "Waiting to Load": "#fb923c", "Repairs": C.red };
      const BUCKET_COL = ["#10b981", "#22d3ee", "#38bdf8", "#8b5cf6", "#475569"];
      async function loadTonnage(force) {
        const ts = vstate.tonnage;
        if (!ts.data || force || ts.data.days !== ts.days) {
          body.innerHTML = `<div style="color:${C.muted};padding:30px;text-align:center">Loading tonnage lists from Signal…</div>`;
          try { ts.data = await (await fetch(`/api/signal/tonnage?days=${ts.days}${force ? "&refresh=1" : ""}`)).json(); }
          catch (e) { body.innerHTML = `<div style="color:${C.red};padding:30px">${e.message}</div>`; return; }
        }
        if (!ts.data.available) return failBox("tonnage lists", ts.data);
        if (!ts.port || !ts.data.ports.some(p => p.port === ts.port)) ts.port = (ts.data.ports.find(p => p.port === "Ras Tanura") || ts.data.ports[0] || {}).port;
        drawTonnage();
      }
      function drawTonnage() {
        const ts = vstate.tonnage, d = ts.data;
        body.innerHTML = "";
        const c = el("div", { style: { display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center", marginBottom: "14px" } });
        c.appendChild(lbl("HISTORY"));
        [30, 90, 180, 365].forEach(n => c.appendChild(pill(n >= 365 ? "1y" : n + "d", ts.days === n, () => { ts.days = n; loadTonnage(false); })));
        c.appendChild(gap()); c.appendChild(lbl("LOAD PORT"));
        const pSel = el("select", { style: { background: "#0b1220", color: C.text, border: `1px solid ${C.border}`, borderRadius: "6px", padding: "4px 8px", fontSize: "12px" } });
        d.ports.slice().sort((a, b) => a.port.localeCompare(b.port)).forEach(p => { const o = el("option", { value: p.port }, `${p.port} (${p.area}) — ${p.config_classes.join("/")}`); if (p.port === ts.port) o.selected = true; pSel.appendChild(o); });
        pSel.addEventListener("change", () => { ts.port = pSel.value; drawTonnage(); }); c.appendChild(pSel);
        c.appendChild(refreshBtn(() => loadTonnage(true)));
        body.appendChild(c);

        const sumB = (p, cl, bs) => bs.reduce((a, b) => a + ((p.by_class_bucket[cl] || {})[b] || 0), 0);
        const promptAll = p => d.classes.reduce((a, cl) => a + sumB(p, cl, ["0-5", "6-10", "11-15"]), 0);
        // overview: prompt-available by port
        const kpi = el("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: "8px", marginBottom: "14px" } });
        d.ports.forEach(p => {
          const h = d.history[p.port]; let delta = null;
          if (h && d.history_dates.length > 8) { const tot = d.history_dates.map((_, i) => d.classes.reduce((a, cl) => a + (h[cl][i] || 0), 0)); const now = tot.slice(-1)[0], wk = tot[tot.length - 8]; delta = wk ? (now - wk) / wk * 100 : null; }
          const k = el("div", { style: { background: p.port === ts.port ? "#0f1a2e" : C.card, border: `1px solid ${p.port === ts.port ? C.amber : C.border}`, borderRadius: "10px", padding: "9px 11px", cursor: "pointer" }, onClick: () => { ts.port = p.port; drawTonnage(); } });
          k.appendChild(el("div", { style: { fontSize: "10.5px", color: C.muted, fontWeight: "700", textTransform: "uppercase", letterSpacing: ".4px" } }, `${p.port} · ${p.config_classes.join("/")}`));
          const row = el("div", { style: { display: "flex", alignItems: "baseline", gap: "6px", marginTop: "3px" } });
          row.appendChild(el("span", { style: { fontSize: "19px", fontWeight: "800", color: C.text } }, String(p.prompt_available)));
          row.appendChild(el("span", { style: { fontSize: "10px", color: C.muted } }, `open ≤15d · ${p.total} ≤30d`));
          k.appendChild(row);
          if (delta != null) k.appendChild(el("div", { style: { fontSize: "10.5px", color: delta >= 0 ? C.green : C.red } }, `${delta >= 0 ? "▲" : "▼"} ${Math.abs(delta).toFixed(0)}% vs 7d ago`));
          kpi.appendChild(k);
        });
        body.appendChild(kpi);

        const p = d.ports.find(x => x.port === ts.port); if (!p) return;
        const hasCls = d.classes.filter(cl => Object.values(p.by_class_bucket[cl] || {}).some(v => v));
        const two = el("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginBottom: "14px" } });
        const bDiv = el("div", { style: { height: "280px" } }); two.appendChild(card(`${p.port} — vessels by days to ETA and class (all statuses, ${d.as_of})`, bDiv, { marginBottom: "0" }));
        const oDiv = el("div", { style: { height: "280px" } }); two.appendChild(card(`${p.port} — operational status of vessels within 30 days`, oDiv, { marginBottom: "0" }));
        body.appendChild(two);
        loadPlotly(() => {
          Plotly.newPlot(bDiv, hasCls.map(cl => ({ type: "bar", name: cl, x: d.buckets.map(b => b + " d"), y: d.buckets.map(b => p.by_class_bucket[cl][b] || 0), marker: { color: CLASS_COL[cl] } })), { ...plotLayout, xaxis: { ...AXB }, yaxis: { ...AXB }, barmode: "group", margin: { t: 10, b: 40, l: 40, r: 10 }, xaxis: { ...AXB, type: "category" }, yaxis: { ...AXB, title: { text: "vessels", font: { size: 10, color: C.muted } } } }, { responsive: true, displayModeBar: false });
          const ops = Object.entries(p.by_ops).sort((a, b) => b[1] - a[1]);
          Plotly.newPlot(oDiv, [{ type: "bar", orientation: "h", y: ops.map(o => o[0]), x: ops.map(o => o[1]), marker: { color: ops.map(o => OPS_COL[o[0]] || C.muted) }, text: ops.map(o => o[1]), textposition: "outside", textfont: { color: C.text, size: 10 } }], { ...plotLayout, xaxis: { ...AXB }, yaxis: { ...AXB }, margin: { t: 10, b: 30, l: 140, r: 40 }, xaxis: { ...AXB, type: "linear" }, yaxis: { ...AXB, type: "category", autorange: "reversed" } }, { responsive: true, displayModeBar: false });
        });

        const h = d.history[p.port];
        const hDiv = el("div", { style: { height: "300px" } });
        body.appendChild(card(`${p.port} — open tonnage able to arrive within 15 days, daily history (${d.history_def})`, hDiv));
        loadPlotly(() => {
          const traces = h ? d.classes.filter(cl => h[cl].some(v => v)).map(cl => ({ type: "bar", name: cl, x: d.history_dates, y: h[cl], marker: { color: CLASS_COL[cl] } })) : [];
          if (h) { const tot = d.history_dates.map((_, i) => d.classes.reduce((a, cl) => a + (h[cl][i] || 0), 0)); traces.push({ type: "scatter", mode: "lines", name: "7d avg", x: d.history_dates, y: movAvg(tot, 7), line: { color: "#e8edf8", width: 1.5 } }); }
          Plotly.newPlot(hDiv, traces, { ...plotLayout, xaxis: { ...AXB }, yaxis: { ...AXB }, barmode: "stack", margin: { t: 10, b: 50, l: 40, r: 10 }, yaxis: { ...AXB, title: { text: "open vessels ≤15d", font: { size: 10, color: C.muted } } } }, { responsive: true, displayModeBar: false });
        });

        // all-ports summary table
        const tw = table([
          { h: "Load port", f: r => `<b>${esc(r.port)}</b> <span style="color:${C.muted}">${esc(r.area)}</span>` }, { h: "List class", f: r => r.config_classes.join(" / ") },
          { h: "Open ≤15d", num: true, f: r => r.prompt_available, color: () => C.green }, { h: "Total ≤30d", num: true, f: r => r.total },
          ...d.classes.map(cl => ({ h: cl + " ≤15d", num: true, f: r => sumB(r, cl, ["0-5", "6-10", "11-15"]) || null, color: () => CLASS_COL[cl] })),
          { h: "Ballast unfixed", num: true, f: r => r.by_ops["Ballast Unfixed"] || null }, { h: "Ballast fixed", num: true, f: r => r.by_ops["Ballast Fixed"] || null }, { h: "Laden", num: true, f: r => r.by_ops["Laden"] || null }, { h: "On subs / poss. fixed", num: true, f: r => ((r.by_com["On Subs"] || 0) + (r.by_com["Poss Fixed"] || 0)) || null },
          { h: "Spot", num: true, f: r => r.by_dep["Spot"] || null }, { h: "Programme / TC", num: true, f: r => ((r.by_dep["Program"] || 0) + (r.by_dep["Contract"] || 0) + (r.by_dep["Relet"] || 0)) || null },
        ], d.ports, { maxH: 460 });
        body.appendChild(card(`All configured load ports — tonnage list ${d.as_of}`, tw));
        body.appendChild(stamp(d, `configurations from ${d.source.config} · distinct vessels per port/day · negative DaysToETA (already passed) excluded`));
      }

      async function load(reset, force) {
        if (reset) { body.innerHTML = `<div style="color:${C.muted};padding:30px;text-align:center">Loading ${state.days}-day passages from Signal…</div>`; }
        try {
          if (!state.status || force) {
            state.status = await (await fetch("/api/signal/status")).json();
          }
          if (!state.status.connected) { setPill("● OFFLINE", C.red); renderControls(); renderNotConnected(state.status); return; }
          setPill(`● CONNECTED · ${state.status.database || "SQL"}`, C.green);
          const r = await fetch(`/api/signal/passages?days=${state.days}${force ? "&refresh=1" : ""}`);
          const d = await r.json();
          state.data = d;
          if (state.view !== "passages") return;
          if (!d.available) {
            renderControls(); body.innerHTML = "";
            const why = d.reason === "no_passages_table" ? "Connected, but no table with strait/passage columns was auto-detected — browse the tables below and tell me which one holds the transits (or set SIGNAL_PASSAGES_SQL)." : `Error reading passages: ${d.error || d.reason}`;
            body.appendChild(card(null, why));
            await renderSchemaExplorer();
            return;
          }
          draw();
        } catch (e) {
          setPill("● ERROR", C.red);
          body.innerHTML = `<div style="color:${C.red};padding:30px">Failed to load Signal data: ${e.message}</div>`;
        }
      }
      renderSubnav();
      renderControls();
      load(true);
    }

    // Global theme styles
    const gstyle = document.createElement("style");
    gstyle.textContent = `
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
      #mp-overlay, #mp-overlay * { font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif; }
      #mp-overlay ::-webkit-scrollbar { width: 9px; height: 9px; }
      #mp-overlay ::-webkit-scrollbar-track { background: #070b14; }
      #mp-overlay ::-webkit-scrollbar-thumb { background: #1c2740; border-radius: 5px; }
      #mp-overlay ::-webkit-scrollbar-thumb:hover { background: #2a3a5c; }
      .mp-nav-item { display:flex; align-items:center; gap:10px; width:100%; text-align:left; padding:9px 14px 9px 16px;
        background:transparent; border:none; border-left:3px solid transparent; color:#7e8ba8; cursor:pointer;
        font-size:12.5px; font-weight:600; letter-spacing:0.2px; transition: all .15s ease; border-radius:0 8px 8px 0; }
      .mp-nav-item:hover { background:rgba(56,189,248,0.06); color:#cdd8ec; }
      .mp-nav-item.active { background:linear-gradient(90deg, rgba(56,189,248,0.14), rgba(56,189,248,0.02));
        border-left:3px solid #38bdf8; color:#38bdf8; }
      .mp-nav-group { font-size:9.5px; font-weight:800; letter-spacing:2px; color:#4a5670; padding:16px 16px 6px; text-transform:uppercase; }
      @keyframes mp-live { 0%,100% { opacity:1; } 50% { opacity:0.35; } }
    `;
    document.head.appendChild(gstyle);

    // Overlay = main app shell (sidebar + content)
    const overlay = el("div", { id: "mp-overlay", style: { position: "fixed", inset: "0", background: `radial-gradient(1200px 700px at 80% -10%, rgba(56,189,248,0.07), transparent), ${C.bg}`, zIndex: "100000", display: "flex", flexDirection: "column", overflow: "hidden" } });

    // ── Top header bar ──
    const topBar = el("div", { style: { background: "rgba(9,13,24,0.92)", backdropFilter: "blur(8px)", borderBottom: `1px solid ${C.border}`, padding: "0 22px", display: "flex", alignItems: "center", justifyContent: "space-between", height: "54px", flexShrink: "0" } });
    const brand = el("div", { style: { display: "flex", alignItems: "center", gap: "12px" } });
    brand.appendChild(el("div", { style: { width: "30px", height: "30px", borderRadius: "8px", background: "linear-gradient(135deg,#38bdf8,#8b5cf6)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "16px", boxShadow: "0 0 18px rgba(56,189,248,0.45)" } }, "🛢"));
    const brandTxt = el("div", {});
    brandTxt.appendChild(el("div", { style: { fontSize: "14.5px", fontWeight: "800", color: C.text, letterSpacing: "1.5px" } }, "BARREL TERMINAL"));
    brandTxt.appendChild(el("div", { style: { fontSize: "9px", fontWeight: "600", color: C.muted, letterSpacing: "2.5px" } }, "CRUDE & PRODUCTS MARKET INTELLIGENCE"));
    brand.appendChild(brandTxt);
    topBar.appendChild(brand);
    const hdrRight = el("div", { style: { display: "flex", alignItems: "center", gap: "16px" } });
    const liveDot = el("span", { style: { display: "inline-block", width: "8px", height: "8px", borderRadius: "50%", background: C.green, animation: "mp-live 1.6s ease-in-out infinite", marginRight: "6px" } });
    const liveWrap = el("span", { style: { fontSize: "10.5px", fontWeight: "700", color: C.green, letterSpacing: "1.5px" } });
    liveWrap.appendChild(liveDot); liveWrap.appendChild(document.createTextNode("LIVE"));
    hdrRight.appendChild(liveWrap);
    const clock = el("span", { style: { fontSize: "12px", fontWeight: "600", color: C.muted, fontVariantNumeric: "tabular-nums" } });
    const tick = () => { clock.textContent = new Date().toISOString().slice(0, 16).replace("T", "  ") + " UTC"; };
    tick(); setInterval(tick, 15000);
    hdrRight.appendChild(clock);
    topBar.appendChild(hdrRight);
    overlay.appendChild(topBar);

    // ── Body: sidebar + content ──
    const body = el("div", { style: { flex: "1", display: "flex", overflow: "hidden" } });

    const navGroups = [
      { name: "Intelligence", items: [
        { id: "mktcomm", label: "Market Commentary", icon: "🧭" },
        { id: "xmkt", label: "Cross-Market", icon: "🧠" },
      ]},
      { name: "Positioning & Pricing", items: [
        { id: "mp", label: "Money Positioning", icon: "💰" },
        { id: "voloi", label: "Volume & OI Tracker", icon: "📊" },
        { id: "pricing", label: "Pricing", icon: "🏷️" },
        { id: "margins", label: "Refinery Margins", icon: "📈" },
      ]},
      { name: "Balances & Stocks", items: [
        { id: "gb", label: "Gasoline Balances", icon: "⛽" },
        { id: "jodi", label: "JODI Global", icon: "🌍" },
        { id: "cbm", label: "Crude Balances", icon: "🛢️" },
        { id: "lgb", label: "Local Gasoline Bal", icon: "⛽" },
        { id: "eabal", label: "Local Balances", icon: "🌐" },
        { id: "gs", label: "Gasoline Stocks", icon: "📊" },
        { id: "ps", label: "Product Stocks", icon: "🛢️" },
      ]},
      { name: "Refineries", items: [
        { id: "gspe", label: "Genscape Refinery", icon: "🏭" },
        { id: "gseu", label: "Genscape Europe", icon: "🇪🇺" },
        { id: "iir", label: "IIR Turnarounds", icon: "🔧" },
      ]},
      { name: "Platts / SPGCI", items: [
        { id: "platts", label: "Platts", icon: "🅿️" },
      ]},
      { name: "Flows & Data", items: [
        { id: "signal", label: "Signal", icon: "📡" },
        { id: "kpler", label: "Kpler Flows", icon: "🚢" },
        { id: "ktf", label: "Kpler Refinery Flows", icon: "🏭" },
        { id: "kinv", label: "Kpler Inventories", icon: "🛢️" },
        { id: "ksql", label: "Kpler SQL Sync", icon: "🔄" },
      ]},
    ];
    const tabs = navGroups.flatMap(g => g.items);
    const firstTab = "mktcomm";

    const sidebar = el("div", { style: { width: "228px", flexShrink: "0", background: "rgba(8,12,22,0.85)", borderRight: `1px solid ${C.border}`, overflowY: "auto", paddingBottom: "20px" } });
    const btns = {}, panes = {};
    navGroups.forEach(g => {
      sidebar.appendChild(el("div", { class: "mp-nav-group" }, g.name));
      g.items.forEach(t => {
        const b = el("button", { class: "mp-nav-item" + (t.id === firstTab ? " active" : ""), onClick: () => switchTab(t.id) },
          [el("span", { style: { fontSize: "14px", width: "18px", textAlign: "center" } }, t.icon), el("span", {}, t.label)]);
        btns[t.id] = b;
        sidebar.appendChild(b);
      });
    });
    body.appendChild(sidebar);

    // Content
    const content = el("div", { style: { flex: "1", overflowY: "auto", padding: "22px 26px" } });
    tabs.forEach(t => {
      const p = el("div", { style: { display: t.id === firstTab ? "block" : "none", maxWidth: "1400px", margin: "0 auto" } });
      panes[t.id] = p;
      content.appendChild(p);
    });
    body.appendChild(content);
    overlay.appendChild(body);

    function switchTab(id) {
      tabs.forEach(t => {
        btns[t.id].classList.toggle("active", t.id === id);
        panes[t.id].style.display = t.id === id ? "block" : "none";
      });
      content.scrollTop = 0;
      if (id === "mp" && !panes.mp._loaded) { panes.mp._loaded = true; renderMP(panes.mp); }
      if (id === "pricing" && !panes.pricing._loaded) { panes.pricing._loaded = true; renderPricing(panes.pricing); }
      if (id === "gb" && !panes.gb._loaded) { panes.gb._loaded = true; renderGBal(panes.gb); }
      if (id === "jodi" && !panes.jodi._loaded) { panes.jodi._loaded = true; renderJODI(panes.jodi); }
      if (id === "kpler" && !panes.kpler._loaded) { panes.kpler._loaded = true; renderKpler(panes.kpler); }
      if (id === "mktcomm" && !panes.mktcomm._loaded) { panes.mktcomm._loaded = true; renderMarketCommentary(panes.mktcomm); }
      if (id === "xmkt" && !panes.xmkt._loaded) { panes.xmkt._loaded = true; renderCrossMarket(panes.xmkt); }
      if (id === "gspe" && !panes.gspe._loaded) { panes.gspe._loaded = true; renderGenscape(panes.gspe); }
      if (id === "gseu" && !panes.gseu._loaded) { panes.gseu._loaded = true; renderGspeEurope(panes.gseu); }
      if (id === "iir" && !panes.iir._loaded) { panes.iir._loaded = true; renderIIR(panes.iir); }
      if (id === "cbm" && !panes.cbm._loaded) { panes.cbm._loaded = true; renderCBM(panes.cbm); }
      if (id === "margins" && !panes.margins._loaded) { panes.margins._loaded = true; renderMargins(panes.margins); }
      if (id === "lgb" && !panes.lgb._loaded) { panes.lgb._loaded = true; renderLEM(panes.lgb); }
      if (id === "eabal" && !panes.eabal._loaded) { panes.eabal._loaded = true; renderEABal(panes.eabal); }
      if (id === "gs" && !panes.gs._loaded) { panes.gs._loaded = true; renderGS(panes.gs); }
      if (id === "ps" && !panes.ps._loaded) { panes.ps._loaded = true; renderPS(panes.ps); }
      if (id === "voloi" && !panes.voloi._loaded) { panes.voloi._loaded = true; renderVOLOI(panes.voloi); }
      if (id === "platts" && !panes.platts._loaded) { panes.platts._loaded = true; renderPlatts(panes.platts); }
      if (id === "ktf" && !panes.ktf._loaded) { panes.ktf._loaded = true; renderKTF(panes.ktf); }
      if (id === "kinv" && !panes.kinv._loaded) { panes.kinv._loaded = true; renderKINV(panes.kinv); }
      if (id === "ksql" && !panes.ksql._loaded) { panes.ksql._loaded = true; renderKSQL(panes.ksql); }
      if (id === "signal" && !panes.signal._loaded) { panes.signal._loaded = true; renderSignal(panes.signal); }
    }

    document.body.appendChild(overlay);

    // Launch directly into the terminal on the first tab
    panes[firstTab]._loaded = true;
    renderMarketCommentary(panes[firstTab]);
  }

  function init() {
    if (document.getElementById("root")) setTimeout(inject, 1500);
    else setTimeout(init, 500);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();

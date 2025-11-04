# app.py — Single-file Flask web app for a basic portfolio optimizer
# ---------------------------------------------------------------
# Quick start:
#   1) python -m venv .venv && source .venv/bin/activate  (Windows: .venv\\Scripts\\activate)
#   2) pip install flask yfinance numpy pandas
#   3) python app.py
#   4) Open http://127.0.0.1:5000
#
# Notes:
# - Uses your simple weighting rules (low = inverse volatility, medium = equal, high = return-tilt)
# - Pulls daily data via yfinance, annualizes stats, returns weights + metrics
# - Minimal frontend with a form and results table (no build tools required)
# - Great as an MVP you can later split into a proper API + React frontend

from __future__ import annotations
from flask import Flask, request, jsonify, render_template_string, send_file
from datetime import date
import numpy as np
import pandas as pd
import yfinance as yf
import riskfolio as rp
from io import BytesIO
import matplotlib
matplotlib.use("Agg")
from scipy.optimize import minimize
import random
from datetime import datetime


import warnings
warnings.filterwarnings("ignore")

app = Flask(__name__)

# ----------------------------
# HTML (inline for single-file)
# ----------------------------
INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Portfolio Builder</title>
  <style>
    :root { --bg:#0b1020; --panel:#131a33; --txt:#e6ebff; --muted:#9aa4d6; --accent:#8bb0ff; }
    *{ box-sizing: border-box; }
    body { margin:0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; background:var(--bg); color:var(--txt); }
    .wrap { max-width:1000px; margin: 32px auto; padding: 0 16px; }
    .card { background:var(--panel); border-radius:16px; padding:20px; box-shadow: 0 10px 30px rgba(0,0,0,.25); }
    h1 { margin:0 0 16px; font-size: 24px; }
    p { color:var(--muted); }
    label { display:block; font-weight:600; margin: 16px 0 8px; }
    input, select, textarea { width:100%; padding:12px; border-radius:10px; border:1px solid #2a3568; background:#0f152b; color:var(--txt); }
    textarea { min-height:72px; resize: vertical; }
    .row { display:grid; gap:12px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .row-3 { display:grid; gap:12px; grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .btn { margin-top:16px; padding:12px 16px; border:0; border-radius:12px; background:linear-gradient(90deg, #5d82ff, #8bb0ff); color:#0b1020; font-weight:800; cursor:pointer; }
    .btn:disabled{ opacity:.6; cursor:not-allowed; }
    .results { margin-top:24px; }
    table { width:100%; border-collapse: collapse; }
    th, td { text-align:left; padding:10px 8px; border-bottom: 1px solid #273066; font-variant-numeric: tabular-nums; }
    .kpi { display:grid; gap:12px; grid-template-columns: repeat(4, minmax(0, 1fr)); margin-top:16px; }
    .kpi .box { background:#0f152b; border:1px solid #263068; padding:12px; border-radius:12px; }
    .err { color:#ffb4b4; font-weight:600; }
    .hint { font-size: 12px; color: var(--muted); margin-top: 4px; }
    .footer { margin-top: 28px; color: var(--muted); font-size: 12px; text-align:center; }
    /* --- KPI info popovers --- */
  .info {
    display:inline-flex; align-items:center; justify-content:center;
    width:18px; height:18px; margin-left:6px; border-radius:50%;
    border:1px solid #2a3568; font-size:12px; font-weight:800; cursor:pointer;
    color:var(--accent); background:#0f152b;
  }
  .tooltip {
    position:absolute; z-index:10; max-width:340px;
    background:#0f152b; color:var(--txt);
    border:1px solid #263068; border-radius:10px; padding:10px 12px;
    box-shadow:0 10px 30px rgba(0,0,0,.35); font-size:13px; line-height:1.35;
  }
  .tooltip .tt-title { font-weight:700; margin-bottom:6px; color:#cfe0ff; }
  .tooltip .tt-note { margin-top:6px; color:var(--muted); font-size:12px; }

  .tabbar { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
  .tabbar .pill {
    padding:6px 10px; border-radius:999px; border:1px solid #2a3568;
    background:#0f152b; color:var(--txt); cursor:pointer; font-weight:700;
    font-size:13px; line-height:1;
  }
  .tabbar .pill.active { background:#5d82ff; color:#0b1020; border-color:#5d82ff; }
  .tabbar .metric { color:var(--muted); font-size:12px; margin-left:4px; font-weight:600; }

  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Portfolio Builder (MVP)</h1>
      <p>Enter tickers, pick a risk level, choose a date range, and get a simple optimized allocation. This is a demo — not financial advice.</p>

      <div class="row-3">
        <div>
          <label>Risk level</label>
          <select id="riskLevel">
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </div>
        <div>
          <label>Investment amount (optional)</label>
          <input id="amount" type="number" step="100" placeholder="10000" />
          <div class="hint">If provided, we’ll estimate dollar allocations.</div>
        </div>
        <div>
          <label>Investment period</label>
            <input id="investmentPeriod" type="number" min="1" step="1" value="3" />
            <div class="hint">We’ll use full calendar years ending last year. For example, 3 = 2022–2024.</div>
        </div>
      </div>


      <label style="margin-top:12px;">Tickers (comma-separated)</label>
      <textarea id="tickers" placeholder="AAPL, AMZN, PFE">AAPL, AMZN, PFE</textarea>

      <button id="go" class="btn" type="button">Optimize</button>
      <div id="error" class="err" style="display:none; margin-top:12px;"></div>

      <div class="results" id="results" style="display:none;">
        <div class="kpi">
        <div class="box">
          <div>Expected Annual Return
            <button class="info" type="button" data-metric="return">i</button>
          </div>
          <div id="expRet" style="font-size:20px; font-weight:800;"></div>
        </div>

        <div class="box">
          <div>Portfolio Volatility
            <button class="info" type="button" data-metric="volatility">i</button>
          </div>
          <div id="volatility" style="font-size:20px; font-weight:800;"></div>
        </div>

        <div class="box">
          <div>Sharpe Ratio
            <button class="info" type="button" data-metric="sharpe">i</button>
          </div>
          <div id="sharpe" style="font-size:20px; font-weight:800;"></div>
        </div>

        <div class="box">
          <div>Risk-free Rate</div>
          <div id="rfNote" style="font-size:20px; font-weight:800;"></div>
        </div>
        </div>

        <!-- Compact strategy bar -->
        <div class="tabbar" id="strategyBar" style="margin-top:8px"></div>
        <div id="strategyInfo" class="hint" style="margin:8px 0 6px;"></div>

        <h3 style="margin-top:20px;">Allocation</h3>
        <table id="table"></table>

        <h3 style="margin-top:28px;">Efficient Frontier</h3>
        <div class="row-3" style="align-items:end">
          <div>
            <label>Risk dial (0 = Min-Var, 100 = Max Sharpe)</label>
            <input id="riskDial" type="range" min="0" max="100" step="1" value="75" />
            <div class="hint">Slide to see how the <strong>Suggested</strong> point moves along the frontier.</div>
            <div class="hint">Double-click to reset frontier.</div>
          </div>
          <div>
          </div>
        </div>

        <div id="frontierError" class="err" style="display:none; margin-top:12px;"></div>

        <canvas id="frontierCanvas" width="900" height="360"
          style="margin-top:12px; width:100%; max-width:1000px; background:#0f152b; border:1px solid #263068; border-radius:12px;">
        </canvas>


        <div id="optWeights" class="hint" style="margin-top:10px;"></div>
      </div>

      <div class="footer">Demo tool for educational purposes only.</div>
    </div>
  </div>

<script>
document.addEventListener('DOMContentLoaded', function () {
  // ---- tiny helpers ----
  function $(id){ return document.getElementById(id); }
  function pct(x){ return (100*x).toFixed(2) + '%'; }

  // ---- strategy explanations (shown under the pill bar) ----
  const STRAT_EXPLAIN = {
  "Suggested": `
    This is the portfolio built specifically for <strong>your comfort with risk</strong>.
    <ul style="margin-top:6px;">
      <li><strong>Low risk:</strong> focuses on stable, steady performers so your portfolio changes less day to day — great if you’d rather protect your money than chase big growth.</li>
      <li><strong>Medium risk:</strong> spreads money evenly across assets for balance — some growth, some safety. It’s a “set it and forget it” type of portfolio.</li>
      <li><strong>High risk:</strong> tilts toward higher-return stocks that can swing more, aiming for faster long-term growth. Best if you can handle short-term ups and downs for better potential rewards later.</li>
    </ul>
    Think of it like a “personalized blend” — the portfolio automatically adjusts its balance of stability and growth to fit <em>you</em>.
  `,

  "Min-Variance": `
    This is the <strong>most stable portfolio</strong> possible for your chosen assets.  
    It minimizes risk and volatility — meaning it tries to keep your portfolio’s value from jumping up and down too much.  
    Investors often use this as a <em>benchmark for safety</em>: it shows the lowest level of risk you could take without holding cash.
    <br>NOTE: this portfolio is not dependent on your chosen risk level.
  `,

  "Max Sharpe": `
    This is the <strong>best risk-adjusted portfolio</strong>: it aims to get you the most return for every unit of risk taken.  
    In plain terms, it’s what professional investors would call the “sweet spot” — the most efficient trade-off between earning more and not taking on unnecessary risk.  
    You can compare your suggested portfolio to this one to see how efficiently your risk level is working for you.
    <br>NOTE: this portfolio is not dependent on your chosen risk level.
  `
};

  // ---- render KPIs + table for a chosen strategy ----
  function renderAllocationFromStrategy(strategy, assetStats) {
    // KPIs
    $('expRet').textContent = pct(strategy.metrics.expected_return);
    $('volatility').textContent = pct(strategy.metrics.portfolio_volatility);
    $('sharpe').textContent = (strategy.metrics.sharpe_ratio).toFixed(2);

    // Table rows (using per-asset ER/Vol we built from server data)
    const header = ['Ticker','Weight','Expected Return','Volatility','Dollars (optional)'];
    const rows = [header];
    strategy.weights.forEach(w => {
      const t = w.Ticker;
      const s = assetStats[t] || { er: NaN, vol: NaN, dollars: null };
      rows.push([
        t,
        pct(w.Weight),
        pct(s.er),
        pct(s.vol),
        (s.dollars != null ? ('$' + s.dollars.toLocaleString()) : '')
      ]);
    });

    // Render table
    let html = '';
    rows.forEach((r, i) => {
      html += '<tr>';
      r.forEach(cell => { const tag = (i===0 ? 'th':'td'); html += `<${tag}>${cell}</${tag}>`; });
      html += '</tr>';
    });
    $('table').innerHTML = html;
  }

  // ---- compact pill bar to switch among strategies ----
  function buildStrategyBar(strategies, assetStats) {
    const bar  = $('strategyBar');
    const info = $('strategyInfo');
    bar.innerHTML = '';

    strategies.forEach((s, i) => {
      const pill = document.createElement('button');
      pill.className = 'pill';
      pill.dataset.sel = String(i);

      // Shorten "Suggested (high)" etc. to "Suggested"
      const short = s.name.replace(/^Suggested.*\)/, 'Suggested');
      pill.innerHTML =
        `${short}<span class="metric"> • ER ${(s.metrics.expected_return*100).toFixed(1)}% • σ ${(s.metrics.portfolio_volatility*100).toFixed(1)} • S ${s.metrics.sharpe_ratio.toFixed(2)}</span>`;

      // minimal pill styles (kept inline to avoid editing your <style> block)
      pill.style.padding = '6px 10px';
      pill.style.borderRadius = '999px';
      pill.style.border = '1px solid #2a3568';
      pill.style.background = '#0f152b';
      pill.style.color = 'var(--txt)';
      pill.style.cursor = 'pointer';
      pill.style.fontWeight = '700';
      pill.style.fontSize = '13px';
      pill.style.lineHeight = '1';

      bar.appendChild(pill);
    });

    // ensure flex container
    bar.style.display = 'flex';
    bar.style.flexWrap = 'wrap';
    bar.style.gap = '8px';
    bar.style.alignItems = 'center';

    function setActive(i){
      // mark active
      [...bar.querySelectorAll('.pill')].forEach((el, k) => {
        if (k === i) {
          el.style.background = '#5d82ff';
          el.style.borderColor = '#5d82ff';
          el.style.color = '#0b1020';
        } else {
          el.style.background = '#0f152b';
          el.style.borderColor = '#2a3568';
          el.style.color = 'var(--txt)';
        }
      });

      // render chosen strategy
      const strat = strategies[i];
      renderAllocationFromStrategy(strat, assetStats);

      // explanation
      const base = STRAT_EXPLAIN[strat.name]
                || STRAT_EXPLAIN[strat.name.split(' ')[0]]
                || '';
      info.innerHTML = `<strong>${strat.name}</strong> — ${strat.blurb}<br>${base}`;
    }

    // click handlers
    bar.querySelectorAll('.pill').forEach(btn => {
      btn.addEventListener('click', () => setActive(parseInt(btn.dataset.sel,10)));
    });

    // default to Suggested if present
    let start = strategies.findIndex(s => /^Suggested/.test(s.name));
    if (start < 0) start = 0;
    if (strategies.length) setActive(start);
  }

  // =================== OPTIMIZE ===================
  const goBtn = $('go');
  if (!goBtn) { console.error('No #go button'); return; }

  goBtn.addEventListener('click', async function () {
    $('error').style.display   = 'none';
    $('results').style.display = 'none';
    goBtn.disabled = true;

    try {
      const tickers = $('tickers').value.split(',').map(t => t.trim().toUpperCase()).filter(Boolean);
      const risk_level = $('riskLevel').value;
      const amount = parseFloat($('amount').value) || null;
      const investment_period = parseInt($('investmentPeriod').value, 10) || 3;

      const res = await fetch('/optimize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tickers, risk_level, investment_period, amount })
      });
      if (!res.ok) throw new Error((await res.text()) || 'Request failed');

      const data = await res.json();

      // risk-free note
      const rfPct  = data.metrics.risk_free_rate;
      const rfAsOf = data.metrics.risk_free_rate_asof;
      $('rfNote').innerHTML =
        '<strong>13W T-bill:</strong> ' + rfPct.toFixed(2) + '%<br>' +
        '<span style="font-size: 11px; color: var(--muted);">As of ' + rfAsOf + '</span>';

      // Build a quick per-asset stats lookup from server’s “portfolio” array
      const assetStats = {};
      (data.portfolio || []).forEach(r => {
        assetStats[r.Ticker] = {
          er: r.Expected_Return,
          vol: r.volatility,
          dollars: (typeof r.Dollars === 'number') ? r.Dollars : null
        };
      });

      // Build the pill bar and auto-render Suggested
      const strategies = (data.strategies || []).filter(s =>
      /^Suggested/.test(s.name) || s.name === 'Min-Variance' || s.name === 'Max Sharpe'
    );
    buildStrategyBar(strategies, assetStats);

      $('results').style.display = 'block';
    } catch (err) {
      console.error(err);
      $('error').textContent = err && err.message ? err.message : String(err);
      $('error').style.display = 'block';
    } finally {
      goBtn.disabled = false;
    }
    
    if (window.__refreshFrontier) { window.__refreshFrontier(); }

  });

// ---------- FRONTIER: compute + draw (fixed view, no zoom/pan) ----------
(function () {
  const canvas = $('frontierCanvas');
  const ctx = canvas.getContext('2d');
  const dial = $('riskDial');

  // shared state
  let F = null;                 // payload from /frontier
  let dataBounds = null;        // full data bounds
  let view = null;              // current view (fixed = dataBounds)
  let suggestedOverride = null; // {vol,ret} when dial moves

  // plot constants/helpers
  const PAD = 40;
  const X_TICK_PX = 90;
  const Y_TICK_PX = 70;

  function plotWidth(){  return canvas.width  - 2*PAD; }
  function plotHeight(){ return canvas.height - 2*PAD; }
  function X(v){ return PAD + (v - view.xMin) * (plotWidth()) / (view.xMax - view.xMin || 1); }
  function Y(v){ return canvas.height - PAD - (v - view.yMin) * (plotHeight()) / (view.yMax - view.yMin || 1); }
  function pct0(x){ return (100*x).toFixed(0) + '%'; }

  function niceStep(span, approxCount){
    if (span <= 0 || !isFinite(span)) return 1;
    const raw = span / Math.max(1, approxCount);
    const pow10 = Math.pow(10, Math.floor(Math.log10(raw)));
    const mults = [1, 2, 2.5, 5, 10];
    for (const m of mults){ const s = m*pow10; if (raw <= s) return s; }
    return 10*pow10;
  }
  function makeTicks(min, max, pxSize){
    const span = max - min;
    const approx = Math.max(4, Math.floor(pxSize / (pxSize === plotWidth() ? X_TICK_PX : Y_TICK_PX)));
    const step = niceStep(span, approx);
    const start = Math.ceil(min / step) * step;
    const out = [];
    for (let v = start; v <= max + 1e-12; v += step) out.push(v);
    return out;
  }

  // set initial/fixed view — left edge clamped to 0 so CML origin is always visible
  function setInitialView(payload){
    const xs = payload.cloud.vol.concat(payload.frontier.vol, [
      payload.points.min_var.vol, payload.points.max_sharpe.vol, payload.points.suggested.vol
    ]);
    const ys = payload.cloud.ret.concat(payload.frontier.ret, [
      payload.points.min_var.ret, payload.points.max_sharpe.ret, payload.points.suggested.ret
    ]);

    const padX = 0.06 * Math.max(...xs);
    const padY = 0.10 * Math.max(...ys.map(Math.abs));

    const xMax = Math.max(...xs) + padX;
    const yMin = Math.min(...ys) - padY;
    const yMax = Math.max(...ys) + padY;

    dataBounds = { xMin: 0, xMax, yMin, yMax }; // lock left to 0
    view = { ...dataBounds };                    // fixed view
  }

  function draw(){
    if (!F || !view) return;
    ctx.clearRect(0,0,canvas.width,canvas.height);

    // grid + axes with more tick labels
    ctx.strokeStyle = 'rgba(255,255,255,0.08)';
    ctx.lineWidth = 1;

    makeTicks(view.xMin, view.xMax, plotWidth()).forEach(x => {
      const px = X(x);
      ctx.beginPath(); ctx.moveTo(px, PAD); ctx.lineTo(px, canvas.height-PAD); ctx.stroke();
      ctx.fillStyle = '#9aa4d6';
      ctx.font = '12px system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial';
      ctx.textAlign = 'center';
      ctx.fillText(pct0(x), px, canvas.height - PAD + 16);
    });
    makeTicks(view.yMin, view.yMax, plotHeight()).forEach(y => {
      const py = Y(y);
      ctx.beginPath(); ctx.moveTo(PAD, py); ctx.lineTo(canvas.width-PAD, py); ctx.stroke();
      ctx.fillStyle = '#9aa4d6';
      ctx.font = '12px system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial';
      ctx.textAlign = 'left';
      ctx.fillText(pct0(y), 6, py+4);
    });

    // axes box
    ctx.strokeStyle = '#3b477a';
    ctx.strokeRect(PAD, PAD, canvas.width-2*PAD, canvas.height-2*PAD);

    // cloud
    ctx.fillStyle = 'rgba(139,176,255,0.25)';
    for (let i=0;i<F.cloud.vol.length;i++){
      const px = X(F.cloud.vol[i]), py = Y(F.cloud.ret[i]);
      ctx.beginPath(); ctx.arc(px, py, 1.3, 0, Math.PI*2); ctx.fill();
    }

    // frontier
    ctx.strokeStyle = '#5d82ff'; ctx.lineWidth = 2.5;
    ctx.beginPath();
    F.frontier.vol.forEach((vx,j)=>{
      const px = X(vx), py = Y(F.frontier.ret[j]);
      if (j===0) ctx.moveTo(px,py); else ctx.lineTo(px,py);
    });
    ctx.stroke();

    // CML from x=0 to right edge of the current (fixed) view
    if (F.points.max_sharpe && F.rf){
      const rf = F.rf.rate;
      const ms = F.points.max_sharpe;
      const slope = (ms.ret - rf) / Math.max(ms.vol,1e-9);
      const x0 = 0, x1 = view.xMax;
      const y0 = rf, y1 = rf + slope * x1;
      ctx.setLineDash([6,6]);
      ctx.strokeStyle = '#ff9d3b';
      ctx.beginPath(); ctx.moveTo(X(x0), Y(y0)); ctx.lineTo(X(x1), Y(y1)); ctx.stroke();
      ctx.setLineDash([]);
    }

    // labeled points
    function dot(p, color, label){
      ctx.fillStyle = color;
      const px = X(p.vol), py = Y(p.ret);
      ctx.beginPath(); ctx.arc(px,py,5,0,Math.PI*2); ctx.fill();
      ctx.fillStyle = '#cfe0ff';
      ctx.font = '12px system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial';
      ctx.fillText(label, px+8, py-6);
    }
    dot(F.points.min_var,   '#22c55e', 'Min-Var');
    dot(F.points.max_sharpe,'#f59e0b', 'Max-Sharpe');
    const sug = suggestedOverride || F.points.suggested;
    dot(sug, '#ef4444', 'Suggested');
  }

  // risk dial -> slide Suggested along frontier (no view changes)
  function nearestOnFrontier(targetVol){
    if (!F) return null;
    const arr = F.frontier.vol;
    let k = 0, best = Infinity;
    for (let i=0;i<arr.length;i++){ const d = Math.abs(arr[i]-targetVol); if (d<best){best=d;k=i;} }
    return { vol: F.frontier.vol[k], ret: F.frontier.ret[k] };
  }
  function updateSuggestedFromDial(){
    if (!F) return;
    const a = F.points.min_var.vol;
    const b = F.points.max_sharpe.vol;
    const t = (parseInt(dial.value,10) / 100);
    const targetVol = a + t * (b - a);
    suggestedOverride = nearestOnFrontier(targetVol);

    // update KPI cards
    $('volatility').textContent = (100*suggestedOverride.vol).toFixed(2)+'%';
    $('expRet').textContent     = (100*suggestedOverride.ret).toFixed(2)+'%';
    const rf = F?.rf?.rate ?? 0;
    const sh = (suggestedOverride.vol>0) ? ( (suggestedOverride.ret - rf) / suggestedOverride.vol ) : 0;
    $('sharpe').textContent = sh.toFixed(2);

    draw();
  }
  if (dial) dial.addEventListener('input', updateSuggestedFromDial);

  // fetch + render
  async function computeFrontier(){
    $('frontierError').style.display = 'none';
    try {
      const tickers = $('tickers').value.split(',').map(t=>t.trim().toUpperCase()).filter(Boolean);
      const risk_level = $('riskLevel').value;
      const investment_period = parseInt($('investmentPeriod').value, 10) || 3;

      const res = await fetch('/frontier', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ tickers, risk_level, investment_period })
      });
      if (!res.ok) throw new Error(await res.text() || 'Frontier request failed');

      F = await res.json();
      suggestedOverride = null;
      setInitialView(F);
      draw();

      // set dial position to suggested's place between min-var & max-sharpe
      const a = F.points.min_var.vol, b = F.points.max_sharpe.vol, s = F.points.suggested.vol;
      const t = Math.max(0, Math.min(1, (s - a) / (b - a || 1)));
      dial.value = Math.round(t*100);
    } catch (err) {
      console.error(err);
      $('frontierError').textContent = err.message || String(err);
      $('frontierError').style.display = 'block';
    }
  }
  // Double-click: reset view + KPIs back to the original Suggested point
canvas.addEventListener('dblclick', () => {
  if (!F || !dataBounds) return;

  // reset the viewport (still fixed, but this keeps behavior consistent)
  view = { ...dataBounds };

  // clear dial override and restore original Suggested KPIs
  suggestedOverride = null;

  // put dial back to Suggested position between Min-Var and Max Sharpe
  const a = F.points.min_var.vol;
  const b = F.points.max_sharpe.vol;
  const s = F.points.suggested.vol;
  const t = Math.max(0, Math.min(1, (s - a) / (b - a || 1)));
  dial.value = Math.round(t * 100);

  // restore KPI cards to Suggested
  $('volatility').textContent = (100 * F.points.suggested.vol).toFixed(2) + '%';
  $('expRet').textContent     = (100 * F.points.suggested.ret).toFixed(2) + '%';
  const rf = F?.rf?.rate ?? 0;
  const sh = (F.points.suggested.vol > 0)
    ? ((F.points.suggested.ret - rf) / F.points.suggested.vol)
    : 0;
  $('sharpe').textContent = sh.toFixed(2);

  draw();
});


  // hook so Optimize can refresh the frontier
  window.__refreshFrontier = computeFrontier;

  // make it obvious we don't support pan
  canvas.style.cursor = 'default';
})();


  // ---- metric popovers (unchanged) ----
  const METRIC_HELP = {
    "return": {
      title: "Expected Annual Return",
      body: "Average % gain per year from historical data. Higher can grow wealth faster but often with higher volatility.",
      note: "If two portfolios have similar risk, prefer the higher expected return."
    },
    "volatility": {
      title: "Portfolio Volatility (sigma)",
      body: "Annualized standard deviation of returns—how much the portfolio typically swings. Higher = wider ups/downs.",
      note: "If return is the same, lower sigma improves risk-adjusted performance."
    },
    "sharpe": {
      title: "Sharpe Ratio",
      body: "Return per unit of risk: (Return − Risk-free) / Volatility. Higher is better.",
      note: "Useful to compare portfolios with different risk levels."
    }
  };

  let openTip = null;
  function closeTip(){ if (openTip && openTip.parentNode) openTip.parentNode.removeChild(openTip); openTip = null; }
  function showTip(anchor, data) {
    closeTip();
    const tip = document.createElement('div');
    tip.className = 'tooltip';
    tip.innerHTML =
      '<div class="tt-title">' + data.title + '</div>' +
      '<div>' + data.body + '</div>' +
      '<div class="tt-note">' + (data.note || '') + '</div>';
    const r = anchor.getBoundingClientRect();
    tip.style.position = 'absolute';
    tip.style.top  = (r.bottom + window.scrollY + 8) + 'px';
    tip.style.left = (r.left   + window.scrollX - 6) + 'px';
    document.body.appendChild(tip);
    openTip = tip;
    function off(e) {
      if (e.type === 'keydown' && e.key !== 'Escape') return;
      if (e.type === 'click' && tip.contains(e.target)) return;
      window.removeEventListener('click', off, true);
      window.removeEventListener('keydown', off, true);
      closeTip();
    }
    window.addEventListener('click', off, true);
    window.addEventListener('keydown', off, true);
  }

  document.addEventListener('click', function (e) {
    const btn = e.target.closest ? e.target.closest('.info') : null;
    if (!btn) return;
    const key = btn.getAttribute('data-metric');
    const data = METRIC_HELP[key];
    if (data) showTip(btn, data);
  });
  document.addEventListener('keydown', function (e) {
    const btn = document.activeElement;
    if (!btn || !btn.classList || !btn.classList.contains('info')) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      const key = btn.getAttribute('data-metric');
      const data = METRIC_HELP[key];
      if (data) showTip(btn, data);
    }
  });
});
</script>


</body>
</html>
"""



# ----------------------------
# Helper functions
# ----------------------------

def get_date_range(investment_period: int) -> tuple[str, str]:
    """
    Given an investment period in years, returns (start_date, end_date) strings
    in YYYY-MM-DD format, using full calendar years ending last year.

    Example: today=2025-08-14, period=3
    -> start_date='2022-01-01', end_date='2024-12-31'
    """
    if investment_period < 1:
        raise ValueError("Investment period must be at least 1 year")

    current_year = date.today().year
    start_year = current_year - investment_period
    start_date = f"{start_year}-01-01"
    end_date = f"{current_year - 1}-12-31"
    return start_date, end_date

def annualize_returns(returns: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    """Annualize mean, volatility, and cov from daily returns."""
    mean = returns.mean() * 252
    volatility = returns.std() * np.sqrt(252)
    cov = returns.cov() * 252
    return mean, volatility, cov


def compute_weights(risk_level: str,
                    mean_returns: pd.Series,
                    volatility: pd.Series,
                    weight_cap: float | None = 0.6) -> pd.Series:
    """
    Heuristic weights for low/medium/high risk.
    - Returns a pd.Series indexed like mean_returns.
    - Optional weight_cap (e.g., 0.6) to avoid extreme concentration.
    """
    rl = (risk_level or "").lower().strip()
    idx = mean_returns.index
    n = len(idx)

    if rl == "low":
        # inverse volatility
        vol = volatility.reindex(idx).replace([0, np.inf, -np.inf], np.nan)
        inv_vol = 1.0 / vol
        inv_vol = inv_vol.fillna(0.0)
        w = inv_vol / inv_vol.sum() if inv_vol.sum() > 0 else pd.Series(1.0/n, index=idx)

    elif rl == "medium":
        # equal weight
        w = pd.Series(1.0/n, index=idx)

    elif rl == "high":
        mu = mean_returns.reindex(idx).astype(float).values
        sig = volatility.reindex(idx).astype(float).replace(0, np.nan).fillna(volatility.median()).values
        score = mu / (sig + 1e-8)        # risk-adjusted return (Sharpe proxy)
        # Softmax with temperature: lower = more aggressive tilt
        tau = 0.6
        z = (score - np.max(score)) / max(tau, 1e-6)
        ex = np.exp(z)
        soft = ex / ex.sum()
        floor_mass = 0.10
        w = pd.Series((1 - floor_mass) * soft, index=idx) + pd.Series(floor_mass / n, index=idx)
    else:
        raise ValueError("risk_level must be 'low', 'medium', or 'high'")

    # Optional cap to prevent a single-asset blowout
    if weight_cap is not None and 0 < weight_cap < 1:
        w = w.clip(lower=0.0, upper=weight_cap)
        s = w.sum()
        if s == 0:
            w[:] = 1.0/n
        else:
            w /= s

    return w

def get_risk_free_rate():
    # Get latest US 13-week Treasury bill yield (^IRX)
    t_bill = yf.download("^IRX", period="5d", interval="1d", auto_adjust=False)['Adj Close']  # last few days
    latest_rate = float(t_bill.dropna().iloc[-1]) / 100.0   # <- cast to float
    asof = t_bill.index[-1].date().isoformat()
    return latest_rate, asof

# ---------- Optimizer helpers (long-only; SLSQP) ----------

def _bounds(n, allow_shorts=False):
    return [(-1.0, 1.0) if allow_shorts else (0.0, 1.0) for _ in range(n)]

def _cons_fullinvest(n):
    return {"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}

def min_variance_for_return(mu, Sigma, target, allow_shorts=False):
    """
    Minimize variance s.t. sum w = 1, w>=0 (unless allow_shorts), and mu@w >= target
    """
    n = len(mu)
    w0 = np.ones(n) / n
    bounds = _bounds(n, allow_shorts)
    cons = [
        _cons_fullinvest(n),
        {"type": "ineq", "fun": lambda w, mu=mu, t=target: float(mu @ w - t)},
    ]
    def var_obj(w): return float(w @ Sigma @ w)
    res = minimize(var_obj, w0, method="SLSQP", bounds=bounds, constraints=cons, options={"maxiter": 1000})
    if not res.success:
        return None, (None, None)
    w = res.x
    r = float(mu @ w)
    v = float(np.sqrt(max(w @ Sigma @ w, 1e-16)))
    return w, (r, v)

def max_sharpe(mu, Sigma, rf=0.0, allow_shorts=False):
    n = len(mu)
    w0 = np.ones(n) / n
    bounds = _bounds(n, allow_shorts)
    cons = [_cons_fullinvest(n)]
    def neg_sharpe(w):
        r = float(mu @ w)
        v = float(np.sqrt(max(w @ Sigma @ w, 1e-16)))
        return - (r - rf) / v
    res = minimize(neg_sharpe, w0, method="SLSQP", bounds=bounds, constraints=cons, options={"maxiter": 1000})
    if not res.success:
        return None, (None, None, None)
    w = res.x
    r = float(mu @ w)
    v = float(np.sqrt(max(w @ Sigma @ w, 1e-16)))
    s = (r - rf) / v
    return w, (r, v, s)

def efficient_frontier(mu, Sigma, n_points=60, allow_shorts=False):
    """Exact frontier by sweeping feasible target returns and solving min-var."""
    t_min = float(max(mu.min(), 0.0))   # avoid negative target for long-only
    t_max = float(mu.max())
    targets = np.linspace(t_min, t_max, n_points)
    vols, rets = [], []
    for t in targets:
        w, (r, v) = min_variance_for_return(mu, Sigma, t, allow_shorts=allow_shorts)
        if w is None: 
            continue
        rets.append(r); vols.append(v)
    return np.array(vols), np.array(rets)

def mc_cloud(mu, Sigma, n_points=1500, allow_shorts=False, seed=123):
    random.seed(seed); np.random.seed(seed)
    n = len(mu)
    V, R = [], []
    for _ in range(n_points):
        z = np.random.rand(n)
        if allow_shorts:
            z = (z - 0.5) * 2.0
            w = z / np.sum(np.abs(z))
        else:
            w = z / z.sum()
        r = float(mu @ w)
        v = float(np.sqrt(max(w @ Sigma @ w, 1e-16)))
        V.append(v); R.append(r)
    return np.array(V), np.array(R)

def _metrics_for(w_series, mean_r, cov, rf):
    w = w_series.values
    mu = mean_r.loc[w_series.index].values
    Sigma = cov.loc[w_series.index, w_series.index].values
    r = float(mu @ w)
    v = float(np.sqrt(max(w @ Sigma @ w, 1e-16)))
    s = float((r - rf) / v) if v > 0 else float('nan')
    return {"expected_return": r, "portfolio_volatility": v, "sharpe_ratio": s}


# ----------------------------
# Routes
# ----------------------------
@app.get("/")
def index():
    return render_template_string(INDEX_HTML)


@app.post("/optimize")
def optimize():
    try:
        data = request.get_json(force=True)
        tickers = data.get('tickers') or []
        risk_level = data.get('risk_level', 'medium')
        investment_period = int(data.get('investment_period'))  # default to 3 years
        start_date, end_date = get_date_range(investment_period)
        amount = data.get('amount', None)
        if isinstance(amount, str) and amount.strip() == "":
            amount = None
        amount = float(amount) if amount is not None else None

        # Basic validation
        if not tickers or not isinstance(tickers, list):
            return ("Must provide atleast one ticker", 400)
        if len(tickers) != len(set(tickers)):
            tickers = list(dict.fromkeys(tickers))  # dedupe preserving order
        if not start_date or not end_date:
            return ("Provide start_date and end_date (YYYY-MM-DD)", 400)
        try:
            _ = datetime.strptime(start_date, "%Y-%m-%d")
            _ = datetime.strptime(end_date, "%Y-%m-%d")
        except Exception:
            return ("Invalid date format. Use YYYY-MM-DD", 400)

        # Fetch prices
        df = yf.download(tickers, start_date, end_date, auto_adjust=False, progress=False)
        if 'Adj Close' not in df or df['Adj Close'].dropna(how='all').empty:
            return ("No price data returned for the given inputs.", 400)
        prices = df['Adj Close'].dropna(how='all')
        # yfinance returns a Series for a single ticker; force 2D DataFrame
        if isinstance(prices, pd.Series):
            prices = prices.to_frame()
            # ensure column name matches the ticker the user entered
            if len(tickers) == 1:
                prices.columns = [tickers[0]]

        # Ensure all requested tickers present
        found = [t for t in tickers if t in prices.columns]
        missing = [t for t in tickers if t not in prices.columns]
        if not found:
            return ("None of the requested tickers returned Adj Close data.", 400)
        if missing:
            tickers = found  # drop missing silently but report back
        returns = prices[tickers].pct_change().dropna()
        if returns.empty:
            return ("Not enough data to compute returns.", 400)

        mean_r, volatility, cov = annualize_returns(returns)

        # ---- suggested (your rule-based heuristic)
        weights = compute_weights(risk_level, mean_r, volatility)
        weights = weights / weights.sum()

        # simple baselines
        ew = pd.Series(1.0/len(tickers), index=weights.index, name="EW")
        inv_vol = (1.0 / volatility.reindex(weights.index)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        inv_vol = (inv_vol / inv_vol.sum()).rename("InvVol")

        # exact Min-Var (long-only)
        mu = mean_r.loc[weights.index].values
        Sigma = cov.loc[weights.index, weights.index].values
        w_mv, (r_mv, v_mv) = min_variance_for_return(mu, Sigma, target=max(mu.min(), 0.0), allow_shorts=False)
        mv = pd.Series(w_mv, index=weights.index, name="MinVar") if w_mv is not None else None

        # Max-Sharpe (long-only)
        rf_dec, asof = get_risk_free_rate()
        w_ms, (r_ms, v_ms, s_ms) = max_sharpe(mu, Sigma, rf=rf_dec, allow_shorts=False)
        ms = pd.Series(w_ms, index=weights.index, name="MaxSharpe") if w_ms is not None else None

        # Optional dollar allocation for "Suggested"
        dollars = (weights * amount).round(2) if amount is not None else None

        # Old single-table (keep for existing UI; shows Suggested)
        table = []
        for t in weights.index:
            table.append({
                'Ticker': t,
                'Weight': float(weights[t]),
                'Expected_Return': float(mean_r[t]),
                'volatility': float(volatility[t]),
                'Dollars': float(dollars[t]) if dollars is not None else None
            })

        # Collect multiple strategy options
        strategies = []
        def add_strategy(name, w_ser, blurb):
          if w_ser is None:
              return
          m = _metrics_for(w_ser, mean_r, cov, rf_dec)
          strategies.append({
              "name": name,
              "blurb": blurb,
              "metrics": {
                  "expected_return": float(m["expected_return"]),
                  "portfolio_volatility": float(m["portfolio_volatility"]),
                  "sharpe_ratio": float(m["sharpe_ratio"]),
              },
              "weights": [{"Ticker": str(t), "Weight": float(w_ser[t])} for t in w_ser.index]  # <- no Series
          })


        add_strategy(f"Suggested Portfolio)", weights,
                     "Uses the risk-level you provided")
        add_strategy("Equal Weight", ew, "Simple 1/N baseline.")
        add_strategy("Inverse Volatility", inv_vol, "Lower-vol assets get higher weights (risk parity proxy).")
        add_strategy("Min-Variance", mv, "Lowest possible volatility portfolio (long-only).")
        add_strategy("Max Sharpe", ms, "Highest risk-adjusted return given the risk-free rate.")

        # Primary metrics block (for Suggested) + risk-free info in same shape your UI expects
        suggested_metrics = _metrics_for(weights, mean_r, cov, rf_dec)
        res = {
            "portfolio": table,
            "metrics": {
                "expected_return": float(suggested_metrics["expected_return"]),
                "portfolio_volatility": float(suggested_metrics["portfolio_volatility"]),
                "sharpe_ratio": float(suggested_metrics["sharpe_ratio"]),
                "risk_free_rate": float(rf_dec) * 100.0,
                "risk_free_rate_asof": asof,
            },
            "strategies": strategies,
            "note": {"dropped_missing_tickers": list(missing)},  # ensure list
        }
        return jsonify(res)

    except Exception as e:
        return (str(e), 500)

@app.post("/frontier")
def frontier():
    """
    Body: { tickers: [..], investment_period: int, risk_level: 'low'|'medium'|'high', target_vol?: float }
    Returns JSON with frontier arrays, cloud arrays (thinned), and points for min-var, max-sharpe, suggested.
    """
    try:
        data = request.get_json(force=True)
        tickers = data.get('tickers') or []
        investment_period = int(data.get('investment_period'))
        risk_level = data.get('risk_level', 'medium')
        target_vol = data.get('target_vol', None)
        target_vol = float(target_vol) if target_vol not in (None, "",) else None

        # reuse your date + price logic
        start_date, end_date = get_date_range(investment_period)
        df = yf.download(tickers, start_date, end_date, auto_adjust=False, progress=False)
        if 'Adj Close' not in df or df['Adj Close'].dropna(how='all').empty:
            return ("No price data returned for the given inputs.", 400)
        prices = df['Adj Close'].dropna(how='all')
        # yfinance returns a Series for a single ticker; force 2D DataFrame
        if isinstance(prices, pd.Series):
            prices = prices.to_frame()
            # ensure column name matches the ticker the user entered
            if len(tickers) == 1:
                prices.columns = [tickers[0]]
        found = [t for t in tickers if t in prices.columns]
        if not found:
            return ("None of the requested tickers returned Adj Close data.", 400)
        tickers = found
        returns = prices[tickers].pct_change().dropna()
        if returns.empty:
            return ("Not enough data to compute returns.", 400)

        mean_r, vol_s, cov = annualize_returns(returns)
        mu = mean_r.values
        Sigma = cov.values
        n = len(tickers)

        # heuristic (your suggestion)
        w_suggest = compute_weights(risk_level, mean_r, vol_s)
        w_suggest = w_suggest / w_suggest.sum()
        r_suggest = float(mu @ w_suggest.values)
        v_suggest = float(np.sqrt(max(w_suggest.values @ Sigma @ w_suggest.values, 1e-16)))

        # exact frontier
        ef_vol, ef_ret = efficient_frontier(mu, Sigma, n_points=60, allow_shorts=False)

        # min-var (at lowest feasible target)
        w_mv, (r_mv, v_mv) = min_variance_for_return(mu, Sigma, target=max(mu.min(), 0.0), allow_shorts=False)

        # max-sharpe
        rf_dec, rf_asof = get_risk_free_rate()    # decimal
        w_ms, (r_ms, v_ms, s_ms) = max_sharpe(mu, Sigma, rf=rf_dec, allow_shorts=False)

        # capital market line points (for plotting convenience)
        slope = (r_ms - rf_dec) / max(v_ms, 1e-16)
        x_cml = np.linspace(0.0, max(ef_vol.max(), v_ms) * 1.1, 25).tolist()
        y_cml = (rf_dec + slope * np.array(x_cml)).tolist()

        # monte-carlo cloud (thinned)
        cloud_vol, cloud_ret = mc_cloud(mu, Sigma, n_points=1200, allow_shorts=False)
        # thin to save payload
        idx = np.linspace(0, len(cloud_vol) - 1, 600, dtype=int)
        cloud_vol = cloud_vol[idx].tolist()
        cloud_ret = cloud_ret[idx].tolist()

        # optional: nearest EF point to a target volatility
        opt_at_target = None
        target_vol = float(target_vol) if target_vol not in (None, "",) else None
        if target_vol is not None and len(ef_vol) > 0:
            k = int(np.argmin(np.abs(ef_vol - target_vol)))
            opt_at_target = {"vol": float(ef_vol[k]), "ret": float(ef_ret[k])}

        return jsonify({
            "tickers": tickers,
            "rf": {"rate": float(rf_dec), "asof": rf_asof},
            "frontier": {"vol": ef_vol.tolist(), "ret": ef_ret.tolist()},
            "cloud": {"vol": cloud_vol, "ret": cloud_ret},
            "points": {
                "min_var": {"vol": float(v_mv), "ret": float(r_mv)},
                "max_sharpe": {"vol": float(v_ms), "ret": float(r_ms), "sharpe": float(s_ms)},
                "suggested": {"vol": float(v_suggest), "ret": float(r_suggest)}
            },
            "opt_at_target": opt_at_target
        })
    except Exception as e:
        return (str(e), 500)

if __name__ == '__main__':
    app.run(debug=True, host="127.0.0.1", port=5055)

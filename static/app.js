document.addEventListener('DOMContentLoaded', function () {
  // ---- tiny helpers ----
  function $(id){ return document.getElementById(id); }
  function pct(x){ return (100*x).toFixed(2) + '%'; }
  let currentPayload = null;
  const SERIES_LABELS = {
    Portfolio: 'Your suggested mix',
    SPY: 'Broad U.S. market',
    QQQ: 'Large technology-focused companies'
  };
  const STRATEGY_LABELS = {
    'Min-Variance': 'Steadiest mix',
    'Max Sharpe': 'Best risk/reward balance'
  };
  let activeMode = 'guided';

  function activateTab(tabId) {
    document.querySelectorAll('.view-tab').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === tabId);
    });
    document.querySelectorAll('.tab-panel').forEach(panel => {
      panel.classList.toggle('active', panel.id === tabId);
    });
  }

  document.querySelectorAll('.view-tab').forEach(btn => {
    btn.addEventListener('click', () => activateTab(btn.dataset.tab));
  });

  function setMode(mode) {
    activeMode = mode === 'custom' ? 'custom' : 'guided';
    $('guidedInputs').style.display = activeMode === 'guided' ? 'block' : 'none';
    $('customInputs').style.display = activeMode === 'custom' ? 'block' : 'none';
    document.querySelectorAll('.mode-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === activeMode);
    });
  }

  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => setMode(btn.dataset.mode));
  });

  function questionnaireAnswers() {
    return {
      goal: $('goal').value,
      horizon: $('horizon').value,
      risk_comfort: $('riskComfort').value,
      loss_tolerance: $('lossTolerance').value,
      liquidity: $('liquidity').value,
      emergency_fund: $('emergencyFund').value,
      contribution: $('contribution').value
    };
  }

  function requestPayloadFromForm() {
    const amount = parseFloat($('amount').value) || null;
    if (activeMode === 'guided') {
      return {
        mode: 'guided',
        questionnaire: questionnaireAnswers(),
        amount
      };
    }
    return {
      mode: 'custom',
      tickers: $('tickers').value.split(',').map(t => t.trim().toUpperCase()).filter(Boolean),
      risk_level: $('riskLevel').value,
      investment_period: parseInt($('investmentPeriod').value, 10) || 3,
      amount
    };
  }

  function setQuestionnaireAnswers(answers) {
    if (!answers) return;
    const map = {
      goal: 'goal',
      horizon: 'horizon',
      risk_comfort: 'riskComfort',
      loss_tolerance: 'lossTolerance',
      liquidity: 'liquidity',
      emergency_fund: 'emergencyFund',
      contribution: 'contribution'
    };
    Object.keys(map).forEach(key => {
      const el = $(map[key]);
      if (el && answers[key] != null) el.value = answers[key];
    });
  }

  // ---- strategy explanations (shown under the pill bar) ----
  const STRAT_EXPLAIN = {
  "Suggested": `
    This is the mix built for <strong>your comfort with risk</strong>.
    <ul style="margin-top:6px;">
      <li><strong>Lower risk:</strong> gives more weight to steadier holdings.</li>
      <li><strong>Moderate risk:</strong> spreads money evenly for a simple balanced mix.</li>
      <li><strong>Higher risk:</strong> gives more weight to holdings that historically offered more growth for their risk.</li>
    </ul>
    This is a starting point for learning, not a guarantee of future results.
  `,

  "Min-Variance": `
    This is the <strong>steadiest mix</strong> found from your choices. It tries to reduce ups and downs as much as possible.
  `,

  "Max Sharpe": `
    This mix tries to get the <strong>most return for the risk taken</strong>. It can still go down, but it looks for a better balance between growth and movement.
  `
};

  // ---- render KPIs + table for a chosen strategy ----
  function renderAllocationFromStrategy(strategy, assetStats) {
    // KPIs
    $('expRet').textContent = pct(strategy.metrics.expected_return);
    $('volatility').textContent = pct(strategy.metrics.portfolio_volatility);
    $('sharpe').textContent = (strategy.metrics.sharpe_ratio).toFixed(2);

    // Table rows (using per-asset ER/Vol we built from server data)
    const header = ['Symbol','Role','Share of mix','Estimated yearly growth','Typical yearly movement','Dollars'];
    const rows = [header];
    strategy.weights.forEach(w => {
      const t = w.Ticker;
      const s = assetStats[t] || { er: NaN, vol: NaN, dollars: null, role: '' };
      rows.push([
        t,
        s.role,
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

  function strategyDisplayName(name) {
    if (/^Suggested/.test(name)) return 'Suggested mix';
    return STRATEGY_LABELS[name] || name;
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

      const short = strategyDisplayName(s.name);
      pill.innerHTML =
        `${short}<span class="metric"> - Growth ${(s.metrics.expected_return*100).toFixed(1)}% - Movement ${(s.metrics.portfolio_volatility*100).toFixed(1)}%</span>`;
      bar.appendChild(pill);
    });

    function setActive(i){
      [...bar.querySelectorAll('.pill')].forEach((el, k) => {
        el.classList.toggle('active', k === i);
      });

      // render chosen strategy
      const strat = strategies[i];
      renderAllocationFromStrategy(strat, assetStats);

      // explanation
      const base = STRAT_EXPLAIN[strat.name]
                || STRAT_EXPLAIN[strat.name.split(' ')[0]]
                || '';
      info.innerHTML = `<strong>${strategyDisplayName(strat.name)}</strong> - ${strat.blurb}<br>${base}`;
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

  function renderBacktest(backtest) {
    const table = $('backtestTable');
    if (!table) return;
    const summary = backtest && backtest.summary ? backtest.summary : {};
    const names = Object.keys(summary);
    if (!names.length) {
      table.innerHTML = '<tr><td>No comparison data available.</td></tr>';
      return;
    }

    let html = '<tr><th>Investment</th><th>$1 became</th><th>Total growth</th><th>Worst drop</th></tr>';
    names.forEach(name => {
      const item = summary[name];
      const label = item.label || SERIES_LABELS[name] || name;
      html += '<tr>' +
        `<td>${label}</td>` +
        `<td>$${item.ending_value.toFixed(2)}</td>` +
        `<td>${pct(item.total_return)}</td>` +
        `<td>${pct(item.max_drawdown)}</td>` +
        '</tr>';
    });
    table.innerHTML = html;
  }

  function formatRiskDriver(driver) {
    if (driver.value == null || Number.isNaN(driver.value)) return 'Not available';
    if (driver.label === 'Market sensitivity') return driver.value.toFixed(2) + 'x';
    if (driver.label === 'Market similarity') return driver.value.toFixed(2);
    return pct(driver.value);
  }

  function renderRiskProfile(profile) {
    const el = $('riskProfile');
    if (!el) return;
    if (!profile) {
      el.innerHTML = '<div class="hint">Risk information is not available for this run.</div>';
      return;
    }
    const drivers = (profile.drivers || []).map(driver => (
      '<div class="risk-driver">' +
        `<strong>${driver.label}</strong>` +
        `<span>${formatRiskDriver(driver)}</span>` +
        `<small>${driver.plain_language}</small>` +
      '</div>'
    )).join('');
    el.innerHTML =
      '<div class="risk-summary">' +
        `<div class="risk-badge">${profile.label} risk</div>` +
        `<div>${profile.explanation}</div>` +
      '</div>' +
      `<div class="risk-grid">${drivers}</div>` +
      `<div class="hint">${profile.threshold_note || ''}</div>`;
  }

  function renderStabilizerSummary(data) {
    const el = $('stabilizerSummary');
    if (!el) return;
    const stabilizers = data.stabilizers;
    if (!stabilizers) {
      el.classList.remove('active');
      el.innerHTML = '';
      return;
    }
    const added = stabilizers.added || [];
    const addedText = added.length
      ? added.map(item => `${item.ticker} (${item.label})`).join(', ')
      : 'none';
    el.classList.add('active');
    el.innerHTML =
      `<strong>Stabilizers added:</strong> ${addedText}<br>` +
      `<span>${stabilizers.message}</span>`;
  }

  function renderQuestionnaireSummary(data) {
    const el = $('questionnaireSummary');
    if (!el) return;
    const guidance = data.questionnaire;
    if (!guidance) {
      el.classList.remove('active');
      el.innerHTML = '';
      return;
    }
    const labels = guidance.labels || {};
    const reasons = (guidance.reasons || []).map(reason => `<li>${reason}</li>`).join('');
    const tickers = (guidance.tickers || []).join(', ');
    el.classList.add('active');
    el.innerHTML =
      '<strong>Guided profile used for this run</strong>' +
      `<div class="profile-line">Goal: ${labels.goal || ''} | Horizon: ${labels.horizon || ''} | Risk comfort: ${labels.risk_comfort || ''}</div>` +
      `<div class="profile-line">Starting basket: ${tickers}. Risk setting: ${guidance.risk_level}.</div>` +
      `<div class="hint">${guidance.explanation || ''}</div>` +
      (reasons ? `<ul>${reasons}</ul>` : '') +
      `<div class="hint">${guidance.note || ''}</div>`;
  }

  function renderOptimization(data) {
    currentPayload = data;
    $('emptyState').style.display = 'none';
    $('workspaceTitle').textContent = 'Your guided portfolio';
    $('workspaceSubtitle').textContent = 'Review the main risk signals first, then switch views for holdings, history, and tradeoffs.';

    const rfPct  = data.metrics.risk_free_rate;
    const rfAsOf = data.metrics.risk_free_rate_asof;
    $('rfNote').innerHTML =
      '<strong>3-month U.S. Treasury:</strong> ' + rfPct.toFixed(2) + '%<br>' +
      '<span style="font-size: 11px; color: var(--muted);">As of ' + rfAsOf + '</span>';

    const assetStats = {};
    (data.portfolio || []).forEach(r => {
      assetStats[r.Ticker] = {
        er: r.Expected_Return,
        vol: r.volatility,
        dollars: (typeof r.Dollars === 'number') ? r.Dollars : null,
        role: r.Role || '',
        description: r.Description || ''
      };
    });

    const strategies = (data.strategies || []).filter(s =>
      /^Suggested/.test(s.name) || s.name === 'Min-Variance' || s.name === 'Max Sharpe'
    );
    buildStrategyBar(strategies, assetStats);
    renderRiskProfile(data.risk_profile);
    renderBacktest(data.backtest);
    renderStabilizerSummary(data);
    renderQuestionnaireSummary(data);

    const interpretation = data.metrics && data.metrics.sharpe_interpretation;
    $('sharpeText').textContent = interpretation ? interpretation.label : '';
    if (interpretation && interpretation.message) {
      $('sharpeText').title = interpretation.message;
    }

    if (data.inputs) {
      $('tickers').value = (data.inputs.requested_tickers || data.inputs.tickers || []).join(', ');
      $('riskLevel').value = data.inputs.risk_level || 'medium';
      $('investmentPeriod').value = data.inputs.investment_period || 3;
      $('amount').value = data.inputs.amount || '';
      setMode(data.inputs.mode === 'guided' ? 'guided' : 'custom');
    }
    if (data.questionnaire) {
      setQuestionnaireAnswers(data.questionnaire.answers);
    }

    $('savePortfolio').disabled = false;
    $('results').style.display = 'block';
    activateTab('overviewPanel');
  }

  async function refreshSavedPortfolios() {
    const select = $('savedPortfolios');
    if (!select) return;
    const res = await fetch('/portfolios');
    if (!res.ok) return;
    const data = await res.json();
    const options = ['<option value="">Saved scenarios</option>'];
    (data.portfolios || []).forEach(item => {
      const tickers = (item.tickers || []).join(', ');
      options.push(`<option value="${item.id}">${item.name} - ${tickers}</option>`);
    });
    select.innerHTML = options.join('');
  }

  // =================== OPTIMIZE ===================
  const goBtn = $('go');
  if (!goBtn) { console.error('No #go button'); return; }
  refreshSavedPortfolios();

  goBtn.addEventListener('click', async function () {
    $('error').style.display   = 'none';
    $('results').style.display = 'none';
    goBtn.disabled = true;

    try {
      const payload = requestPayloadFromForm();

      const res = await fetch('/optimize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error((await res.text()) || 'Request failed');

      const data = await res.json();
      renderOptimization(data);
    } catch (err) {
      console.error(err);
      $('error').textContent = err && err.message ? err.message : String(err);
      $('error').style.display = 'block';
    } finally {
      goBtn.disabled = false;
    }
    
    if (window.__refreshFrontier) { window.__refreshFrontier(); }

  });

  $('savePortfolio').addEventListener('click', async function () {
    if (!currentPayload) return;
    $('error').style.display = 'none';
    try {
      const res = await fetch('/portfolios', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: $('saveName').value, payload: currentPayload })
      });
      if (!res.ok) throw new Error((await res.text()) || 'Save failed');
      await refreshSavedPortfolios();
      $('saveName').value = '';
    } catch (err) {
      $('error').textContent = err && err.message ? err.message : String(err);
      $('error').style.display = 'block';
    }
  });

  $('loadPortfolio').addEventListener('click', async function () {
    const id = $('savedPortfolios').value;
    if (!id) return;
    $('error').style.display = 'none';
    try {
      const res = await fetch('/portfolios/' + encodeURIComponent(id));
      if (!res.ok) throw new Error((await res.text()) || 'Load failed');
      const data = await res.json();
      renderOptimization(data);
      if (window.__refreshFrontier) { window.__refreshFrontier(); }
    } catch (err) {
      $('error').textContent = err && err.message ? err.message : String(err);
      $('error').style.display = 'block';
    }
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
    ctx.strokeStyle = 'rgba(32,36,31,0.10)';
    ctx.lineWidth = 1;

    makeTicks(view.xMin, view.xMax, plotWidth()).forEach(x => {
      const px = X(x);
      ctx.beginPath(); ctx.moveTo(px, PAD); ctx.lineTo(px, canvas.height-PAD); ctx.stroke();
      ctx.fillStyle = '#6e756b';
      ctx.font = '12px system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial';
      ctx.textAlign = 'center';
      ctx.fillText(pct0(x), px, canvas.height - PAD + 16);
    });
    makeTicks(view.yMin, view.yMax, plotHeight()).forEach(y => {
      const py = Y(y);
      ctx.beginPath(); ctx.moveTo(PAD, py); ctx.lineTo(canvas.width-PAD, py); ctx.stroke();
      ctx.fillStyle = '#6e756b';
      ctx.font = '12px system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial';
      ctx.textAlign = 'left';
      ctx.fillText(pct0(y), 6, py+4);
    });

    // axes box
    ctx.strokeStyle = '#d8d1c3';
    ctx.strokeRect(PAD, PAD, canvas.width-2*PAD, canvas.height-2*PAD);

    // cloud
    ctx.fillStyle = 'rgba(47,111,94,0.22)';
    for (let i=0;i<F.cloud.vol.length;i++){
      const px = X(F.cloud.vol[i]), py = Y(F.cloud.ret[i]);
      ctx.beginPath(); ctx.arc(px, py, 1.3, 0, Math.PI*2); ctx.fill();
    }

    // frontier
    ctx.strokeStyle = '#2f6f5e'; ctx.lineWidth = 2.5;
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
      ctx.strokeStyle = '#c7953d';
      ctx.beginPath(); ctx.moveTo(X(x0), Y(y0)); ctx.lineTo(X(x1), Y(y1)); ctx.stroke();
      ctx.setLineDash([]);
    }

    // labeled points
    function dot(p, color, label){
      ctx.fillStyle = color;
      const px = X(p.vol), py = Y(p.ret);
      ctx.beginPath(); ctx.arc(px,py,5,0,Math.PI*2); ctx.fill();
      ctx.fillStyle = '#20241f';
      ctx.font = '12px system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial';
      ctx.fillText(label, px+8, py-6);
    }
    dot(F.points.min_var,   '#2f6f5e', 'Steadiest');
    dot(F.points.max_sharpe,'#c7953d', 'Best balance');
    const sug = suggestedOverride || F.points.suggested;
    dot(sug, '#b85c38', 'Suggested');
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
      const inputs = currentPayload && currentPayload.inputs ? currentPayload.inputs : null;
      const tickers = inputs
        ? (inputs.requested_tickers || inputs.tickers || [])
        : $('tickers').value.split(',').map(t=>t.trim().toUpperCase()).filter(Boolean);
      const risk_level = inputs ? inputs.risk_level : $('riskLevel').value;
      const investment_period = inputs ? inputs.investment_period : (parseInt($('investmentPeriod').value, 10) || 3);

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
      title: "Estimated Yearly Growth",
      body: "The average yearly growth suggested by the selected historical data.",
      note: "This is based on the past. It is not a prediction or guarantee."
    },
    "volatility": {
      title: "Typical Yearly Movement",
      body: "How much the portfolio usually moved up and down in a year.",
      note: "A higher number means a bumpier ride."
    },
    "sharpe": {
      title: "Return for Risk Taken",
      body: "A score that compares growth with how bumpy the ride was.",
      note: "Higher is generally better, but it still uses historical data."
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

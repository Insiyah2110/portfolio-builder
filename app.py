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
import matplotlib.pyplot as plt
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

      <button id="go" class="btn">Optimize</button>
      <div id="error" class="err" style="display:none; margin-top:12px;"></div>

      <div class="results" id="results" style="display:none;">
        <div class="kpi">
          <div class="box"><div>Expected Annual Return</div><div id="expRet" style="font-size:20px; font-weight:800;"></div></div>
          <div class="box"><div>Portfolio Volatility</div><div id="volatility" style="font-size:20px; font-weight:800;"></div></div>
          <div class="box"><div>Sharpe Ratio</div><div id="sharpe" style="font-size:20px; font-weight:800;"></div></div>
          <div class="box"><div>Risk-free Rate</div><div id="rfNote" style="font-size:20px; font-weight:800;"></div></div>
        </div>

        <h3 style="margin-top:20px;">Allocation</h3>
        <table id="table"></table>

        <h3 style="margin-top:28px;">Efficient Frontier (Optional)</h3>
        <div class="row-3">
          <div>
            <label>Target volatility (optional)</label>
            <input id="targetVol" type="number" step="0.01" placeholder="e.g., 0.15 for 15%" />
            <div class="hint">Leave empty to show Max Sharpe from sampled portfolios.</div>
          </div>
          <div>
            <label>&nbsp;</label>
            <button id="frontierBtn" class="btn" type="button">Compute Efficient Frontier</button>
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
const $ = (id) => document.getElementById(id);

// ---------- Optimize (existing flow) ----------
$('go').addEventListener('click', async () => {
  $('error').style.display = 'none';
  $('results').style.display = 'none';
  $('go').disabled = true;
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

    if (!res.ok) {
      const msg = await res.text();
      throw new Error(msg || 'Request failed');
    }

    const data = await res.json();
    $('expRet').textContent = (100*data.metrics.expected_return).toFixed(2) + '%';
    $('volatility').textContent = (100*data.metrics.portfolio_volatility).toFixed(2) + '%';
    $('sharpe').textContent = data.metrics.sharpe_ratio.toFixed(2);
    const rfPct  = data.metrics.risk_free_rate;
    const rfAsOf = data.metrics.risk_free_rate_asof;
    $('rfNote').innerHTML = `
      <strong>13W T-bill:</strong> ${rfPct.toFixed(2)}%<br>
      <span style="font-size: 11px; color: var(--muted);">As of ${rfAsOf}</span>
    `;

    const rows = [
      ['Ticker','Weight','Expected Return','Volatility','Dollars (optional)'],
      ...data.portfolio.map(r => [
        r.Ticker,
        (100*r.Weight).toFixed(2)+'%',
        (100*r.Expected_Return).toFixed(2)+'%',
        (100*r.volatility).toFixed(2)+'%',
        r.Dollars !== null ? ('$' + r.Dollars.toLocaleString()) : ''
      ])
    ];

    const table = $('table');
    table.innerHTML = rows.map((row,i)=>`<tr>${row.map(c=>`<${i===0?'th':'td'}>${c}</${i===0?'th':'td'}>`).join('')}</tr>`).join('');

    $('results').style.display = 'block';
  } catch (err) {
    $('error').textContent = err.message;
    $('error').style.display = 'block';
  } finally {
    $('go').disabled = false;
  }
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
    latest_rate = t_bill.dropna().iloc[-1] / 100  # convert from % to decimal
    asof = t_bill.index[-1].date().isoformat()
    return latest_rate, asof


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
        weights = compute_weights(risk_level, mean_r, volatility)
        weights = weights / weights.sum()  # normalize

        exp_ret = float(np.dot(weights.values, mean_r.loc[weights.index].values))
        port_volatility = float(np.sqrt(np.dot(weights.values.T, np.dot(cov.loc[weights.index, weights.index].values, weights.values))))
        risk_free_rate, asof = get_risk_free_rate()
        sharpe = float((exp_ret - risk_free_rate) / port_volatility) if port_volatility > 0 else float('nan')

        # Optional dollar allocation
        dollars = None
        if amount is not None:
            dollars = (weights * amount).round(2)

        # Build response
        table = []
        for t in weights.index:
            row = {
                'Ticker': t,
                'Weight': float(weights[t]),
                'Expected_Return': float(mean_r[t]),
                'volatility': float(volatility[t]),
                'Dollars': float(dollars[t]) if dollars is not None else None
            }
            table.append(row)

        res = {
            'portfolio': table,
            'metrics': {
                'expected_return': exp_ret,
                'portfolio_volatility': port_volatility,
                'sharpe_ratio': sharpe,
                'risk_free_rate': float(risk_free_rate) * 100,
                'risk_free_rate_asof': asof
            },
            'note': {
                'dropped_missing_tickers': missing
            }
        }
        return jsonify(res)

    except Exception as e:
        return (str(e), 500)

if __name__ == '__main__':
    app.run(debug=True)

# Python script to optimize portfolio

import yfinance as yf
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

"""
Some common tickers:
Apple - AAPL
Microsoft - MSFT
Pfizer - PFE
Coca Cola - KO
Nvidia - NVDA
Amazon - AMZN
Lululemon - LULU
Intel - INTC
"""
# Step 1: get user's stock list, risk level, investment period
# tickers = input("Enter comma-separated stock tickers: ").upper().split(',')
# risk_level = input("Enter risk level (low, medium, high): ").lower()
# investment_period = int(input("Enter investment period in years (e.g. 1,3,5): "))

# # Determine historical data fram based on investment period
# start_year = 2024 - investment_period
# start_date = f"{start_year}-01-01"
# end_date = "2024-12-31"

tickers = ["AMZN", "PFE", "KO", "MSFT"]
risk_level = "low"
start_date = "2015-01-01"
end_date = "2024-12-31"

# Download data and find daily returns
prices_raw = yf.download(tickers, start_date, end_date, auto_adjust=False)
prices_adj = prices_raw['Adj Close']
daily_returns = prices_adj.pct_change().dropna()

mean_daily = daily_returns.mean().values
cov_daily = daily_returns.cov().values

trading_days = 252
mean_returns = mean_daily * trading_days             # annualized expected returns (μ)
cov_matrix   = cov_daily * trading_days              # annualized covariance (Σ)
volatility = daily_returns.std() * np.sqrt(252)
correlation = daily_returns.corr()

# Get latest US 13-week Treasury bill yield (^IRX)
t_bill = yf.download("^IRX", period="5d", interval="1d", auto_adjust=False)['Adj Close']  # last few days
latest_rate = t_bill.dropna().iloc[-1] / 100  # convert from % to decimal


# ---- Build weights by risk_level ----
if risk_level == "low":
    inv_vol = 1.0 / np.where(volatility > 0, volatility, np.nan)
    inv_vol = np.nan_to_num(inv_vol, nan=0.0)
    weights = inv_vol / inv_vol.sum()
elif risk_level == "medium":
    weights = np.repeat(1.0 / len(tickers), len(tickers))
elif risk_level == "high":
    # Tilt to higher expected returns (long-only, normalized)
    pos = np.clip(mean_returns, 0, None)
    if pos.sum() == 0:
        weights = np.repeat(1.0 / len(tickers), len(tickers))
    else:
        weights = pos / pos.sum()
else:
    raise ValueError("risk_level must be 'low', 'medium', or 'high'")

# Normalize weights
weights = weights / weights.sum()

# Step 4: Portfolio metrics
expected_return = np.dot(weights, mean_returns)
portfolio_volatility = np.sqrt(np.dot(weights.T, np.dot(daily_returns.cov() * 252, weights)))
sharpe_ratio = (expected_return - float(latest_rate)) / portfolio_volatility 

# ---- Efficient Frontier (Monte Carlo, long-only) ----
def simulate_efficient_frontier(mean_returns, cov_matrix, n_portfolios=50000, rf=float(latest_rate), seed=42):
    rng = np.random.default_rng(seed)
    n = len(mean_returns)
    rets, vols, sharpes, W = [], [], [], []
    for _ in range(n_portfolios):
        w = rng.random(n); w /= w.sum()
        r = float(np.dot(w, mean_returns))
        v = float(np.sqrt(np.dot(w, np.dot(cov_matrix, w))))
        s = (r - rf) / v if v > 0 else np.nan
        rets.append(r); vols.append(v); sharpes.append(s); W.append(w)
    return np.array(rets), np.array(vols), np.array(sharpes), np.array(W)

def plot_efficient_frontier(
    vols, rets, sharpes,
    rf,
    your_vol=None, your_ret=None,
    save_path="efficient_frontier.png"
):
    idx = np.nanargmax(sharpes)
    tang_ret, tang_vol = float(rets[idx]), float(vols[idx])
    sharpe_max = float(sharpes[idx])

    plt.figure(figsize=(8, 6))
    plt.scatter(vols, rets, s=5, alpha=0.3, label="Random portfolios")

    # Max-Sharpe (tangent) portfolio
    plt.scatter(tang_vol, tang_ret, s=120, edgecolors="k", linewidths=1.5,
                marker="o", label="Max Sharpe")

    # Your current portfolio
    if your_vol is not None and your_ret is not None:
        plt.scatter(your_vol, your_ret, s=160, edgecolors="k", linewidths=1.5,
                    marker="X", label="Your portfolio")

    # --- Capital Market Line (from rf to tangent point) ---
    x_max = max(np.max(vols), tang_vol, your_vol if your_vol is not None else 0.0)
    cml_x = np.array([0.0, x_max])
    cml_y = rf + sharpe_max * cml_x
    plt.plot(cml_x, cml_y, linewidth=2.0, label="Capital Market Line")

    # Mark rf on the y-axis
    plt.scatter(float(latest_rate), rf, s=60, marker="_", linewidths=2.0, label="Risk-free rate")

    plt.xlabel("Volatility (σ)")
    plt.ylabel("Expected Return (μ)")
    plt.title("Efficient Frontier (Monte Carlo, long-only)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(save_path, dpi=160)
    plt.close()
    return idx

rets, vols, sharpes, W = simulate_efficient_frontier(
    mean_returns, cov_matrix, n_portfolios=50000, rf=float(latest_rate)
)

best_idx = plot_efficient_frontier(
    vols, rets, sharpes,
    rf=float(latest_rate),
    your_vol=float(portfolio_volatility),
    your_ret=float(expected_return),
    save_path="efficient_frontier.png"
)


# Step 5: Output results
portfolio = pd.DataFrame({
    'Ticker': tickers,
    'Weight': weights,
    'Expected Return': mean_returns,
    'Volatility': volatility
})

print("\n--- Portfolio Summary ---")
print(f"Current risk-free rate is: {float(latest_rate):.3%}")
print(portfolio)
print(f"\nExpected Annual Return: {expected_return:.2%}")
print(f"Portfolio Volatility: {portfolio_volatility:.2%}")
print(f"Sharpe Ratio: {sharpe_ratio:.2f}")
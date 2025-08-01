# Python script to optimize portfolio

import yfinance as yf
import numpy as np
import pandas as pd

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

tickers = ["AAPL", "AMZN", "PFE"]
risk_level = "high"
start_date = "2015-01-01"
end_date = "2024-12-31"

# Download data and find daily returns
prices_raw = yf.download(tickers, start_date, end_date, auto_adjust=False)
prices_adj = prices_raw['Adj Close']
daily_returns = prices_adj.pct_change().dropna()

# print(daily_returns)

# Find daily mean, volatility, correlation
mean_returns = daily_returns.mean() * 252
volatility = daily_returns.std() * np.sqrt(252)
correlation = daily_returns.corr()

# Assign weights based on risk level

if risk_level == "low":
    # Inverse volatility weighting
    inv_vol = 1 / volatility
    weights = inv_vol / inv_vol.sum()
elif risk_level == "medium":
    weights = np.repeat(1/len(tickers), len(tickers))
elif risk_level == "high":
    # Tilt toward higher expected return
    weights = mean_returns / mean_returns.sum()
else:
    raise ValueError("Invalid risk level")

# Normalize weights
weights = weights / weights.sum()

# Step 4: Portfolio metrics
expected_return = np.dot(weights, mean_returns)
portfolio_volatility = np.sqrt(np.dot(weights.T, np.dot(daily_returns.cov() * 252, weights)))
sharpe_ratio = (expected_return - 0.03) / portfolio_volatility  # assuming 3% risk-free rate

# Step 5: Output results
portfolio = pd.DataFrame({
    'Ticker': tickers,
    'Weight': weights,
    'Expected Return': mean_returns,
    'Volatility': volatility
})

print("\n--- Portfolio Summary ---")
print(portfolio)
print(f"\nExpected Annual Return: {expected_return:.2%}")
print(f"Portfolio Volatility: {portfolio_volatility:.2%}")
print(f"Sharpe Ratio: {sharpe_ratio:.2f}")
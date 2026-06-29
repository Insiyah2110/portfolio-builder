from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import random

import numpy as np
import pandas as pd
from scipy.optimize import minimize
import yfinance as yf


TRADING_DAYS = 252
BENCHMARK_LABELS = {
    "SPY": "Broad U.S. market",
    "QQQ": "Large technology-focused companies",
}
STABILIZER_ASSETS = {
    "SGOV": "Short-term U.S. Treasury fund",
    "BND": "Broad U.S. bond fund",
}
STABILIZER_MIX = {
    "low": {"user": 0.50, "stabilizers": {"SGOV": 0.30, "BND": 0.20}},
    "medium": {"user": 0.75, "stabilizers": {"SGOV": 0.10, "BND": 0.15}},
    "high": {"user": 0.95, "stabilizers": {"SGOV": 0.05}},
}


@dataclass(frozen=True)
class MarketData:
    tickers: list[str]
    prices: pd.DataFrame
    returns: pd.DataFrame
    mean_returns: pd.Series
    volatility: pd.Series
    covariance: pd.DataFrame
    start_date: str
    end_date: str
    missing: list[str]


def get_date_range(investment_period: int) -> tuple[str, str]:
    if investment_period < 1:
        raise ValueError("Investment period must be at least 1 year")

    current_year = date.today().year
    start_year = current_year - investment_period
    return f"{start_year}-01-01", f"{current_year - 1}-12-31"


def annualize_returns(returns: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    mean = returns.mean() * TRADING_DAYS
    volatility = returns.std() * np.sqrt(TRADING_DAYS)
    cov = returns.cov() * TRADING_DAYS
    return mean, volatility, cov


def fetch_market_data(tickers: list[str], investment_period: int) -> MarketData:
    if not tickers or not isinstance(tickers, list):
        raise ValueError("Must provide at least one ticker")

    tickers = [str(t).strip().upper() for t in tickers if str(t).strip()]
    tickers = list(dict.fromkeys(tickers))
    if not tickers:
        raise ValueError("Must provide at least one ticker")

    start_date, end_date = get_date_range(int(investment_period))
    df = yf.download(tickers, start_date, end_date, auto_adjust=False, progress=False)
    if "Adj Close" not in df or df["Adj Close"].dropna(how="all").empty:
        raise ValueError("No price data returned for the given inputs.")

    prices = df["Adj Close"].dropna(how="all")
    if isinstance(prices, pd.Series):
        prices = prices.to_frame()
        if len(tickers) == 1:
            prices.columns = [tickers[0]]

    found = [t for t in tickers if t in prices.columns]
    missing = [t for t in tickers if t not in prices.columns]
    if not found:
        raise ValueError("None of the requested tickers returned Adj Close data.")

    prices = prices[found]
    returns = prices.pct_change().dropna()
    if returns.empty:
        raise ValueError("Not enough data to compute returns.")

    mean_returns, volatility, covariance = annualize_returns(returns)
    return MarketData(
        tickers=found,
        prices=prices,
        returns=returns,
        mean_returns=mean_returns,
        volatility=volatility,
        covariance=covariance,
        start_date=start_date,
        end_date=end_date,
        missing=missing,
    )


def requested_tickers(tickers: list[str]) -> list[str]:
    cleaned = [str(t).strip().upper() for t in tickers if str(t).strip()]
    return list(dict.fromkeys(cleaned))


def stabilizer_policy(risk_level: str) -> dict:
    return STABILIZER_MIX.get((risk_level or "medium").lower().strip(), STABILIZER_MIX["medium"])


def expand_with_stabilizers(tickers: list[str], risk_level: str) -> tuple[list[str], dict]:
    user_tickers = requested_tickers(tickers)
    policy = stabilizer_policy(risk_level)
    stabilizers = list(policy["stabilizers"].keys())
    combined = list(dict.fromkeys(user_tickers + stabilizers))
    added = [ticker for ticker in stabilizers if ticker not in user_tickers]
    return combined, {
        "user_tickers": user_tickers,
        "added": [{"ticker": ticker, "label": STABILIZER_ASSETS[ticker]} for ticker in added],
        "target_user_share": float(policy["user"]),
        "target_stabilizer_share": float(sum(policy["stabilizers"].values())),
        "message": stabilizer_message(risk_level, added),
    }


def stabilizer_message(risk_level: str, added: list[str]) -> str:
    if not added:
        return "No additional stabilizers were added because they were already in your list."
    rl = (risk_level or "medium").lower().strip()
    if rl == "low":
        return "For a lower-risk mix, the tool adds Treasury and bond funds to reduce dependence on stocks alone."
    if rl == "high":
        return "For a higher-risk mix, the tool keeps most of the portfolio in your choices and adds a small stabilizer."
    return "For a moderate-risk mix, the tool adds some Treasury and bond exposure for balance."


def blend_with_stabilizers(raw_weights: pd.Series, user_tickers: list[str], risk_level: str) -> pd.Series:
    policy = stabilizer_policy(risk_level)
    stabilizer_targets = pd.Series(policy["stabilizers"], dtype=float)
    user_available = [ticker for ticker in user_tickers if ticker in raw_weights.index]
    stabilizer_available = [ticker for ticker in stabilizer_targets.index if ticker in raw_weights.index]

    result = pd.Series(0.0, index=raw_weights.index)

    if user_available:
        user_raw = raw_weights.loc[user_available]
        user_raw = user_raw / user_raw.sum() if user_raw.sum() > 0 else pd.Series(1.0 / len(user_available), index=user_available)
        result.loc[user_available] = user_raw * policy["user"]

    if stabilizer_available:
        st_raw = stabilizer_targets.loc[stabilizer_available]
        st_raw = st_raw / st_raw.sum()
        result.loc[stabilizer_available] += st_raw * sum(policy["stabilizers"].values())

    if result.sum() == 0:
        result = pd.Series(1.0 / len(raw_weights), index=raw_weights.index)
    else:
        result = result / result.sum()
    return result


def compute_weights(
    risk_level: str,
    mean_returns: pd.Series,
    volatility: pd.Series,
    weight_cap: float | None = 0.6,
) -> pd.Series:
    rl = (risk_level or "").lower().strip()
    idx = mean_returns.index
    n = len(idx)

    if rl == "low":
        vol = volatility.reindex(idx).replace([0, np.inf, -np.inf], np.nan)
        inv_vol = (1.0 / vol).fillna(0.0)
        w = inv_vol / inv_vol.sum() if inv_vol.sum() > 0 else pd.Series(1.0 / n, index=idx)
    elif rl == "medium":
        w = pd.Series(1.0 / n, index=idx)
    elif rl == "high":
        mu = mean_returns.reindex(idx).astype(float).values
        sig = volatility.reindex(idx).astype(float).replace(0, np.nan).fillna(volatility.median()).values
        score = mu / (sig + 1e-8)
        tau = 0.6
        z = (score - np.max(score)) / max(tau, 1e-6)
        soft = np.exp(z)
        soft = soft / soft.sum()
        floor_mass = 0.10
        w = pd.Series((1 - floor_mass) * soft, index=idx) + pd.Series(floor_mass / n, index=idx)
    else:
        raise ValueError("risk_level must be 'low', 'medium', or 'high'")

    if weight_cap is not None and 0 < weight_cap < 1:
        w = w.clip(lower=0.0, upper=weight_cap)
        w = pd.Series(1.0 / n, index=idx) if w.sum() == 0 else w / w.sum()

    return w


def suggested_weights(risk_level: str, mean_returns: pd.Series, volatility: pd.Series, user_tickers: list[str]) -> pd.Series:
    raw = compute_weights(risk_level, mean_returns, volatility)
    return blend_with_stabilizers(raw, user_tickers, risk_level)


def get_risk_free_rate() -> tuple[float, str]:
    t_bill = yf.download("^IRX", period="5d", interval="1d", auto_adjust=False, progress=False)["Adj Close"]
    clean = t_bill.dropna()
    latest = clean.iloc[-1]
    if isinstance(latest, pd.Series):
        latest = latest.iloc[0]
    latest_rate = float(latest) / 100.0
    asof = clean.index[-1].date().isoformat()
    return latest_rate, asof


def _bounds(n: int, allow_shorts: bool = False):
    return [(-1.0, 1.0) if allow_shorts else (0.0, 1.0) for _ in range(n)]


def _cons_fullinvest(_n: int):
    return {"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}


def min_variance_for_return(mu, sigma, target, allow_shorts: bool = False):
    n = len(mu)
    w0 = np.ones(n) / n
    constraints = [
        _cons_fullinvest(n),
        {"type": "ineq", "fun": lambda w, mu=mu, t=target: float(mu @ w - t)},
    ]

    def var_obj(w):
        return float(w @ sigma @ w)

    res = minimize(
        var_obj,
        w0,
        method="SLSQP",
        bounds=_bounds(n, allow_shorts),
        constraints=constraints,
        options={"maxiter": 1000},
    )
    if not res.success:
        return None, (None, None)
    w = res.x
    r = float(mu @ w)
    v = float(np.sqrt(max(w @ sigma @ w, 1e-16)))
    return w, (r, v)


def max_sharpe(mu, sigma, rf: float = 0.0, allow_shorts: bool = False):
    n = len(mu)
    w0 = np.ones(n) / n

    def neg_sharpe(w):
        r = float(mu @ w)
        v = float(np.sqrt(max(w @ sigma @ w, 1e-16)))
        return -((r - rf) / v)

    res = minimize(
        neg_sharpe,
        w0,
        method="SLSQP",
        bounds=_bounds(n, allow_shorts),
        constraints=[_cons_fullinvest(n)],
        options={"maxiter": 1000},
    )
    if not res.success:
        return None, (None, None, None)
    w = res.x
    r = float(mu @ w)
    v = float(np.sqrt(max(w @ sigma @ w, 1e-16)))
    s = (r - rf) / v
    return w, (r, v, s)


def efficient_frontier(mu, sigma, n_points: int = 60, allow_shorts: bool = False):
    t_min = float(max(mu.min(), 0.0))
    t_max = float(mu.max())
    targets = np.linspace(t_min, t_max, n_points)
    vols, rets = [], []
    for target in targets:
        w, (r, v) = min_variance_for_return(mu, sigma, target, allow_shorts=allow_shorts)
        if w is None:
            continue
        rets.append(r)
        vols.append(v)
    return np.array(vols), np.array(rets)


def mc_cloud(mu, sigma, n_points: int = 1500, allow_shorts: bool = False, seed: int = 123):
    random.seed(seed)
    np.random.seed(seed)
    n = len(mu)
    vols, rets = [], []
    for _ in range(n_points):
        z = np.random.rand(n)
        if allow_shorts:
            z = (z - 0.5) * 2.0
            w = z / np.sum(np.abs(z))
        else:
            w = z / z.sum()
        r = float(mu @ w)
        v = float(np.sqrt(max(w @ sigma @ w, 1e-16)))
        vols.append(v)
        rets.append(r)
    return np.array(vols), np.array(rets)


def metrics_for(w_series: pd.Series, mean_returns: pd.Series, covariance: pd.DataFrame, rf: float):
    w = w_series.values
    mu = mean_returns.loc[w_series.index].values
    sigma = covariance.loc[w_series.index, w_series.index].values
    r = float(mu @ w)
    v = float(np.sqrt(max(w @ sigma @ w, 1e-16)))
    s = float((r - rf) / v) if v > 0 else float("nan")
    return {"expected_return": r, "portfolio_volatility": v, "sharpe_ratio": s}


def return_for_risk_explanation(sharpe_ratio: float) -> dict:
    if pd.isna(sharpe_ratio):
        return {
            "label": "Not available",
            "message": "There was not enough usable data to compare growth with risk.",
        }
    if sharpe_ratio < 0:
        return {
            "label": "Did not beat the safe baseline",
            "message": "This was negative because the estimated portfolio growth was below the baseline safe return for the selected period.",
        }
    if sharpe_ratio < 0.5:
        return {
            "label": "Weak reward for the risk",
            "message": "The portfolio earned only a small amount above the safe baseline compared with how much it moved around.",
        }
    if sharpe_ratio < 1.0:
        return {
            "label": "Reasonable reward for the risk",
            "message": "The portfolio earned more than the safe baseline, with a moderate tradeoff between growth and movement.",
        }
    return {
        "label": "Strong reward for the risk",
        "message": "The portfolio historically earned meaningfully more than the safe baseline for the amount of movement it had.",
    }


def asset_role(ticker: str, user_tickers: list[str]) -> str:
    if ticker in STABILIZER_ASSETS:
        return "Stabilizer"
    if ticker in user_tickers:
        return "Your choice"
    return "Added holding"


def max_drawdown(curve: pd.Series) -> float:
    if curve.empty:
        return float("nan")
    running_max = curve.cummax()
    return float((curve / running_max - 1.0).min())


def downside_volatility(returns: pd.Series) -> float:
    downside = returns[returns < 0]
    if downside.empty:
        return 0.0
    value = downside.std() * np.sqrt(TRADING_DAYS)
    return 0.0 if pd.isna(value) else float(value)


def risk_level_from_score(score: int) -> tuple[str, str]:
    if score <= 3:
        return "Lower", "This mix had relatively smaller swings and smaller historical losses."
    if score <= 6:
        return "Moderate", "This mix had meaningful ups and downs, but not the most extreme pattern."
    return "Higher", "This mix had larger swings, deeper historical losses, or stronger stock-market sensitivity."


def build_risk_profile(
    prices: pd.DataFrame,
    weights: pd.Series,
    portfolio_volatility: float,
    benchmark_returns: pd.Series | None = None,
) -> dict:
    weights = weights.reindex(prices.columns).fillna(0.0)
    weights = weights / weights.sum()
    returns = prices.pct_change().dropna().dot(weights)
    curve = (1.0 + returns).cumprod()

    downside = downside_volatility(returns)
    drawdown = max_drawdown(curve)
    positive_days = float((returns > 0).mean()) if len(returns) else float("nan")

    market_correlation = None
    market_beta = None
    if benchmark_returns is not None:
        aligned = pd.concat([returns.rename("portfolio"), benchmark_returns.rename("market")], axis=1).dropna()
        if len(aligned) > 2 and aligned["market"].var() > 0:
            market_correlation = float(aligned["portfolio"].corr(aligned["market"]))
            market_beta = float(aligned["portfolio"].cov(aligned["market"]) / aligned["market"].var())

    score = 0
    score += 1 if portfolio_volatility >= 0.12 else 0
    score += 1 if portfolio_volatility >= 0.20 else 0
    score += 1 if portfolio_volatility >= 0.30 else 0
    score += 1 if downside >= 0.08 else 0
    score += 1 if downside >= 0.15 else 0
    score += 1 if drawdown <= -0.20 else 0
    score += 1 if drawdown <= -0.35 else 0
    if market_beta is not None:
        score += 1 if market_beta >= 1.0 else 0
        score += 1 if market_beta >= 1.4 else 0

    label, explanation = risk_level_from_score(score)
    drivers = [
        {
            "label": "Typical yearly movement",
            "value": float(portfolio_volatility),
            "plain_language": "How much the portfolio moved up and down in a typical year.",
        },
        {
            "label": "Downside movement",
            "value": float(downside),
            "plain_language": "How much it tended to move on losing days, annualized.",
        },
        {
            "label": "Worst historical drop",
            "value": float(drawdown),
            "plain_language": "The largest fall from a previous high during the selected period.",
        },
        {
            "label": "Positive days",
            "value": positive_days,
            "plain_language": "The share of trading days that were up days.",
        },
    ]
    if market_beta is not None:
        drivers.append(
            {
                "label": "Market sensitivity",
                "value": float(market_beta),
                "plain_language": "Above 1 means it moved more than the broad U.S. market; below 1 means it moved less.",
            }
        )
    if market_correlation is not None:
        drivers.append(
            {
                "label": "Market similarity",
                "value": float(market_correlation),
                "plain_language": "Closer to 1 means it behaved more like the broad U.S. market.",
            }
        )

    return {
        "label": label,
        "score": score,
        "explanation": explanation,
        "drivers": drivers,
        "threshold_note": "The rating combines typical movement, downside movement, worst historical drop, and broad-market sensitivity.",
    }


def backtest_growth(prices: pd.DataFrame, weights: pd.Series, benchmarks: tuple[str, ...] = ("SPY", "QQQ")):
    weights = weights.reindex(prices.columns).fillna(0.0)
    weights = weights / weights.sum()
    returns = prices.pct_change().dropna()
    portfolio_curve = (1.0 + returns.dot(weights)).cumprod()

    start_date = prices.index.min().date().isoformat()
    end_date = prices.index.max().date().isoformat()
    try:
        benchmark_prices = yf.download(
            list(benchmarks),
            start=start_date,
            end=end_date,
            auto_adjust=False,
            progress=False,
        )
    except Exception:
        benchmark_prices = pd.DataFrame()

    series = {
        "Portfolio": portfolio_curve,
    }

    if "Adj Close" in benchmark_prices:
        bench_adj = benchmark_prices["Adj Close"].dropna(how="all")
        if isinstance(bench_adj, pd.Series):
            bench_adj = bench_adj.to_frame()
        for ticker in benchmarks:
            if ticker in bench_adj.columns:
                curve = bench_adj[ticker].dropna()
                if not curve.empty:
                    series[ticker] = curve / curve.iloc[0]

    combined = pd.concat(series, axis=1).dropna(how="all").ffill().dropna(how="all")
    points = []
    for dt, row in combined.iterrows():
        item = {"date": dt.date().isoformat()}
        for name in combined.columns:
            val = row[name]
            if pd.notna(val):
                item[name] = float(val)
        points.append(item)

    summary = {}
    for name in combined.columns:
        col = combined[name].dropna()
        if col.empty:
            continue
        label = BENCHMARK_LABELS.get(name, name)
        summary[name] = {
            "label": label,
            "ending_value": float(col.iloc[-1]),
            "total_return": float(col.iloc[-1] - 1.0),
            "max_drawdown": max_drawdown(col),
        }

    return {"series": points, "summary": summary}


def benchmark_daily_returns(start_date: str, end_date: str, ticker: str = "SPY") -> pd.Series | None:
    try:
        benchmark = yf.download(ticker, start=start_date, end=end_date, auto_adjust=False, progress=False)
    except Exception:
        return None
    if "Adj Close" not in benchmark:
        return None
    adj = benchmark["Adj Close"].dropna()
    if isinstance(adj, pd.DataFrame):
        adj = adj.iloc[:, 0]
    returns = adj.pct_change().dropna()
    if returns.empty:
        return None
    returns.name = ticker
    return returns


def optimize_payload(tickers: list[str], risk_level: str, investment_period: int, amount: float | None):
    all_tickers, stabilizer_info = expand_with_stabilizers(tickers, risk_level)
    market = fetch_market_data(all_tickers, investment_period)
    user_tickers = [ticker for ticker in stabilizer_info["user_tickers"] if ticker in market.tickers]
    if not user_tickers:
        raise ValueError("None of your selected holdings returned usable price data.")
    mean_r = market.mean_returns
    volatility = market.volatility
    cov = market.covariance

    weights = suggested_weights(risk_level, mean_r, volatility, user_tickers)
    weights = weights / weights.sum()

    rf_dec, asof = get_risk_free_rate()
    mu = mean_r.loc[weights.index].values
    sigma = cov.loc[weights.index, weights.index].values

    ew = pd.Series(1.0 / len(market.tickers), index=weights.index, name="EW")
    inv_vol = (1.0 / volatility.reindex(weights.index)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    inv_vol = (inv_vol / inv_vol.sum()).rename("InvVol")

    w_mv, _ = min_variance_for_return(mu, sigma, target=max(mu.min(), 0.0), allow_shorts=False)
    mv = pd.Series(w_mv, index=weights.index, name="MinVar") if w_mv is not None else None

    w_ms, _ = max_sharpe(mu, sigma, rf=rf_dec, allow_shorts=False)
    ms = pd.Series(w_ms, index=weights.index, name="MaxSharpe") if w_ms is not None else None

    dollars = (weights * amount).round(2) if amount is not None else None
    portfolio = []
    for ticker in weights.index:
        portfolio.append(
            {
                "Ticker": str(ticker),
                "Role": asset_role(str(ticker), user_tickers),
                "Description": STABILIZER_ASSETS.get(str(ticker), "Selected holding"),
                "Weight": float(weights[ticker]),
                "Expected_Return": float(mean_r[ticker]),
                "volatility": float(volatility[ticker]),
                "Dollars": float(dollars[ticker]) if dollars is not None else None,
            }
        )

    strategies = []

    def add_strategy(name: str, w_ser: pd.Series | None, blurb: str):
        if w_ser is None:
            return
        metrics = metrics_for(w_ser, mean_r, cov, rf_dec)
        strategies.append(
            {
                "name": name,
                "blurb": blurb,
                "metrics": {k: float(v) for k, v in metrics.items()},
                "weights": [{"Ticker": str(t), "Weight": float(w_ser[t])} for t in w_ser.index],
            }
        )

    add_strategy(f"Suggested ({risk_level})", weights, "Uses your choices plus stabilizers matched to your risk comfort.")
    add_strategy("Equal Weight", ew, "Simple 1/N baseline.")
    add_strategy("Inverse Volatility", inv_vol, "Lower-movement holdings get higher weights.")
    add_strategy("Min-Variance", mv, "The steadiest mix found from your choices.")
    add_strategy("Max Sharpe", ms, "The mix with the best historical balance of growth and movement.")

    suggested_metrics = metrics_for(weights, mean_r, cov, rf_dec)
    market_returns = benchmark_daily_returns(market.start_date, market.end_date, "SPY")
    risk_profile = build_risk_profile(
        market.prices,
        weights,
        suggested_metrics["portfolio_volatility"],
        benchmark_returns=market_returns,
    )
    return {
        "portfolio": portfolio,
        "metrics": {
            "expected_return": float(suggested_metrics["expected_return"]),
            "portfolio_volatility": float(suggested_metrics["portfolio_volatility"]),
            "sharpe_ratio": float(suggested_metrics["sharpe_ratio"]),
            "sharpe_interpretation": return_for_risk_explanation(suggested_metrics["sharpe_ratio"]),
            "risk_free_rate": float(rf_dec) * 100.0,
            "risk_free_rate_asof": asof,
        },
        "strategies": strategies,
        "backtest": backtest_growth(market.prices, weights),
        "risk_profile": risk_profile,
        "inputs": {
            "tickers": market.tickers,
            "requested_tickers": stabilizer_info["user_tickers"],
            "risk_level": risk_level,
            "investment_period": investment_period,
            "amount": amount,
            "start_date": market.start_date,
            "end_date": market.end_date,
        },
        "stabilizers": stabilizer_info,
        "note": {"dropped_missing_tickers": market.missing},
    }


def frontier_payload(tickers: list[str], risk_level: str, investment_period: int, target_vol: float | None = None):
    all_tickers, stabilizer_info = expand_with_stabilizers(tickers, risk_level)
    market = fetch_market_data(all_tickers, investment_period)
    user_tickers = [ticker for ticker in stabilizer_info["user_tickers"] if ticker in market.tickers]
    if not user_tickers:
        raise ValueError("None of your selected holdings returned usable price data.")
    mean_r = market.mean_returns
    volatility = market.volatility
    cov = market.covariance
    mu = mean_r.values
    sigma = cov.values

    weights = suggested_weights(risk_level, mean_r, volatility, user_tickers)
    weights = weights / weights.sum()
    r_suggest = float(mu @ weights.values)
    v_suggest = float(np.sqrt(max(weights.values @ sigma @ weights.values, 1e-16)))

    ef_vol, ef_ret = efficient_frontier(mu, sigma, n_points=60, allow_shorts=False)
    w_mv, (r_mv, v_mv) = min_variance_for_return(mu, sigma, target=max(mu.min(), 0.0), allow_shorts=False)
    rf_dec, rf_asof = get_risk_free_rate()
    w_ms, (r_ms, v_ms, s_ms) = max_sharpe(mu, sigma, rf=rf_dec, allow_shorts=False)

    cloud_vol, cloud_ret = mc_cloud(mu, sigma, n_points=1200, allow_shorts=False)
    idx = np.linspace(0, len(cloud_vol) - 1, 600, dtype=int)
    cloud_vol = cloud_vol[idx]
    cloud_ret = cloud_ret[idx]

    opt_at_target = None
    if target_vol is not None and len(ef_vol) > 0:
        k = int(np.argmin(np.abs(ef_vol - target_vol)))
        opt_at_target = {"vol": float(ef_vol[k]), "ret": float(ef_ret[k])}

    return {
        "tickers": market.tickers,
        "rf": {"rate": float(rf_dec), "asof": rf_asof},
        "frontier": {"vol": ef_vol.tolist(), "ret": ef_ret.tolist()},
        "cloud": {"vol": cloud_vol.tolist(), "ret": cloud_ret.tolist()},
        "points": {
            "min_var": {"vol": float(v_mv), "ret": float(r_mv)},
            "max_sharpe": {"vol": float(v_ms), "ret": float(r_ms), "sharpe": float(s_ms)},
            "suggested": {"vol": float(v_suggest), "ret": float(r_suggest)},
        },
        "opt_at_target": opt_at_target,
    }

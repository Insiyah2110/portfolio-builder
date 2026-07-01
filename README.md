# Portfolio Builder

Portfolio Builder is a Flask web app for building and comparing guided investment mixes. Users can either answer a short questionnaire that selects a broad ETF starting basket, or enter their own ticker symbols. The app downloads historical market data with `yfinance`, adds stabilizing funds based on the selected risk level, calculates allocation metrics, and presents the results in a browser workspace.

The app is intended for learning and exploration. It is not financial advice.

## Current Features

- Use Guided mode to build a sample portfolio from goal, horizon, risk comfort, loss tolerance, liquidity needs, emergency savings, and contribution pattern.
- Use Custom mode to enter ticker symbols, a risk level, an investment period, and an optional investment amount.
- Translate Guided mode answers into a curated ETF basket and risk setting before running the same optimizer used by Custom mode.
- Automatically add stabilizer assets:
  - `SGOV` and `BND` for lower-risk and moderate-risk portfolios.
  - `SGOV` for higher-risk portfolios.
- Compare suggested, minimum-variance, and maximum-Sharpe strategies.
- Show estimated yearly growth, typical yearly movement, Sharpe ratio interpretation, and the current 3-month U.S. Treasury baseline.
- Backtest how $1 would have grown compared with broad market examples.
- Draw an efficient-frontier tradeoff view in the browser.
- Save and reload portfolio scenarios in a local SQLite database.

## Guided Questionnaire

Guided mode intentionally asks for broad categories instead of exact personal financial details. The questionnaire uses:

- Main goal: long-term wealth, retirement, education, major purchase, or emergency reserve.
- Time horizon: 0-2 years, 3-5 years, 6-10 years, or 10+ years.
- Risk comfort and maximum loss tolerance.
- Liquidity need: whether the user may need the money soon.
- Emergency savings status.
- Contribution pattern.

The questionnaire maps those answers to one of four starting profiles:

- `cash_first`: starts from `SGOV` for very short-term or very low-risk cases.
- `conservative`: starts from `VTI` and `VXUS` with a lower-risk setting.
- `balanced`: starts from `VTI` and `VXUS` with a moderate-risk setting.
- `growth`: starts from `VTI`, `VXUS`, and `QQQ` with a higher-risk setting.

After that mapping, the normal optimizer still runs. It may add stabilizers such as `SGOV` and `BND`, then calculates the same recommendations, risk checks, backtest, and efficient-frontier view.

## Project Structure

```text
.
├── app.py                  # Flask routes and application entry point
├── portfolio/
│   ├── optimizer.py        # Market-data fetching, optimization, metrics, and payload builders
│   ├── questionnaire.py    # Guided-mode scoring and ETF basket selection
│   └── storage.py          # SQLite persistence for saved scenarios
├── static/
│   ├── app.js              # Browser UI behavior, chart drawing, and API calls
│   └── styles.css          # App styling
├── templates/
│   └── index.html          # Main Flask template
├── requirements.txt        # Python dependencies
├── Procfile                # Gunicorn start command
└── render.yaml             # Render deployment config
```

## Local Setup

Create and activate a virtual environment, then install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the app:

```bash
python app.py
```

Open `http://127.0.0.1:5055`.

## Data and Persistence

Market data comes from Yahoo Finance through `yfinance`, so optimization requests require network access. Saved scenarios are stored in `portfolio_builder.sqlite3` by default. To use a different database path, set `DATABASE_PATH` before starting the app.

Runtime databases, virtual environments, Python caches, local secrets, and generated/reference artifacts are intentionally ignored by git.

## Deployment

The repository includes both a `Procfile` and `render.yaml`. Production runs with:

```bash
gunicorn app:app --workers 2 --timeout 120
```

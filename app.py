from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from portfolio.optimizer import frontier_payload, optimize_payload
from portfolio.storage import get_portfolio, init_db, list_portfolios, save_portfolio


app = Flask(__name__)
init_db()


def _json_error(message: str, status: int):
    return (message, status)


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/optimize")
def optimize():
    try:
        data = request.get_json(force=True)
        amount = data.get("amount", None)
        if isinstance(amount, str) and amount.strip() == "":
            amount = None
        amount = float(amount) if amount is not None else None

        payload = optimize_payload(
            tickers=data.get("tickers") or [],
            risk_level=data.get("risk_level", "medium"),
            investment_period=int(data.get("investment_period", 3)),
            amount=amount,
        )
        return jsonify(payload)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@app.post("/frontier")
def frontier():
    try:
        data = request.get_json(force=True)
        target_vol = data.get("target_vol", None)
        target_vol = float(target_vol) if target_vol not in (None, "") else None
        payload = frontier_payload(
            tickers=data.get("tickers") or [],
            risk_level=data.get("risk_level", "medium"),
            investment_period=int(data.get("investment_period", 3)),
            target_vol=target_vol,
        )
        return jsonify(payload)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@app.get("/portfolios")
def portfolios_index():
    return jsonify({"portfolios": list_portfolios()})


@app.get("/portfolios/<int:portfolio_id>")
def portfolios_show(portfolio_id: int):
    portfolio = get_portfolio(portfolio_id)
    if portfolio is None:
        return _json_error("Saved portfolio not found", 404)
    return jsonify(portfolio)


@app.post("/portfolios")
def portfolios_create():
    try:
        data = request.get_json(force=True)
        payload = data.get("payload")
        if not isinstance(payload, dict):
            return _json_error("Provide an optimization payload to save", 400)
        saved = save_portfolio(data.get("name", ""), payload)
        return jsonify({"saved": saved}), 201
    except Exception as exc:
        return _json_error(str(exc), 500)


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5055)

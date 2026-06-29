from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import sqlite3
from pathlib import Path


DB_PATH = Path(os.environ.get("DATABASE_PATH", "portfolio_builder.sqlite3"))


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_portfolios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                tickers TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                investment_period INTEGER NOT NULL,
                amount REAL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def save_portfolio(name: str, payload: dict) -> dict:
    init_db()
    inputs = payload.get("inputs", {})
    record_name = (name or "").strip() or f"{inputs.get('risk_level', 'Portfolio').title()} portfolio"
    created_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO saved_portfolios
                (name, tickers, risk_level, investment_period, amount, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_name,
                json.dumps(inputs.get("requested_tickers") or inputs.get("tickers", [])),
                inputs.get("risk_level", ""),
                int(inputs.get("investment_period", 0)),
                inputs.get("amount"),
                json.dumps(payload),
                created_at,
            ),
        )
        portfolio_id = int(cur.lastrowid)
    return {"id": portfolio_id, "name": record_name, "created_at": created_at}


def list_portfolios() -> list[dict]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, tickers, risk_level, investment_period, amount, created_at
            FROM saved_portfolios
            ORDER BY datetime(created_at) DESC, id DESC
            """
        ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "tickers": json.loads(row["tickers"]),
            "risk_level": row["risk_level"],
            "investment_period": row["investment_period"],
            "amount": row["amount"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def get_portfolio(portfolio_id: int) -> dict | None:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, payload, created_at FROM saved_portfolios WHERE id = ?",
            (portfolio_id,),
        ).fetchone()
    if row is None:
        return None
    payload = json.loads(row["payload"])
    payload["saved"] = {"id": row["id"], "name": row["name"], "created_at": row["created_at"]}
    return payload

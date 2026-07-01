from __future__ import annotations


GOAL_LABELS = {
    "emergency": "Emergency or cash reserve",
    "major_purchase": "Major purchase",
    "education": "Education",
    "retirement": "Retirement",
    "wealth": "Long-term wealth growth",
}

HORIZON_LABELS = {
    "0_2": "0-2 years",
    "3_5": "3-5 years",
    "6_10": "6-10 years",
    "10_plus": "10+ years",
}

RISK_LABELS = {
    "low": "Lower risk",
    "medium": "Moderate risk",
    "high": "Higher risk",
}

LOSS_LABELS = {
    "none": "I would avoid losses where possible",
    "5": "Around 5%",
    "10": "Around 10%",
    "20": "Around 20%",
    "30_plus": "More than 30%",
}

LIQUIDITY_LABELS = {
    "soon": "I may need this money soon",
    "some": "I may need part of it",
    "rare": "I do not expect to touch it",
}

EMERGENCY_LABELS = {
    "none": "No emergency fund yet",
    "partial": "Some emergency savings",
    "funded": "Emergency fund is already covered",
}

CONTRIBUTION_LABELS = {
    "none": "No planned additions",
    "small": "Occasional or small additions",
    "steady": "Steady monthly additions",
}

ETF_UNIVERSES = {
    "cash_first": ["SGOV"],
    "conservative": ["VTI", "VXUS"],
    "balanced": ["VTI", "VXUS"],
    "growth": ["VTI", "VXUS", "QQQ"],
}


def _answer(answers: dict, key: str, default: str) -> str:
    value = str((answers or {}).get(key, default)).strip()
    return value or default


def _score_answers(answers: dict) -> tuple[int, list[str]]:
    score = 0
    reasons = []

    goal = _answer(answers, "goal", "wealth")
    if goal in {"emergency", "major_purchase"}:
        score -= 2
        reasons.append("The goal may need steadier assets because the money could have a specific near-term use.")
    elif goal in {"retirement", "wealth"}:
        score += 1
        reasons.append("The goal can usually support more market exposure when the time horizon is long enough.")

    horizon = _answer(answers, "horizon", "6_10")
    if horizon == "0_2":
        score -= 4
        reasons.append("A short time horizon reduces the room to recover from market drops.")
    elif horizon == "3_5":
        score -= 1
        reasons.append("A medium-short time horizon calls for a more balanced starting point.")
    elif horizon == "10_plus":
        score += 3
        reasons.append("A long time horizon gives the portfolio more time to ride through ups and downs.")
    else:
        score += 1

    risk_comfort = _answer(answers, "risk_comfort", "medium")
    if risk_comfort == "low":
        score -= 2
        reasons.append("Lower stated risk comfort points toward a steadier mix.")
    elif risk_comfort == "high":
        score += 2
        reasons.append("Higher stated risk comfort allows the model to consider a growth-oriented mix.")

    loss_tolerance = _answer(answers, "loss_tolerance", "10")
    if loss_tolerance in {"none", "5"}:
        score -= 3
        reasons.append("Low loss tolerance makes large stock exposure harder to justify.")
    elif loss_tolerance == "20":
        score += 1
    elif loss_tolerance == "30_plus":
        score += 2
        reasons.append("Higher loss tolerance supports accepting more movement for possible growth.")

    liquidity = _answer(answers, "liquidity", "some")
    if liquidity == "soon":
        score -= 3
        reasons.append("Money that may be needed soon should usually be less exposed to market swings.")
    elif liquidity == "rare":
        score += 1

    emergency_fund = _answer(answers, "emergency_fund", "partial")
    if emergency_fund == "none":
        score -= 2
        reasons.append("Without an emergency fund, the portfolio should leave more room for stability.")
    elif emergency_fund == "funded":
        score += 1

    contribution = _answer(answers, "contribution", "small")
    if contribution == "steady":
        score += 1
        reasons.append("Steady contributions can soften the impact of buying before a market drop.")

    return score, reasons


def questionnaire_portfolio(answers: dict) -> dict:
    selected = {
        "goal": _answer(answers, "goal", "wealth"),
        "horizon": _answer(answers, "horizon", "6_10"),
        "risk_comfort": _answer(answers, "risk_comfort", "medium"),
        "loss_tolerance": _answer(answers, "loss_tolerance", "10"),
        "liquidity": _answer(answers, "liquidity", "some"),
        "emergency_fund": _answer(answers, "emergency_fund", "partial"),
        "contribution": _answer(answers, "contribution", "small"),
    }
    score, reasons = _score_answers(answers or {})
    horizon = selected["horizon"]

    if score <= -5:
        profile = "cash_first"
        risk_level = "low"
        investment_period = 1 if horizon == "0_2" else 3
    elif score <= 0:
        profile = "conservative"
        risk_level = "low"
        investment_period = 3 if horizon in {"0_2", "3_5"} else 5
    elif score <= 4:
        profile = "balanced"
        risk_level = "medium"
        investment_period = 5 if horizon in {"3_5", "6_10"} else 10
    else:
        profile = "growth"
        risk_level = "high"
        investment_period = 10

    tickers = ETF_UNIVERSES[profile]
    labels = {
        "goal": GOAL_LABELS.get(selected["goal"], "Long-term wealth growth"),
        "horizon": HORIZON_LABELS.get(horizon, "6-10 years"),
        "risk_comfort": RISK_LABELS.get(selected["risk_comfort"], "Moderate risk"),
        "loss_tolerance": LOSS_LABELS.get(selected["loss_tolerance"], "Around 10%"),
        "liquidity": LIQUIDITY_LABELS.get(selected["liquidity"], "I may need part of it"),
        "emergency_fund": EMERGENCY_LABELS.get(selected["emergency_fund"], "Some emergency savings"),
        "contribution": CONTRIBUTION_LABELS.get(selected["contribution"], "Occasional or small additions"),
    }

    return {
        "mode": "guided",
        "answers": selected,
        "profile": profile,
        "score": score,
        "tickers": tickers,
        "risk_level": risk_level,
        "investment_period": investment_period,
        "labels": labels,
        "reasons": reasons[:4],
        "explanation": (
            "The questionnaire selects a broad ETF starting basket and risk setting from goal, horizon, "
            "risk comfort, loss tolerance, liquidity needs, emergency savings, and contribution pattern."
        ),
        "note": "Uses broad ranges only. This is an educational model, not financial advice.",
    }

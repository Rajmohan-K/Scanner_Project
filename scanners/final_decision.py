from __future__ import annotations

from typing import Any


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _action_text(row: dict[str, Any]) -> str:
    return str(
        row.get("action")
        or row.get("premarket_action")
        or row.get("signal")
        or row.get("trade_type")
        or row.get("final_decision")
        or ""
    ).upper()


def final_trade_grade(meta_score: float) -> str:
    if meta_score >= 90:
        return "A+"
    if meta_score >= 80:
        return "A"
    if meta_score >= 70:
        return "B"
    return "Reject"


def decide(row: dict[str, Any]) -> dict[str, Any]:
    meta_score = _float(row.get("meta_score"))
    risk_score = _float(row.get("risk_score"))
    backtest_score = _float(row.get("backtest_score"))
    ml_confidence = _float(row.get("ml_confidence"))
    risk_reward = _float(row.get("risk_reward_ratio") or row.get("risk_reward") or row.get("rrr"))
    action = _action_text(row)
    conflicts = row.get("conflict_warnings") or []
    if isinstance(conflicts, str):
        conflicts = [part.strip() for part in conflicts.split("|") if part.strip()]

    reasons: list[str] = []
    rejection_reasons: list[str] = []

    if meta_score >= 80:
        reasons.append("Meta score passed strict opportunity threshold")
    else:
        rejection_reasons.append("Meta score below 80")
    if risk_score <= 55:
        reasons.append("Risk score acceptable")
    else:
        rejection_reasons.append("Risk score above acceptable threshold")
    if backtest_score >= 70:
        reasons.append("Backtest validation passed")
    else:
        rejection_reasons.append("Backtest score below 70")
    if ml_confidence >= 65:
        reasons.append("ML confidence confirmed")
    else:
        rejection_reasons.append("ML confidence below 65")
    if risk_reward >= 2:
        reasons.append("Risk reward is at least 1:2")
    else:
        rejection_reasons.append("Risk reward below 1:2")
    if "AVOID" in action or "REJECT" in action:
        rejection_reasons.append("Source scanner marked avoid/reject")
    if conflicts:
        rejection_reasons.append("Scanner conflicts present")

    should_trade = (
        meta_score >= 80
        and risk_score <= 55
        and backtest_score >= 70
        and ml_confidence >= 65
        and risk_reward >= 2
        and "AVOID" not in action
        and "REJECT" not in action
        and not conflicts
    )
    should_watch = not should_trade and meta_score >= 65 and risk_score <= 70 and "AVOID" not in action
    should_reject = not should_trade and not should_watch

    if should_trade:
        decision = "Trade"
    elif should_watch:
        decision = "Watch"
    elif meta_score < 50 or "AVOID" in action or "REJECT" in action:
        decision = "Reject"
    else:
        decision = "No Trade"

    return {
        **row,
        "final_decision": decision,
        "trade_grade": final_trade_grade(meta_score),
        "should_show": should_trade or should_watch,
        "should_trade": should_trade,
        "should_watch": should_watch,
        "should_reject": should_reject,
        "reason_selected": " | ".join(reasons) if reasons else "",
        "reason_rejected": " | ".join(rejection_reasons) if rejection_reasons else "",
        "decision_summary": (
            "Shown as trade candidate"
            if should_trade
            else "Watch only, not trade-ready"
            if should_watch
            else "Hidden by final decision engine"
        ),
    }

from __future__ import annotations

from typing import Any


FAST_RULES = {
    "standard": {
        "min_coarse_quality": 5,
        "min_coarse_confidence": 45,
        "max_coarse_risk": 35,
        "min_volume": 50000,
    },
    "strict": {
        "min_coarse_quality": 18,
        "min_coarse_confidence": 55,
        "max_coarse_risk": 25,
        "min_volume": 100000,
    },
}


DEEP_RULES = {
    "standard": {
        "min_abs_score": 15,
        "min_confidence": 50,
        "min_ml_probability": 50,
        "min_quality_score": 48,
        "min_profitability_score": 8,
        "min_expected_return_pct": 0,
        "min_premarket_grade": 45,
        "min_risk_reward": 1.15,
        "max_stop_distance_pct": 8,
        "min_data_reliability_score": 15,
        "max_drawdown": 30,
        "allow_risk_levels": {"Low", "Medium"},
        "allow_status": {"Qualified", "Watchlist"},
    },
    "strict": {
        "min_abs_score": 22,
        "min_confidence": 60,
        "min_ml_probability": 60,
        "min_quality_score": 58,
        "min_profitability_score": 15,
        "min_expected_return_pct": 5,
        "min_premarket_grade": 58,
        "min_risk_reward": 1.4,
        "max_stop_distance_pct": 5,
        "min_data_reliability_score": 35,
        "max_drawdown": 22,
        "allow_risk_levels": {"Low", "Medium"},
        "allow_status": {"Qualified"},
    },
}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _mode(strict: bool) -> str:
    return "strict" if strict else "standard"


def _rules_with_overrides(base_rules: dict[str, Any], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    rules = dict(base_rules)
    if not overrides:
        return rules

    numeric_keys = {
        "min_abs_score",
        "min_confidence",
        "min_ml_probability",
        "min_quality_score",
        "min_profitability_score",
        "min_expected_return_pct",
        "min_premarket_grade",
        "min_risk_reward",
        "max_stop_distance_pct",
        "min_data_reliability_score",
        "max_drawdown",
    }
    for key in numeric_keys:
        if key in overrides and overrides[key] is not None:
            rules[key] = _as_float(overrides[key], rules[key])
    return rules


def passes_fast_filter(row: dict[str, Any], strict: bool = False) -> tuple[bool, list[str]]:
    rules = FAST_RULES[_mode(strict)]
    reasons: list[str] = []

    if _as_float(row.get("coarse_quality")) < rules["min_coarse_quality"]:
        reasons.append(f"coarse_quality<{rules['min_coarse_quality']}")
    if _as_float(row.get("coarse_confidence")) < rules["min_coarse_confidence"]:
        reasons.append(f"coarse_confidence<{rules['min_coarse_confidence']}")
    if _as_float(row.get("coarse_risk")) > rules["max_coarse_risk"]:
        reasons.append(f"coarse_risk>{rules['max_coarse_risk']}")
    if _as_float(row.get("volume")) < rules["min_volume"]:
        reasons.append(f"volume<{rules['min_volume']}")

    return not reasons, reasons


def passes_deep_filter(
    row: dict[str, Any],
    strict: bool = False,
    overrides: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    rules = _rules_with_overrides(DEEP_RULES[_mode(strict)], overrides)
    reasons: list[str] = []

    if abs(_as_float(row.get("score"))) < rules["min_abs_score"]:
        reasons.append(f"score<{rules['min_abs_score']}")
    if _as_float(row.get("confidence_pct")) < rules["min_confidence"]:
        reasons.append(f"confidence<{rules['min_confidence']}")
    if _as_float(row.get("ml_probability")) < rules["min_ml_probability"]:
        reasons.append(f"ml<{rules['min_ml_probability']}")
    if _as_float(row.get("quality_score")) < rules["min_quality_score"]:
        reasons.append(f"quality<{rules['min_quality_score']}")
    if _as_float(row.get("profitability_score")) < rules["min_profitability_score"]:
        reasons.append(f"profitability<{rules['min_profitability_score']}")
    if _as_float(row.get("expected_return")) < rules["min_expected_return_pct"]:
        reasons.append(f"expected_return<{rules['min_expected_return_pct']}")
    if _as_float(row.get("premarket_grade")) < rules["min_premarket_grade"]:
        reasons.append(f"premarket_grade<{rules['min_premarket_grade']}")
    if _as_float(row.get("risk_reward")) < rules["min_risk_reward"]:
        reasons.append(f"rr<{rules['min_risk_reward']}")
    if _as_float(row.get("stop_distance_pct")) > rules["max_stop_distance_pct"]:
        reasons.append(f"stop_distance>{rules['max_stop_distance_pct']}")
    if _as_float(row.get("data_reliability_score")) < rules["min_data_reliability_score"]:
        reasons.append(f"data_reliability<{rules['min_data_reliability_score']}")
    if _as_float(row.get("max_drawdown")) > rules["max_drawdown"]:
        reasons.append(f"drawdown>{rules['max_drawdown']}")

    risk_level = str(row.get("risk_level", "Unknown") or "Unknown")
    if risk_level not in rules["allow_risk_levels"]:
        reasons.append(f"risk={risk_level}")

    status = str(row.get("premarket_status", "Rejected") or "Rejected")
    if status not in rules["allow_status"]:
        reasons.append(f"status={status}")

    return not reasons, reasons


def annotate_deep_filter(
    row: dict[str, Any],
    strict: bool = False,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    passed, reasons = passes_deep_filter(row, strict=strict, overrides=overrides)
    return {
        **row,
        "quality_filter_passed": passed,
        "quality_filter_reasons": " | ".join(reasons),
    }

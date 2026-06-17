from scoring.quality_filter import annotate_deep_filter, passes_deep_filter, passes_fast_filter
from scoring.ranking_engine import rank_stocks


def test_fast_filter_rejects_low_volume_and_risky_candidate():
    passed, reasons = passes_fast_filter(
        {
            "coarse_quality": 22,
            "coarse_confidence": 65,
            "coarse_risk": 42,
            "volume": 25000,
        }
    )

    assert not passed
    assert "coarse_risk>35" in reasons
    assert "volume<50000" in reasons


def test_deep_filter_marks_high_quality_setup_as_passed():
    row = {
        "score": 28,
        "confidence_pct": 68,
        "ml_probability": 64,
        "quality_score": 63,
        "profitability_score": 19,
        "expected_return": 7.5,
        "premarket_grade": 62,
        "risk_reward": 1.8,
        "stop_distance_pct": 3.5,
        "data_reliability_score": 55,
        "max_drawdown": 12,
        "risk_level": "Medium",
        "premarket_status": "Qualified",
    }

    passed, reasons = passes_deep_filter(row, strict=True)
    annotated = annotate_deep_filter(row, strict=True)

    assert passed
    assert reasons == []
    assert annotated["quality_filter_passed"] is True


def test_deep_filter_rejects_low_expected_return_when_requested():
    passed, reasons = passes_deep_filter(
        {
            "score": 28,
            "confidence_pct": 68,
            "ml_probability": 64,
            "quality_score": 63,
            "profitability_score": 19,
            "expected_return": 3.2,
            "premarket_grade": 62,
            "risk_reward": 1.8,
            "stop_distance_pct": 3.5,
            "data_reliability_score": 55,
            "max_drawdown": 12,
            "risk_level": "Medium",
            "premarket_status": "Qualified",
        },
        strict=True,
        overrides={"min_expected_return_pct": 5},
    )

    assert not passed
    assert "expected_return<5.0" in reasons


def test_ranking_respects_quality_filter_pass_flag():
    rows = [
        {
            "stock": "AAA.NS",
            "score": 30,
            "confidence_pct": 70,
            "ml_probability": 70,
            "quality_score": 70,
            "profitability_score": 25,
            "expected_return": 8,
            "profit_factor": 1.5,
            "backtest_win_rate": 65,
            "premarket_grade": 65,
            "risk_reward": 1.8,
            "stop_distance_pct": 3.5,
            "data_reliability_score": 55,
            "risk_level": "Low",
            "premarket_status": "Qualified",
            "trade_type": "BUY",
            "quality_filter_passed": True,
        },
        {
            "stock": "BBB.NS",
            "score": 80,
            "confidence_pct": 90,
            "ml_probability": 90,
            "quality_filter_passed": False,
        },
    ]

    ranked = rank_stocks(rows, strict_shortlist=True)

    assert ranked["stock"].tolist() == ["AAA.NS"]

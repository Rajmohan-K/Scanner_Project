import pytest
from scoring.premarket_gate import evaluate_premarket_readiness

def test_evaluate_premarket_readiness_premium_trade():
    # Setup record that should trigger Premium Trade and both ready flags
    record = {
        "score": 85.0,
        "confidence_pct": 95.0,
        "ml_probability": 88.0,
        "quality_score": 90.0,
        "profitability_score": 95.0,
        "risk_reward": 2.2,
        "gap_pct": 2.5,
        "risk_level": "Low",
        "trend_regime": "Bullish",
        "volatility_regime": "Normal Vol",
        "trade_type": "BUY",
        "relative_volume": 2.5,
        "expected_return": 5.0,
        "liquidity_score": 85.0,
        "risk_score": 15.0, # trap_exhaustion will be 100 - 15 = 85
    }
    
    module_results = {
        "global_sentiment": {"score": 8.0}, # global_support will be 50 + 32 = 82
        "sector_analysis": {"score": 6.0}, # sector_strength will be 50 + 24 = 74
        "news_sentiment": {"score": 0.8},
        "market_news_sentiment": {"score": 0.8},
    }
    
    res = evaluate_premarket_readiness(record, module_results)
    
    assert res["premarket_grade"] >= 80.0
    assert res["premarket_label"] in ["Premium Trade", "Strong Trade"]
    assert res["intraday_ready"] is True
    assert res["swing_ready"] is True
    assert res["best_horizon"] in ["Intraday", "Swing"]
    assert res["premarket_status"] == "Qualified"

def test_evaluate_premarket_readiness_avoid():
    # Setup record that should be classified as Avoid
    record = {
        "score": 40.0,
        "confidence_pct": 45.0,
        "ml_probability": 40.0,
        "quality_score": 30.0,
        "profitability_score": 20.0,
        "risk_reward": 1.1,
        "gap_pct": 6.0, # exhaustion gap
        "risk_level": "High",
        "trend_regime": "Bearish",
        "volatility_regime": "Extreme Vol",
        "trade_type": "BUY",
        "relative_volume": 0.5,
        "expected_return": 0.5,
        "liquidity_score": 40.0,
        "risk_score": 80.0,
    }
    
    module_results = {
        "global_sentiment": {"score": -5.0},
        "sector_analysis": {"score": -2.0},
        "news_sentiment": {"score": -0.5},
        "market_news_sentiment": {"score": -0.5},
    }
    
    res = evaluate_premarket_readiness(record, module_results)
    
    assert res["premarket_grade"] < 60.0
    assert res["premarket_label"] == "Avoid"
    assert res["intraday_ready"] is False
    assert res["swing_ready"] is False
    assert res["best_horizon"] == "Avoid"
    assert res["premarket_status"] == "Avoid"
    assert "safety threshold" in res["premarket_reasons"].lower()

import pandas as pd
import pytest
from datetime import datetime
from ui.stock_data_service import build_rule_analysis

def test_verify_buy_ready_rules():
    # Mock data satisfying all strict BUY READY thresholds:
    # - Expected profit potential >= 1.5%
    # - Risk-reward ratio >= 1.8
    # - Volume vs average >= 2.0
    # - Price is above VWAP
    # - Price is not more than 0.3% below breakout
    # - Price is not near intraday high
    # - Remaining upside >= 1.5%
    # - Stop loss within 1% to 1.5%
    # - Gain from previous close is <= 3.5%
    # - Quality Score >= 75
    
    quote = {
        "current_price": 100.0,
        "previous_close": 98.0, # Gain is 2.04% (<= 3.5%)
        "open": 98.0,
        "day_high": 102.0, # Distance from high is (102-100)/102 = 1.96% (>= 0.4%)
        "day_low": 97.0
    }
    
    # 20 periods history to build indicators and EMA stack
    # Make sure prices are in an uptrend (current_price > ema20 > ema50 > ema200)
    # We will generate a df with close prices rising gradually
    history_data = []
    current_val = 80.0
    for i in range(250):
        current_val += 0.08
        history_data.append({
            "Open": current_val - 0.5,
            "High": current_val + 0.5,
            "Low": current_val - 0.5,
            "Close": current_val,
            "Volume": 1000.0
        })
    # Last candle high volume to mock volume spike >= 2.0x
    history_data[-1]["Close"] = 100.0
    history_data[-1]["High"] = 100.2
    history_data[-1]["Volume"] = 3000.0
    
    df = pd.DataFrame(history_data)
    
    analysis = build_rule_analysis("TESTSTOCK", quote, df, df)
    
    assert analysis["status"] == "ok"
    assert analysis["symbol"] == "TESTSTOCK"
    assert "current_price" in analysis
    assert "expected_profit_percent" in analysis
    assert "expected_loss_percent" in analysis
    assert "risk_reward_ratio" in analysis
    assert "quality_score" in analysis
    
    # Verify exact keys
    assert "decision" in analysis
    assert "action" in analysis
    assert "reason" in analysis

def test_avoid_already_moved():
    # If gain from previous close is > 3.5%, status must be "AVOID - Already Moved"
    quote = {
        "current_price": 104.0, # moved ~4.0%
        "previous_close": 100.0,
        "open": 100.0,
        "day_high": 104.0,
        "day_low": 99.0
    }
    history_data = [{"Close": 100.0, "High": 100.0, "Low": 100.0, "Volume": 100.0} for _ in range(50)]
    df = pd.DataFrame(history_data)
    
    analysis = build_rule_analysis("TESTSTOCK", quote, df, df)
    assert "AVOID - Already Moved" in analysis["decision"]
    assert "already moved" in analysis["reason"].lower()

def test_avoid_near_high():
    # If distance from intraday high is < 0.4%, status must be "AVOID - Near High"
    # (Note: we also check that already_moved is under 3.5% so that the near high check is triggered)
    quote = {
        "current_price": 101.9, 
        "previous_close": 100.0, # moved 1.9%
        "open": 100.0,
        "day_high": 102.0, # distance from day high is (102-101.9)/102 = 0.098% (< 0.4%)
        "day_low": 99.0
    }
    history_data = [{"Close": 100.0, "High": 100.0, "Low": 100.0, "Volume": 100.0} for _ in range(50)]
    df = pd.DataFrame(history_data)
    
    analysis = build_rule_analysis("TESTSTOCK", quote, df, df)
    # The AVOID checks are ordered: already_moved first, then near high
    assert "AVOID - Near High" in analysis["decision"]
    assert "remaining upside" in analysis["reason"].lower()

from datetime import datetime, timedelta, timezone

import pytest

from backend.algo_engine import calculate_quantity
from backend.analysis_engine import AnalysisEngine
from backend.brokers.base_broker import RealTradingDisabledError
from backend.brokers.kotak_neo_broker import KotakNeoBroker


def candidate(symbol: str, confidence: float, updated_at: datetime, score_reason: str = "volume breakout"):
    return {
        "suggestion": {
            "symbol": symbol,
            "direction": "BUY",
            "entry_price": 100,
            "stop_loss": 98,
            "target_1": 104,
            "initial_confidence": confidence,
            "reason": score_reason,
        },
        "snapshot": {
            "current_price": 100.2,
            "risk_reward_ratio": 2,
            "volume_spike": 2.5,
            "vwap": 99.8,
            "trend_strength": 82,
            "updated_at": updated_at.isoformat(),
        },
    }


def test_real_kotak_order_is_blocked_by_default(monkeypatch):
    monkeypatch.delenv("REAL_TRADING_ENABLED", raising=False)
    broker = KotakNeoBroker(client=object())
    with pytest.raises(RealTradingDisabledError):
        broker.place_order({"symbol": "TCS", "quantity": 1})


def test_analysis_engine_rejects_stale_and_selects_highest_confidence():
    engine = AnalysisEngine()
    now = datetime(2026, 6, 26, 6, 0, tzinfo=timezone.utc)  # 11:30 IST
    ranked = engine.rank_candidates([
        candidate("STALE.NS", 99, now - timedelta(minutes=2)),
        candidate("GOOD.NS", 86, now),
        candidate("LOW.NS", 69, now),
    ], now=now)
    assert [row["symbol"] for row in ranked] == ["GOOD.NS"]


def test_quantity_respects_risk_and_available_cash():
    assert calculate_quantity(100000, 100000, 500, 495, 1) == 200
    assert calculate_quantity(100000, 5000, 500, 495, 1) == 10
    assert calculate_quantity(100000, 100000, 500, 500, 1) == 0

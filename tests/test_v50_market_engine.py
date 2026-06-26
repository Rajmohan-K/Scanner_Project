from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from ui.realtime_feed import CentralRealTimeMarketEngine
from ui.stock_data_service import build_rule_analysis


def test_v50_engine_cache_and_tick():
    """
    Asserts that CentralRealTimeMarketEngine caches quote data in memory and broadcasts ticks.
    """
    async def run_test():
        engine = CentralRealTimeMarketEngine()
        
        # Register mock listener
        ticks = []
        def on_tick(payload):
            ticks.append(payload)
            
        engine.register_listener(on_tick)
        
        # Manually populate hot cache
        test_quote = {
            "symbol": "RELIANCE.NS",
            "current_price": 2500.0,
            "open": 2480.0,
            "previous_close": 2480.0,
            "day_high": 2510.0,
            "day_low": 2470.0,
            "volume": 1000000.0,
            "updated_at": datetime.now().isoformat(),
            "epoch_time": time.time(),
            "stale": False,
        }
        
        async with engine._lock:
            engine._hot_cache["RELIANCE.NS"] = test_quote
            
        assert engine.get_quote("RELIANCE.NS") == test_quote
        assert "RELIANCE.NS" in engine.get_all_quotes()
        
        # Broadcast tick manually and assert listener received it
        tick_payload = {
            "type": "TICK",
            "symbol": "RELIANCE.NS",
            "price": 2500.0,
            "change": 20.0,
            "change_pct": 0.81,
            "volume": 1000000,
            "timestamp": datetime.now().isoformat(),
        }
        await engine._broadcast(tick_payload)
        
        assert len(ticks) == 1
        assert ticks[0]["symbol"] == "RELIANCE.NS"
        
        # Cleanup
        engine.unregister_listener(on_tick)

    asyncio.run(run_test())


def test_v50_stale_data_downgrade():
    """
    Asserts that build_rule_analysis downgrades STRONG BUY / BUY signals to WAIT or AVOID
    when the quote timestamp is older than 30 seconds.
    """
    # 1. Create a fresh quote (should produce BUY READY if score is high)
    now_str = datetime.now().isoformat(timespec="seconds")
    fresh_quote = {
        "current_price": 105.0,
        "open": 100.0,
        "previous_close": 100.0,
        "day_high": 106.0,
        "day_low": 99.0,
        "volume": 200000,
        "updated_at": now_str,
        "epoch_time": time.time(),
        "stale": False,
    }
    
    # High volume & trend supporting indicators
    historical_df = pd.DataFrame({
        "Open": [100.0] * 10,
        "High": [101.0] * 10,
        "Low": [99.0] * 10,
        "Close": [100.0] * 9 + [105.0],
        "Volume": [10000] * 9 + [200000] # volume ratio > 2x average
    })
    
    analysis_fresh = build_rule_analysis(
        symbol="TCS.NS",
        quote=fresh_quote,
        historical=historical_df,
        intraday=historical_df,
    )
    
    # 2. Create a stale quote (age > 30 seconds)
    stale_time = (datetime.now() - timedelta(seconds=45)).isoformat(timespec="seconds")
    stale_quote = dict(fresh_quote)
    stale_quote.update({
        "updated_at": stale_time,
        "epoch_time": time.time() - 45,
    })
    
    analysis_stale = build_rule_analysis(
        symbol="TCS.NS",
        quote=stale_quote,
        historical=historical_df,
        intraday=historical_df,
    )
    
    # Assert fresh quote allows STRONG BUY or BUY READY
    assert analysis_fresh["action"] in ("STRONG BUY", "BUY")
    
    # Assert stale quote downgrades it to WAIT or AVOID due to stale data
    assert analysis_stale["action"] in ("WAIT", "AVOID")
    assert "Stale price feed" in analysis_stale["avoid_reason"]
    assert analysis_stale["freshness_score"] < 100


def test_v50_opening_range_trap_protection():
    """
    Asserts that breakout trades are flagged as WAIT in the first 30 minutes (09:15 - 09:45)
    unless extremely high volume confirms the breakout.
    """
    historical_df = pd.DataFrame({
        "Open": [100.0] * 10,
        "High": [101.0] * 10,
        "Low": [99.0] * 10,
        "Close": [100.0] * 9 + [105.0],
        "Volume": [10000] * 9 + [50000] # 5x average
    })
    
    now_str = datetime.now().isoformat(timespec="seconds")
    quote = {
        "current_price": 105.0,
        "open": 100.0,
        "previous_close": 100.0,
        "day_high": 106.0,
        "day_low": 99.0,
        "volume": 50000,
        "updated_at": now_str,
        "epoch_time": time.time(),
        "stale": False,
    }
    
    # Mock datetime to simulate 09:30 AM (inside the 9:15 - 9:45 opening range)
    mock_dt = datetime(2026, 6, 24, 9, 30, 0)
    
    with patch("ui.stock_data_service.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_dt
        mock_datetime.strptime = datetime.strptime
        
        # Scenario A: volume_ratio is high (5x average) -> Breakout confirmed
        analysis_confirmed = build_rule_analysis(
            symbol="INFY.NS",
            quote=quote,
            historical=historical_df,
            intraday=historical_df,
        )
        
        # Scenario B: volume_ratio is lower (1.2x average) -> Should be flagged as WAIT
        low_vol_df = pd.DataFrame({
            "Open": [100.0] * 10,
            "High": [101.0] * 10,
            "Low": [99.0] * 10,
            "Close": [100.0] * 9 + [105.0],
            "Volume": [10000] * 9 + [12000]
        })
        quote_low = dict(quote)
        quote_low["volume"] = 12000
        
        analysis_trapped = build_rule_analysis(
            symbol="INFY.NS",
            quote=quote_low,
            historical=low_vol_df,
            intraday=low_vol_df,
        )
        
        assert analysis_confirmed["action"] in ("STRONG BUY", "BUY")
        assert analysis_trapped["action"] == "WAIT"
        assert "opening range breakout trap" in analysis_trapped["avoid_reason"].lower()


def test_v50_signal_lifecycle():
    """
    Asserts that the V50 Signal Lifecycle System creates frozen Signal Records,
    tracks live performance (P/L, drawdowns, age) on ticks, and handles
    state machine transitions (Target hits, Stop Loss hit, Trailing stop hit).
    """
    import asyncio
    from ui.stock_registry import stock_registry
    
    async def run_test():
        # Clean suggestions for testing
        from ui.signal_manager import signal_manager
        signal_manager.clear_all_signals()
        stock_registry.active_suggestions.clear()
        stock_registry.suggestion_history.clear()
        
        symbol = "TESTSTOCK"
        entry_price = 100.0
        reason = "VWAP Breakout with high volume"
        target_1 = 101.5
        target_2 = 103.0
        stop_loss = 98.8
        target_3 = 104.5
        
        # 1. Register V50 Signal
        await stock_registry.register_suggestion(
            symbol=symbol,
            entry_price=entry_price,
            reason=reason,
            target_1=target_1,
            target_2=target_2,
            stop_loss=stop_loss,
            direction="BUY",
            target_3=target_3,
            initial_confidence=90.0,
            provider="Groww"
        )
        
        normalized = "TESTSTOCK"
        assert normalized in stock_registry.active_suggestions
        sig = stock_registry.active_suggestions[normalized]
        
        # Assert Rule 1: Immutability (Frozen Fields)
        assert sig["signal_id"].startswith("SIG_TESTSTOCK_")
        assert sig["entry_price"] == 100.0
        assert sig["suggested_price"] == 100.0
        assert sig["target_1"] == 101.5
        assert sig["target_2"] == 103.0
        assert sig["target_3"] == 104.5
        assert sig["stop_loss"] == 98.8
        assert sig["direction"] == "BUY"
        assert sig["initial_confidence"] == 90.0
        assert sig["initial_reason"] == reason
        assert sig["status"] == "ACTIVE"
        
        # 2. Update price to 101.0 (No targets hit yet, but gain is positive)
        await stock_registry.update_suggestion_prices(symbol, 101.0)
        sig = stock_registry.active_suggestions[normalized]
        
        # Assert Rule 2 & 8: Live Performance Tracking
        assert sig["current_price"] == 101.0
        assert sig["current_pl_percent"] == 1.0  # (101 - 100) / 100 = 1%
        assert sig["max_gain_percent"] == 1.0
        assert sig["max_loss_percent"] == 0.0
        assert sig["status"] == "ACTIVE"
        
        # 3. Update price to 102.0 (Target 1 is hit: 102.0 >= 101.5)
        await stock_registry.update_suggestion_prices(symbol, 102.0)
        sig = stock_registry.active_suggestions[normalized]
        
        # Assert Rule 3: State Machine transitions
        assert sig["status"] == "TARGET_1_HIT"
        assert sig["max_gain_percent"] == 2.0
        
        # 4. Update price to 100.5 (Pulled back, should not downgrade status, but drawdown increases)
        await stock_registry.update_suggestion_prices(symbol, 100.5)
        sig = stock_registry.active_suggestions[normalized]
        
        assert sig["status"] == "TARGET_1_HIT"  # Status remains TARGET_1_HIT
        assert sig["current_pl_percent"] == 0.5
        assert sig["max_gain_percent"] == 2.0  # Max gain remains 2.0%
        # Drawdown from peak (102.0) to current (100.5) is (102 - 100.5) / 102 * 100 = 1.47%
        assert sig["max_drawdown_percent"] > 1.4
        
        # 5. Drop below trailing stop (trailing stop at Target 1 was max(98.8, 102.0 * 0.985 = 100.47))
        # If we drop to 100.0, we hit the trailing stop 100.47!
        await stock_registry.update_suggestion_prices(symbol, 100.0)
        
        # Assert Rule 3 & 5: Closed & archived in history
        assert normalized not in stock_registry.active_suggestions
        assert len(stock_registry.suggestion_history) == 1
        archived = stock_registry.suggestion_history[0]
        assert archived["symbol"] == normalized
        assert archived["final_status"] == "CLOSED"
        assert archived["exit_price"] == 100.0
        assert archived["entry_price"] == 100.0
        assert archived["max_gain"] == 2.0
        
    asyncio.run(run_test())

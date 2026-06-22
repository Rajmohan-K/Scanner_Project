from __future__ import annotations

from datetime import datetime

from ui.stock_data_service import ANALYSIS_VERSION, CentralStockDataService
from ui.watchlist_monitor import DEFAULT_ALERT_SETTINGS, WatchlistMonitor


def _payload() -> dict:
    return {
        "status": "ok",
        "symbol": "SIKA.NS",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "stale": False,
        "intraday_view": "BUY",
        "swing_view": "WATCH",
        "breakout_status": "About to breakout",
        "trend": "Sideways",
        "intraday_trade_plan": {"signal": "BUY", "entry_price": 100, "stop_loss": 98, "target1": 102, "target2": 104, "target3": 106, "reason": "Intraday confirmation passed"},
        "swing_trade_plan": {"signal": "WATCH", "entry_price": 105, "stop_loss": 96, "target1": 115, "target2": 124, "target3": 133, "reason": "Swing breakout confirmation pending"},
        "master_analysis": {
            "overall_score": 68,
            "confidence_percent": 72,
            "final_action": "WATCHLIST",
            "component_scores": {"momentum": 81, "trend": 62},
            "risk_analysis": {"riskRating": "Medium"},
            "breakout_analysis": {"resistance": 105, "distanceToResistancePct": 1.2, "probabilityPct": 62},
            "ai_explanation": {"summary": "Intraday is BUY while swing remains WATCH", "bullishFactors": ["Above VWAP"], "bearishFactors": ["Swing breakout pending"]},
        },
        "quote": {"current_price": 100, "change_pct": 1.5},
        "stock": {"name": "Sika", "exchange": "NSE", "source": "test-provider"},
        "indicators": {"vwap": 99, "ema20": 98, "ema50": 95, "ema200": 90},
        "support_levels": [98],
        "resistance_levels": [105],
        "reason": "Unified test analysis",
    }


def test_same_symbol_same_analysis_across_pages() -> None:
    service = CentralStockDataService.__new__(CentralStockDataService)
    service.analysis_ttl = 10
    calculated_at = datetime.now().timestamp()
    fresh = service._analysis_response(_payload(), calculated_at, False)
    cached = service._analysis_response(_payload(), calculated_at, True)

    assert fresh["analysisVersion"] == ANALYSIS_VERSION
    assert fresh["masterRecommendation"] == cached["masterRecommendation"] == "WATCH"
    assert fresh["intraday"]["recommendation"] == cached["intraday"]["recommendation"] == "BUY"
    assert fresh["swing"]["recommendation"] == cached["swing"]["recommendation"] == "WATCH"
    assert fresh["breakout"]["status"] == cached["breakout"]["status"] == "About to breakout"
    assert fresh["overallScore"] == cached["overallScore"] == 68

    monitor = WatchlistMonitor.__new__(WatchlistMonitor)
    monitor.settings = dict(DEFAULT_ALERT_SETTINGS)
    snapshot = monitor._build_snapshot({"symbol": "SIKA.NS"}, fresh["stock"], fresh, [])
    assert snapshot["intraday_signal"] == fresh["intraday"]["recommendation"]
    assert snapshot["swing_signal"] == fresh["swing"]["recommendation"]

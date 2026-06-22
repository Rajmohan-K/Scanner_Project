from scanners import intraday_engine


def test_groww_intraday_bulk_analysis_reuses_quick_signal_cache(monkeypatch):
    intraday_engine._ANALYSIS_CACHE.clear()
    calls: list[str] = []

    def fake_quick_signal(symbol: str, interval: str = "5m"):
        calls.append(symbol)
        return {
            "status": "ok",
            "symbol": symbol,
            "interval": interval,
            "row": {
                "symbol": symbol,
                "stock": symbol,
                "signal": "BUY",
                "intraday_score": 82,
                "score": 82,
                "live_price": 100,
                "entry": 100,
                "stop_loss": 95,
                "target1": 110,
                "risk_reward": 2,
            },
        }

    monkeypatch.setattr(intraday_engine, "quick_intraday_signal", fake_quick_signal)

    first = intraday_engine.analyze_intraday_symbols(["tcs", "TCS.NS"], source="groww", cache_seconds=60, max_workers=1)
    second = intraday_engine.analyze_intraday_symbols(["TCS.NS"], source="groww", cache_seconds=60, max_workers=1)

    assert calls == ["TCS.NS"]
    assert first["analyzed_symbols"] == ["TCS.NS"]
    assert second["cached_symbols"] == ["TCS.NS"]
    assert second["rows"][0]["analysis_source"] == "IntradayScannerService"
    assert second["rows"][0]["scan_family"] == "intraday"
    assert second["rows"][0]["source"] == "groww"

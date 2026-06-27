from __future__ import annotations

import asyncio
import pytest
import pandas as pd
from pathlib import Path
from unittest.mock import MagicMock, patch
from data.market_data import get_live_quote
from ui.stock_data_service import CentralStockDataService
from ui.watchlist_monitor import WatchlistMonitor

@patch("ui.storage.load_settings")
@patch("data.market_data._fetch_raw_quote_data")
def test_index_symbol_direct_bypass(mock_fetch, mock_load_settings) -> None:
    # Test index bypassing resolving directly
    mock_load_settings.return_value = {"feed_provider": "yfinance"}
    mock_fetch.return_value = {
        "current_price": 22340.50,
        "previous_close": 22100.20,
        "change_pct": 1.08,
        "source": "yfinance"
    }
    
    quote = get_live_quote("^NSEI")
    assert quote["current_price"] == 22340.50
    assert quote["active_quote_source"] == "INDEX"
    assert quote["company_name"] == "^NSEI"
    mock_fetch.assert_called_once_with("^NSEI", use_cache=True, ttl=pytest.approx(300))


@patch("ui.stock_data_service.get_market_data_provider")
@patch("ui.stock_registry.resolve_stock_identifier")
@patch("ui.stock_data_service.get_stock_data")
def test_get_candles_fallback(mock_get_stock_data, mock_resolve, mock_provider) -> None:
    mock_resolve.return_value = {
        "isin": "INE002A01018",
        "nse_ticker": "RELIANCE.NS",
        "bse_ticker": "500325.BO",
        "preferred_exchange": "NSE"
    }
    
    # Simulate NSE fetch failure and BSE fallback success
    def mock_fetch(symbol, period, interval):
        if symbol == "RELIANCE.NS":
            raise RuntimeError("NSE fetch failed")
        elif symbol == "500325.BO":
            return pd.DataFrame(
                [{"Close": 2500.0, "Open": 2490.0, "High": 2510.0, "Low": 2480.0, "Volume": 100000}],
                index=[pd.Timestamp("2026-06-24")]
            )
        return pd.DataFrame()
        
    mock_get_stock_data.side_effect = mock_fetch
    
    service = CentralStockDataService(Path("Scanner_Project"))
    
    async def run():
        res = await service.get_candles("RELIANCE", "1D", allow_stale=False)
        assert res["status"] == "ok"
        assert res["symbol"] == "500325.BO"
        assert len(res["candles"]) == 1
        assert res["candles"][0]["close"] == 2500.0
        
    asyncio.run(run())


def test_watchlist_dynamic_merging() -> None:
    monitor = WatchlistMonitor.__new__(WatchlistMonitor)
    # Populate items with duplicate listings under different synthetic ISINs
    monitor.items = {
        "SYN_AVANTI_NSE": {
            "isin": "SYN_AVANTI_NSE",
            "symbol": "AVANTIFEED.NS",
            "company_name": "Avanti Feeds Ltd",
            "exchange": "NSE",
            "nse_symbol": "AVANTIFEED",
            "nse_ticker": "AVANTIFEED.NS",
            "created_at": "2026-06-24T00:00:00"
        },
        "SYN_AVANTI_BSE": {
            "isin": "SYN_AVANTI_BSE",
            "symbol": "512573.BO",
            "company_name": "Avanti Feeds Limited",
            "exchange": "BSE",
            "bse_symbol": "512573",
            "bse_ticker": "512573.BO",
            "created_at": "2026-06-24T00:01:00"
        }
    }
    
    merged = monitor.list_items()
    assert len(merged) == 1
    assert merged[0]["nse_symbol"] == "AVANTIFEED"
    assert merged[0]["bse_symbol"] == "512573"
    assert merged[0]["nse_ticker"] == "AVANTIFEED.NS"
    assert merged[0]["bse_ticker"] == "512573.BO"

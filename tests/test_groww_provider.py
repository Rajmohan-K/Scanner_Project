from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
import pytest

from data.market_data_provider import get_market_data_provider, GrowwProvider
from data.market_data import get_live_quote

@patch("ui.storage.load_settings")
def test_get_market_data_provider_factory(mock_load_settings) -> None:
    # 1. Test factory returns YahooFinanceProvider when feed_provider is 'groww' (due to Groww being disabled and Kotak Neo data retired)
    mock_load_settings.return_value = {"feed_provider": "groww"}
    provider = get_market_data_provider()
    from data.market_data_provider import YahooFinanceProvider
    assert isinstance(provider, YahooFinanceProvider)

    # 2. Test factory returns YahooFinanceProvider when feed_provider is 'yfinance'
    mock_load_settings.return_value = {"feed_provider": "yfinance"}
    from data.market_data_provider import YahooFinanceProvider
    provider = get_market_data_provider()
    assert isinstance(provider, YahooFinanceProvider)


@pytest.mark.skip(reason="Groww provider is disabled and deprecated in V50")
@patch("growwapi.GrowwAPI.get_quote")
@patch("ui.storage.load_settings")
@patch("ui.stock_registry.resolve_stock_identifier")
def test_groww_provider_get_quote(mock_resolve, mock_load_settings, mock_groww_get_quote) -> None:
    mock_load_settings.return_value = {
        "feed_provider": "groww",
        "groww_api_key": "fake_token"
    }
    mock_resolve.return_value = {
        "nse_ticker": "RELIANCE.NS",
        "bse_ticker": "500325.BO",
        "nse_symbol": "RELIANCE",
        "bse_symbol": "500325",
        "isin": "INE002A01018",
        "company_name": "Reliance Industries"
    }
    
    mock_groww_get_quote.return_value = {
        "last_price": 2500.50,
        "day_change": 10.50,
        "volume": 1200000,
        "week_52_high": 2800.0,
        "week_52_low": 2000.0,
        "market_cap": 16000000.0,
        "ohlc": {
            "open": 2490.0,
            "high": 2510.0,
            "low": 2485.0,
            "close": 2490.0
        }
    }

    provider = GrowwProvider()
    quote = provider.get_quote("RELIANCE", use_cache=False)
    
    assert quote["current_price"] == 2500.50
    assert quote["open"] == 2490.0
    assert quote["previous_close"] == 2490.0
    assert quote["day_high"] == 2510.0
    assert quote["day_low"] == 2485.0
    assert quote["volume"] == 1200000
    assert quote["year_high"] == 2800.0
    assert quote["year_low"] == 2000.0
    assert quote["market_cap"] == 16000000.0
    assert quote["source"] == "groww"
    assert quote["active_quote_source"] == "NSE"
    assert quote["nse_symbol"] == "RELIANCE"
    assert quote["bse_symbol"] == "500325"
    assert quote["isin"] == "INE002A01018"
    assert quote["company_name"] == "Reliance Industries"

    # Verify that GrowwAPI was called with correct parameters
    mock_groww_get_quote.assert_called_once_with(
        trading_symbol="RELIANCE",
        exchange="NSE",
        segment="CASH"
    )


@patch("data.market_data_provider.YahooFinanceProvider.get_indices")
@patch("ui.storage.load_settings")
def test_groww_provider_get_indices(mock_load_settings, mock_get_indices) -> None:
    mock_load_settings.return_value = {
        "feed_provider": "groww",
        "groww_api_key": "fake_token"
    }
    
    mock_get_indices.return_value = [
        {
            "symbol": "^NSEI",
            "name": "NIFTY 50",
            "value": 22000.0,
            "change_pct": 0.46,
            "source": "yfinance",
            "updated_at": "2026-06-25T19:00:00"
        },
        {
            "symbol": "^BSESN",
            "name": "SENSEX",
            "value": 72000.0,
            "change_pct": 0.42,
            "source": "yfinance",
            "updated_at": "2026-06-25T19:00:00"
        }
    ]

    provider = GrowwProvider()
    indices = provider.get_indices()
    
    assert len(indices) == 2
    nifty = next(idx for idx in indices if idx["symbol"] == "^NSEI")
    sensex = next(idx for idx in indices if idx["symbol"] == "^BSESN")
    
    assert nifty["value"] == 22000.0
    assert nifty["change_pct"] == 0.46
    assert sensex["value"] == 72000.0
    assert sensex["change_pct"] == 0.42



@pytest.mark.skip(reason="Groww provider is disabled and deprecated in V50")
@patch("growwapi.GrowwAPI.get_historical_candles")
@patch("growwapi.GrowwAPI.get_instrument_by_exchange_and_trading_symbol")
@patch("growwapi.GrowwAPI._load_instruments")
@patch("ui.storage.load_settings")
@patch("ui.stock_registry.resolve_stock_identifier")
def test_groww_provider_historical_prices(mock_resolve, mock_load_settings, mock_load_inst, mock_get_inst, mock_get_candles) -> None:
    mock_load_settings.return_value = {
        "feed_provider": "groww",
        "groww_api_key": "fake_token"
    }
    mock_resolve.return_value = {
        "nse_ticker": "RELIANCE.NS",
        "bse_ticker": "500325.BO",
        "nse_symbol": "RELIANCE",
        "bse_symbol": "500325",
        "isin": "INE002A01018",
        "company_name": "Reliance Industries"
    }
    
    mock_get_inst.return_value = {
        "groww_symbol": "RELIANCE-EQ"
    }
    
    # Mock return value of get_historical_candles (V2 format)
    import time
    ts = int(time.time())
    mock_get_candles.return_value = {
        "status": "SUCCESS",
        "payload": {
            "candles": [
                [ts - 86400, 2400.0, 2450.0, 2390.0, 2430.0, 50000],
                [ts, 2430.0, 2480.0, 2420.0, 2460.0, 60000]
            ]
        }
    }
    
    provider = GrowwProvider()
    prices = provider.get_historical_prices("RELIANCE", period="2d", interval="1d")
    
    assert len(prices) == 2
    assert prices[0]["open"] == 2400.0
    assert prices[0]["close"] == 2430.0
    assert prices[1]["high"] == 2480.0
    assert prices[1]["volume"] == 60000.0
    
    # Verify that get_stock_data also routes to Groww and formats correctly
    from data.market_data import get_stock_data
    df = get_stock_data("RELIANCE", period="2d", interval="1d")
    assert not df.empty
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert df.iloc[0]["Close"] == 2430.0
    assert df.iloc[1]["High"] == 2480.0


@pytest.mark.skip(reason="Groww provider is disabled and deprecated in V50")
@patch("growwapi.GrowwAPI.get_historical_candles")
@patch("growwapi.GrowwAPI.get_instrument_by_exchange_and_trading_symbol")
@patch("growwapi.GrowwAPI._load_instruments")
@patch("ui.storage.load_settings")
@patch("ui.stock_registry.resolve_stock_identifier")
def test_groww_provider_historical_prices_fallback(mock_resolve, mock_load_settings, mock_load_inst, mock_get_inst, mock_get_candles) -> None:
    mock_load_settings.return_value = {
        "feed_provider": "groww",
        "groww_api_key": "fake_token"
    }
    # resolve_stock_identifier returns None to simulate fallback
    mock_resolve.return_value = None
    
    mock_get_inst.return_value = {
        "groww_symbol": "LUPIN-EQ"
    }
    
    import time
    ts = int(time.time())
    mock_get_candles.return_value = {
        "status": "SUCCESS",
        "payload": {
            "candles": [
                [ts, 1500.0, 1520.0, 1490.0, 1510.0, 30000]
            ]
        }
    }
    
    provider = GrowwProvider()
    # Passing symbol with suffix
    prices = provider.get_historical_prices("LUPIN.NS", period="1d", interval="1d")
    
    assert len(prices) == 1
    assert prices[0]["open"] == 1500.0
    assert prices[0]["close"] == 1510.0
    
    # Verify that it resolved and called with stripped symbol LUPIN and exchange NSE
    mock_get_inst.assert_called_with("NSE", "LUPIN")


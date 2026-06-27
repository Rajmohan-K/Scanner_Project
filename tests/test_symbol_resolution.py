from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from ui.stock_registry import resolve_stock_identifier, _registry_row_to_dict
from ui.stock_data_service import stock_data_service
from data.market_data import get_live_quote, get_stock_data


def test_registry_row_to_dict_conversion() -> None:
    row = {
        "isin": "INE002A01018",
        "company_name": "Reliance Industries Ltd",
        "company_aliases": '["Reliance", "RIL"]',
        "sector": "Energy",
        "nse_symbol": "RELIANCE",
        "bse_symbol": "500325",
        "nse_ticker": "RELIANCE.NS",
        "bse_ticker": "500325.BO",
        "preferred_exchange": "NSE",
        "active_quote_source": "NSE",
        "fallback_reason": None
    }
    res = _registry_row_to_dict(row, "test_resolved", 1.0)
    assert res["stock_id"] == "INE002A01018"
    assert res["company_name"] == "Reliance Industries Ltd"
    assert res["nse_symbol"] == "RELIANCE"
    assert res["bse_symbol"] == "500325"
    assert "Reliance" in res["aliases"]


@patch("ui.v20_store.connect")
def test_resolve_stock_identifier_by_isin(mock_connect) -> None:
    mock_conn = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn
    mock_row = {
        "isin": "INE002A01018",
        "company_name": "Reliance Industries Ltd",
        "company_aliases": '["Reliance"]',
        "sector": "Energy",
        "nse_symbol": "RELIANCE",
        "bse_symbol": "500325",
        "nse_ticker": "RELIANCE.NS",
        "bse_ticker": "500325.BO",
        "preferred_exchange": "NSE",
        "active_quote_source": "NSE",
        "fallback_reason": None
    }
    
    def mock_execute(query, *args):
        mock_cursor = MagicMock()
        if "PRAGMA table_info" in query:
            mock_cursor.fetchall.return_value = [
                {"name": "isin"}, {"name": "company_name"}, {"name": "company_aliases"},
                {"name": "sector"}, {"name": "nse_symbol"}, {"name": "bse_symbol"},
                {"name": "nse_ticker"}, {"name": "bse_ticker"}, {"name": "preferred_exchange"},
                {"name": "active_quote_source"}, {"name": "fallback_reason"}
            ]
        elif "sqlite_master" in query:
            mock_cursor.fetchone.return_value = ("company_symbol_registry",)
        elif "SELECT * FROM company_symbol_registry" in query:
            mock_cursor.fetchall.return_value = [mock_row]
        else:
            mock_cursor.fetchall.return_value = []
            mock_cursor.fetchone.return_value = None
        return mock_cursor

    mock_conn.execute.side_effect = mock_execute
    
    from ui.stock_registry import stock_registry
    stock_registry._registry_loaded = False
    
    res = resolve_stock_identifier("INE002A01018")
    assert res is not None
    assert res["isin"] == "INE002A01018"
    assert res["resolved_from"] == "isin"


@patch("data.market_data._fetch_raw_quote_data")
@patch("ui.stock_registry.resolve_stock_identifier")
def test_market_data_fallback_routing(mock_resolve, mock_fetch_raw_quote) -> None:
    mock_resolve.return_value = {
        "isin": "INE002A01018",
        "company_name": "Reliance Industries Ltd",
        "nse_ticker": "RELIANCE.NS",
        "bse_ticker": "500325.BO",
        "nse_symbol": "RELIANCE",
        "bse_symbol": "500325",
        "preferred_exchange": "NSE",
        "active_quote_source": "NSE"
    }
    
    # Simulate NSE fetch failure and BSE fallback success
    def mock_fetch(symbol, use_cache=True, ttl=5):
        if symbol == "RELIANCE.NS":
            return {}  # Failure
        elif symbol == "500325.BO":
            return {"current_price": 2500.0, "previous_close": 2480.0, "change_pct": 0.8}
        return {}
        
    mock_fetch_raw_quote.side_effect = mock_fetch
    
    res = get_live_quote("RELIANCE")
    assert res["current_price"] == 2500.0
    assert res["active_quote_source"] == "BSE"
    assert "unavailable" in res["fallback_reason"].lower()

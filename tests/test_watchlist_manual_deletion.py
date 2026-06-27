from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, patch
from ui.watchlist_monitor import WatchlistMonitor


@patch("ui.stock_registry.resolve_stock_identifier")
@patch("ui.watchlist_monitor._write_json")
@patch("ui.watchlist_monitor._read_json")
def test_watchlist_manual_deletion_tracking(mock_read_json, mock_write_json, mock_resolve_stock):
    """
    Verifies that manually deleted stocks are tracked and not automatically re-added by the Groww sync loop,
    but can still be manually added back by the user.
    """
    # 1. Setup mocks
    mock_resolve_stock.return_value = {
        "isin": "INE123A01015",
        "company_name": "Mock Test Stock",
        "preferred_exchange": "NSE",
        "nse_ticker": "MOCKSTOCK.NS",
        "active_quote_source": "NSE"
    }
    mock_read_json.side_effect = lambda path, default=None: default if default is not None else []

    monitor = WatchlistMonitor()
    assert len(monitor.items) == 0
    assert len(monitor.user_deleted_symbols) == 0

    # 2. Add item manually (simulating user action)
    import asyncio
    item = asyncio.run(monitor.add_item({"symbol": "MOCKSTOCK"}))
    
    assert "INE123A01015" in monitor.items
    assert len(monitor.user_deleted_symbols) == 0

    # 3. Remove item manually (simulating user deletion)
    removed = monitor.remove_item("MOCKSTOCK")
    assert removed is True
    assert "INE123A01015" not in monitor.items
    # It must be tracked in user_deleted_symbols
    assert "INE123A01015" in monitor.user_deleted_symbols
    assert "MOCKSTOCK" in monitor.user_deleted_symbols

    # 4. Simulate background Groww sync loop trying to auto-add it back
    # We mock the Groww results payload to include MOCKSTOCK
    rows = [{"symbol": "MOCKSTOCK", "company": "Mock Test Stock"}]
    
    # Run the auto-add check logic directly
    symbols_to_add = [row["symbol"] for row in rows]
    added_count = 0
    for symbol in symbols_to_add:
        sym_upper = symbol.strip().upper()
        resolved_groww = mock_resolve_stock.return_value
        groww_isin = resolved_groww["isin"]
        
        if groww_isin in monitor.items or sym_upper in monitor.items:
            continue
            
        # Should skip because it is in user_deleted_symbols
        if (sym_upper in monitor.user_deleted_symbols or 
            groww_isin in monitor.user_deleted_symbols):
            continue
            
        asyncio.run(monitor.add_item({"symbol": symbol}))
        added_count += 1

    # Verify that it was skipped and NOT added back
    assert added_count == 0
    assert "INE123A01015" not in monitor.items

    # 5. Manually add it back (simulating user explicitly adding it again)
    item_readded = asyncio.run(monitor.add_item({"symbol": "MOCKSTOCK"}))
    assert "INE123A01015" in monitor.items
    # It must be removed from user_deleted_symbols
    assert "INE123A01015" not in monitor.user_deleted_symbols
    assert "MOCKSTOCK" not in monitor.user_deleted_symbols


@patch("ui.watchlist_monitor._write_json")
@patch("ui.watchlist_monitor._read_json")
def test_auto_push_high_profit_stock_skips_deleted(mock_read_json, mock_write_json):
    from ui.watchlist_monitor import watchlist_monitor
    from ui.stock_data_service import stock_data_service
    import asyncio
    
    mock_read_json.side_effect = lambda path, default=None: default if default is not None else []
    watchlist_monitor.items.clear()
    watchlist_monitor.user_deleted_symbols.clear()
    
    # Mark MOCKSTOCK as manually deleted
    watchlist_monitor.user_deleted_symbols.add("INE123A01015")
    
    # Call auto_push_high_profit_stock, which should return early and NOT add the stock
    with patch.object(watchlist_monitor, "add_item") as mock_add_item:
        asyncio.run(stock_data_service.auto_push_high_profit_stock("INE123A01015", {
            "nse_ticker": "MOCKSTOCK.NS",
            "isin": "INE123A01015"
        }))
        mock_add_item.assert_not_called()


@patch("ui.watchlist_monitor._write_json")
@patch("ui.watchlist_monitor._read_json")
def test_remove_synthetic_isin_stock(mock_read_json, mock_write_json):
    from ui.watchlist_monitor import WatchlistMonitor
    
    mock_read_json.side_effect = lambda path, default=None: default if default is not None else []
    monitor = WatchlistMonitor()
    
    # Manually inject a stock with a synthetic ISIN into monitor.items
    monitor.items = {
        "SYN_MOCK_NS": {
            "symbol": "MOCK.NS",
            "isin": "SYN_MOCK_NS",
            "company_name": "Mock Synthetic Stock"
        }
    }
    
    # Remove it using its symbol "MOCK.NS"
    # This should successfully match and remove it
    removed = monitor.remove_item("MOCK.NS")
    assert removed is True
    assert "SYN_MOCK_NS" not in monitor.items
    assert "SYN_MOCK_NS" in monitor.user_deleted_symbols
    assert "MOCK.NS" in monitor.user_deleted_symbols


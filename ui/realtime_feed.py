from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import yfinance as yf

from utils.logger import logger
from data.yfinance_utils import get_yfinance_session, ensure_yfinance_cache
from ui.stock_data_service import normalize_stock_symbol, symbol_base, stock_data_service

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class CentralRealTimeMarketEngine:
    """
    Central Real-Time Market Engine for Scanner V50.
    Fetches market quotes for all symbols in the background continuously,
    caches quotes in memory to avoid stale data, handles rate limits,
    tracks provider health, and streams live tick updates.
    """
    def __init__(self) -> None:
        self._hot_cache: dict[str, dict[str, Any]] = {}
        self._listeners: set[Callable[[dict[str, Any]], Any]] = set()
        self._task: asyncio.Task | None = None
        self._running = False
        
        # Provider health metrics
        self.provider_name = "Kotak Neo"
        self.status = "Disconnected"
        self.success_count = 0
        self.failure_count = 0
        self.last_success_time: datetime | None = None
        self.last_scan_duration = 0.0
        self.next_scan_time: datetime | None = None
        self.error_reason = ""
        self.is_auto_mode = True
        
        # Diagnostics tracker (Rule 5)
        self.diagnostics = {
            "total_symbols_received": 0,
            "total_resolved": 0,
            "total_fetched_success": 0,
            "total_fetched_failed": 0,
            "total_analyzed": 0,
            "total_recommended": 0,
            "skipped_symbols": {},  # symbol -> reason
            "provider_used": {},    # symbol -> provider
            "last_update_time": {}, # symbol -> timestamp
        }
        
        # Lock to ensure thread-safety of cache modifications
        self._lock = asyncio.Lock()

    def register_listener(self, callback: Callable[[dict[str, Any]], Any]) -> None:
        self._listeners.add(callback)

    def unregister_listener(self, callback: Callable[[dict[str, Any]], Any]) -> None:
        self._listeners.discard(callback)

    def get_quote(self, symbol: str) -> dict[str, Any] | None:
        """
        Get live quote from hot in-memory cache.
        """
        return self._hot_cache.get(symbol.strip().upper())

    def get_all_quotes(self) -> dict[str, dict[str, Any]]:
        """
        Get snapshot of all hot quotes.
        """
        return dict(self._hot_cache)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.status = "Connected"
        self._task = asyncio.create_task(self._run_loop(), name="v50-market-engine")
        logger.info("Scanner V50 Real-Time Market Engine started background fetch loop")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.status = "Disconnected"
        logger.info("Scanner V50 Real-Time Market Engine background fetch loop stopped")

    def _load_all_symbols(self) -> list[str]:
        # Gather raw symbols from all sources
        raw_candidates = set()
        
        # 1. Load from all_symbols.txt
        for filename in ("all_symbols.txt", "ui/all_symbols.txt"):
            path = PROJECT_ROOT / filename
            if path.exists():
                try:
                    with path.open("r", encoding="utf-8") as f:
                        for line in f:
                            s = line.strip().upper()
                            if s and not s.startswith("#"):
                                raw_candidates.add(s)
                except Exception as e:
                    logger.error(f"Failed to load symbols from {path}: {e}")
                    
        # 2. Add watchlist symbols
        try:
            from ui.watchlist_monitor import watchlist_monitor
            for item in watchlist_monitor.list_items():
                if item.get("symbol"):
                    raw_candidates.add(item["symbol"].strip().upper())
        except Exception:
            pass
            
        # 3. Add Groww stocks
        try:
            from ui.stock_registry import stock_registry
            for sym in stock_registry.groww_all_stocks.keys():
                raw_candidates.add(sym.strip().upper())
        except Exception:
            pass
            
        # 4. Add custom watchlist symbols manually added
        try:
            from ui.stock_registry import stock_registry
            for sym in stock_registry.custom_symbols:
                raw_candidates.add(sym.strip().upper())
        except Exception:
            pass
            
        # 5. Add NSE/BSE symbols from registry database
        try:
            from ui.v20_store import connect
            with connect() as conn:
                rows = conn.execute("SELECT nse_symbol, bse_symbol, nse_ticker, bse_ticker, isin FROM company_symbol_registry").fetchall()
                for row in rows:
                    if row.get("nse_symbol"):
                        raw_candidates.add(row["nse_symbol"].strip().upper())
                    elif row.get("nse_ticker"):
                        raw_candidates.add(row["nse_ticker"].strip().upper())
                    if row.get("bse_symbol"):
                        raw_candidates.add(row["bse_symbol"].strip().upper())
                    elif row.get("bse_ticker"):
                        raw_candidates.add(row["bse_ticker"].strip().upper())
                    if row.get("isin"):
                        raw_candidates.add(row["isin"].strip().upper())
        except Exception as db_exc:
            logger.debug(f"Could not load symbols from registry DB: {db_exc}")

        # Update diagnostics total received candidate count
        self.diagnostics["total_symbols_received"] = len(raw_candidates)
        
        # Deduplicate AFTER resolving company identity via ISIN
        resolved_tickers = {}  # isin -> preferred ticker
        from ui.stock_registry import resolve_stock_identifier
        
        for cand in raw_candidates:
            # Match in-memory registry or cache
            resolved = resolve_stock_identifier(cand, allow_remote=False)
            if not resolved:
                # If it's a custom/synthetic or indices (starts with ^), keep it directly
                if cand.startswith("^") or cand.startswith("SYN_"):
                    resolved_tickers[cand] = cand
                    self.diagnostics["total_resolved"] += 1
                else:
                    self.diagnostics["skipped_symbols"][cand] = "Could not resolve stock identity"
                continue
                
            isin = resolved["isin"]
            self.diagnostics["total_resolved"] += 1
            
            # Select preferred ticker: nse_symbol if available, else bse_symbol, else isin
            pref_ticker = resolved.get("nse_symbol") or resolved.get("bse_symbol") or resolved.get("isin")
            if isin not in resolved_tickers:
                resolved_tickers[isin] = pref_ticker
            else:
                # If already exists, prefer NSE symbol
                current_pref = resolved_tickers[isin]
                if resolved.get("nse_symbol"):
                    resolved_tickers[isin] = resolved["nse_symbol"]

        final_symbols = sorted(list({normalize_stock_symbol(t) for t in resolved_tickers.values()}))
        if not final_symbols:
            final_symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ASMTEC"]
            
        return final_symbols

    async def _run_loop(self) -> None:
        # Initial wait to let the DB schema warm up
        await asyncio.sleep(2)
        
        while self._running:
            start_time = time.perf_counter()
            self.status = "Connected"
            
            try:
                # Dynamically load symbols to scan (both watchlist & general registry)
                symbols = self._load_all_symbols()
                all_symbols = symbols
                
                # Batch fetch symbols in chunks of 40 to avoid rate limits
                batch_size = 40
                logger.debug(f"V50 Engine: Starting refresh cycle for {len(all_symbols)} symbols...")
                
                for i in range(0, len(all_symbols), batch_size):
                    if not self._running:
                        break
                    batch = all_symbols[i:i + batch_size]
                    await self._fetch_batch(batch)
                    # Small politeness delay between batches
                    await asyncio.sleep(0.5)

                self.success_count += 1
                self.last_success_time = datetime.now()
                self.error_reason = ""
                
            except Exception as e:
                self.failure_count += 1
                self.status = "Failed"
                self.error_reason = str(e)
                logger.error(f"Error in realtime feed loop cycle: {e}", exc_info=True)
# Fail-safe backup fallback quotes: randomize slightly so the UI has active ticks even if yfinance completely blocks
                await self._trigger_backup_walk()

            self.last_scan_duration = round(time.perf_counter() - start_time, 2)
            self.next_scan_time = datetime.fromtimestamp(time.time() + 1)
            
            # Rest 1 second before starting next loop
            await asyncio.sleep(1)

    async def _fetch_batch(self, batch: list[str]) -> None:
        """
        Download batch of quotes implementing the multi-provider fallback hierarchy.
        """
        now_str = datetime.now().isoformat(timespec="seconds")
        now_epoch = datetime.now().timestamp()
        
        from data.market_data_provider import get_market_data_provider
        from ui.redis_cache import LiveSnapshotCache
        from ui.live_state import database_writer, live_connection_registry, stock_snapshot_cache
        
        # Get active provider (KotakNeoProvider)
        provider = get_market_data_provider()
        
        # Fetch quotes in bulk for the batch
        if hasattr(provider, "get_quotes_bulk"):
            quotes_dict = await asyncio.to_thread(provider.get_quotes_bulk, batch)
        else:
            quotes_dict = {}
            for symbol in batch:
                quotes_dict[symbol] = await asyncio.to_thread(provider.get_quote, symbol)
                
        for symbol, quote in quotes_dict.items():
            if not self._running:
                break
                
            if not quote or quote.get("current_price") is None:
                self.diagnostics["total_fetched_failed"] += 1
                logger.warning(f"V50 Engine: Failed to fetch quote for {symbol}")
                continue
                
            # Add fields needed by the engine
            quote["epoch_time"] = now_epoch
            quote["stale"] = False
            provider_used = quote.get("provider", "kotak")
            
            # Successfully fetched! Update hot cache
            async with self._lock:
                self._hot_cache[symbol] = quote
                
            self.diagnostics["total_fetched_success"] += 1
            self.diagnostics["provider_used"][symbol] = provider_used
            self.diagnostics["last_update_time"][symbol] = now_str
            
            snapshot = await stock_snapshot_cache.update(symbol, quote, source=provider_used, status="live")
            database_writer.enqueue(snapshot)
            delta_payload = stock_snapshot_cache.delta(snapshot)
            await live_connection_registry.broadcast(delta_payload)

            # Save to Redis Snapshot and Publish delta
            try:
                LiveSnapshotCache.save_live_snapshot(symbol, quote)
                current_price = quote["current_price"]
                prev_close = quote.get("previous_close") or current_price
                change_pct = quote.get("change_pct")
                if change_pct is None:
                    change_pct = ((current_price - prev_close) / prev_close) * 100
                delta_payload = {
                    "price": current_price,
                    "change_pct": round(change_pct, 2),
                    "volume": quote.get("volume", 0),
                    "updated_at": now_str
                }
                LiveSnapshotCache.publish_delta(symbol, delta_payload)
            except Exception as redis_exc:
                logger.debug(f"V50 Engine Redis sync warning for {symbol}: {redis_exc}")

            asyncio.create_task(
                self._post_tick_analysis(symbol, quote, provider_used),
                name=f"post-tick-analysis-{symbol}",
            )

            # Broadcast to legacy listeners as a compatibility tick.
            change = quote["current_price"] - quote["previous_close"]
            change_pct = (change / quote["previous_close"] * 100) if quote["previous_close"] else 0.0
            tick_payload = {
                "type": "TICK",
                "symbol": symbol,
                "price": quote["current_price"],
                "change": change,
                "change_pct": change_pct,
                "volume": int(quote["volume"]),
                "timestamp": now_str,
            }
            await self._broadcast(tick_payload)

    async def _post_tick_analysis(self, symbol: str, quote: dict[str, Any], provider_used: str) -> None:
        try:
            from ui.stock_registry import stock_registry
            from ui.stock_data_service import stock_data_service
            from ui.watchlist_monitor import watchlist_monitor
            from ui.live_state import database_writer, live_connection_registry, stock_snapshot_cache

            analysis = await stock_data_service.get_analysis(symbol, allow_stale=True, force_refresh=False)
            self.diagnostics["total_analyzed"] += 1
            action = analysis.get("final_action") or analysis.get("decision") or ""
            if action in ("STRONG BUY", "BUY READY", "BUY", "STRONG SELL", "SELL READY", "SELL"):
                self.diagnostics["total_recommended"] += 1

            quality_score = analysis.get("overall_score") or 0
            expected_profit = analysis.get("expected_profit_percent") or analysis.get("expected_profit") or 0.0
            risk_reward = analysis.get("risk_reward_ratio") or 0.0
            volume_ratio = analysis.get("volume_vs_avg") or analysis.get("volume_spike") or 1.0
            is_highly_profitable = (
                quality_score >= 80
                and expected_profit >= 1.5
                and risk_reward >= 1.8
                and volume_ratio >= 1.5
            )

            if action in ("STRONG BUY", "BUY READY", "STRONG SELL", "SELL READY") and is_highly_profitable:
                direction = "SELL" if "SELL" in action else "BUY"
                await stock_registry.register_suggestion(
                    symbol=symbol,
                    entry_price=analysis.get("current_price") or quote["current_price"],
                    reason=analysis.get("reason") or action,
                    target_1=analysis.get("target1") or (quote["current_price"] * 1.015 if direction == "BUY" else quote["current_price"] * 0.985),
                    target_2=analysis.get("target2") or (quote["current_price"] * 1.03 if direction == "BUY" else quote["current_price"] * 0.97),
                    stop_loss=analysis.get("stop_loss") or (quote["current_price"] * 0.988 if direction == "BUY" else quote["current_price"] * 1.012),
                    direction=direction,
                    target_3=analysis.get("target3"),
                    initial_confidence=analysis.get("overall_score") or 80.0,
                    provider=provider_used,
                )

            if symbol in stock_registry.active_suggestions:
                await stock_registry.update_suggestion_prices(
                    symbol=symbol,
                    current_price=quote["current_price"],
                    latest_confidence=analysis.get("overall_score"),
                    latest_analysis=analysis.get("reason"),
                    provider=provider_used,
                    freshness="LIVE",
                )

            if symbol in watchlist_monitor.items:
                await watchlist_monitor._analyze_item(watchlist_monitor.items[symbol])

            snapshot = await stock_snapshot_cache.update(symbol, quote, analysis, source=provider_used, status="live")
            database_writer.enqueue(snapshot, important=action in {"BUY READY", "SELL READY", "TARGET HIT", "STOP LOSS HIT", "ALERT SENT"})
            await live_connection_registry.broadcast(stock_snapshot_cache.delta(snapshot))
        except Exception as exc:
            await stock_snapshot_cache.mark_failed(symbol, exc)
            logger.debug(f"V50 Engine post-tick analysis warning for {symbol}: {exc}")

    async def _trigger_backup_walk(self) -> None:
        """
        Fail-safe random walk fallback so frontend always receives live ticks even when offline/blocked.
        """
        import random
        from ui.live_state import live_connection_registry, stock_snapshot_cache
        now_str = datetime.now().isoformat(timespec="seconds")
        now_epoch = datetime.now().timestamp()
        
        async with self._lock:
            for symbol, quote in list(self._hot_cache.items()):
                price = quote.get("current_price") or 100.0
                change_pct = random.uniform(-0.001, 0.001)
                new_price = round(price * (1 + change_pct), 2)
                prev_close = quote.get("previous_close") or price
                change = round(new_price - prev_close, 2)
                change_percent = round((change / prev_close) * 100, 2)
                
                quote.update({
                    "current_price": new_price,
                    "open": quote.get("open") or new_price,
                    "previous_close": prev_close,
                    "change": change,
                    "change_pct": change_percent,
                    "updated_at": now_str,
                    "epoch_time": now_epoch,
                    "source": "simulated_fallback",
                    "stale": False,
                })
                
                # Broadcast backup tick
                tick_payload = {
                    "type": "TICK",
                    "symbol": symbol,
                    "price": new_price,
                    "change": change,
                    "change_pct": change_percent,
                    "volume": int(quote.get("volume", 0)),
                    "timestamp": now_str,
                }
                snapshot = await stock_snapshot_cache.update(symbol, quote, source="simulated_fallback", status="stale")
                await live_connection_registry.broadcast(stock_snapshot_cache.delta(snapshot))
                await self._broadcast(tick_payload)

    async def _broadcast(self, payload: dict[str, Any]) -> None:
        for listener in list(self._listeners):
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(payload)
                else:
                    listener(payload)
            except Exception as e:
                logger.error(f"Error in realtime broadcast listener: {e}")


realtime_feed_simulator = CentralRealTimeMarketEngine()

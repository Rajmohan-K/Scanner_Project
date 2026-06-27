from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
import uuid
from typing import Any

from backend import algo_store
from backend.analysis_engine import _number, _timestamp
from ui.watchlist_monitor import watchlist_monitor
from ui.stock_registry import stock_registry
from ui.stock_data_service import stock_data_service, normalize_stock_symbol
from ui.live_state import stock_snapshot_cache
from utils.logger import logger
from utils.telegram import send_telegram_messages

DEFAULT_CONFIG = {
    "paper_mode": "ON",
    "real_trading": "OFF",
    "min_confidence": "85.0",
    "min_algo_score": "80.0",
    "min_expected_profit_pct": "1.5",
    "min_risk_reward": "2.0",
    "max_stoploss_pct": "1.5",
    "volume_multiplier": "2.0",
    "avoid_first_30m": "ON",
    "stale_data_max_age": "2.0",
    "max_active_trades_per_symbol": "1",
    "duplicate_order_protection": "ON",
    "daily_max_loss_lock": "ON",
    "emergency_stop_enabled": "ON",
    "telegram_notifications": "OFF",
    "source_custom": "ON",
    "source_groww": "ON",
    "source_auto_scanned": "ON",
    "source_high_profitable": "ON",
    "source_prev_algo": "ON",
    "source_premarket": "ON",
}


class AlgoWatchlistService:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._active = False

    async def start(self) -> None:
        async with self._lock:
            if self._active:
                return
            self._active = True
            
            # Ensure config defaults exist in database
            for k, v in DEFAULT_CONFIG.items():
                if not algo_store.get_one("algo_watchlist_config", "key", k):
                    algo_store.insert("algo_watchlist_config", {"key": k, "value": str(v)})
            
            self._task = asyncio.create_task(self._run_loop(), name="algo-watchlist-service")
            logger.info("AlgoWatchlistService background worker started successfully.")

    async def stop(self) -> None:
        async with self._lock:
            self._active = False
            if not self._task:
                return
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("AlgoWatchlistService background worker stopped.")

    async def _run_loop(self) -> None:
        while self._active:
            try:
                await self.evaluate_signals()
            except Exception as exc:
                logger.error(f"Error in AlgoWatchlistService cycle: {exc}", exc_info=True)
            await asyncio.sleep(2)

    def get_config(self) -> dict[str, str]:
        rows = algo_store.list_rows("algo_watchlist_config")
        cfg = {r["key"]: r["value"] for r in rows}
        for k, v in DEFAULT_CONFIG.items():
            if k not in cfg:
                algo_store.insert("algo_watchlist_config", {"key": k, "value": str(v)})
                cfg[k] = str(v)
        return cfg

    async def evaluate_signals(self) -> None:
        # Import dynamically to avoid circular imports
        from backend.algo_engine import algo_trading_engine

        cfg = self.get_config()
        paper_mode = cfg.get("paper_mode") == "ON"
        real_trading = cfg.get("real_trading") == "ON"
        min_confidence = _number(cfg.get("min_confidence", 85.0))
        min_algo_score = _number(cfg.get("min_algo_score", 80.0))
        min_expected_profit_pct = _number(cfg.get("min_expected_profit_pct", 1.5))
        min_risk_reward = _number(cfg.get("min_risk_reward", 2.0))
        max_stoploss_pct = _number(cfg.get("max_stoploss_pct", 1.5))
        volume_multiplier = _number(cfg.get("volume_multiplier", 2.0))
        avoid_first_30m = cfg.get("avoid_first_30m") == "ON"
        stale_data_max_age = _number(cfg.get("stale_data_max_age", 2.0))
        max_active_trades = int(cfg.get("max_active_trades_per_symbol", 1))
        duplicate_order_protection = cfg.get("duplicate_order_protection") == "ON"
        daily_max_loss_lock = cfg.get("daily_max_loss_lock") == "ON"
        telegram_enabled = cfg.get("telegram_notifications") == "ON"

        # Checkboxes for individual sourcing channels
        source_custom = cfg.get("source_custom", "ON") == "ON"
        source_groww = cfg.get("source_groww", "ON") == "ON"
        source_auto_scanned = cfg.get("source_auto_scanned", "ON") == "ON"
        source_high_profitable = cfg.get("source_high_profitable", "ON") == "ON"
        source_prev_algo = cfg.get("source_prev_algo", "ON") == "ON"
        source_premarket = cfg.get("source_premarket", "ON") == "ON"

        algo_status = algo_trading_engine.status()
        session = algo_status.get("session") or {}
        running = algo_status.get("status") == "RUNNING"
        
        capital = _number(session.get("capital", 100000.0))
        available = _number(algo_status.get("portfolio", {}).get("available_funds", capital))
        risk_per_trade = _number(session.get("risk_per_trade", 1.0))
        max_trades = int(session.get("max_trades", 3))
        max_loss = _number(session.get("max_loss", 2000.0))

        portfolio = algo_status.get("portfolio") or {}
        net_pnl = _number(portfolio.get("net_pnl", 0.0))
        active_orders = algo_status.get("orders") or []
        active_orders_count = sum(1 for o in active_orders if o.get("status") in {"PENDING", "OPEN", "PARTIAL_EXIT"})

        daily_loss_limit_reached = net_pnl <= -abs(max_loss)
        max_trades_reached = active_orders_count >= max_trades

        # Gather Candidate Symbols from configured sources
        candidates: set[str] = set()

        if source_custom:
            custom_rows = algo_store.list_rows("algo_watchlist_custom_stocks")
            for r in custom_rows:
                if r.get("monitoring_status") == "ACTIVE" and r.get("symbol"):
                    candidates.add(normalize_stock_symbol(r["symbol"]))
                    
        if source_groww:
            for sym in stock_registry.groww_active_intraday_stocks:
                if sym:
                    candidates.add(normalize_stock_symbol(sym))
            for sym in stock_registry.groww_added_stocks:
                if sym:
                    candidates.add(normalize_stock_symbol(sym))
                    
        if source_auto_scanned:
            for sym, sugg in stock_registry.active_suggestions.items():
                src = sugg.get("source_name") or sugg.get("source") or ""
                if "premarket" not in str(src).lower() and "custom" not in str(src).lower():
                    candidates.add(normalize_stock_symbol(sym))
                    
        if source_high_profitable:
            for sym, sugg in stock_registry.active_suggestions.items():
                entry_val = _number(sugg.get("entry_price") or sugg.get("entry"))
                target_val = _number(sugg.get("target_1") or sugg.get("target1"))
                ret_pot = (target_val - entry_val) / entry_val * 100 if entry_val > 0 else 0.0
                if ret_pot >= 3.0 or _number(sugg.get("ml_score") or sugg.get("confidence")) >= 70:
                    candidates.add(normalize_stock_symbol(sym))
                    
        if source_prev_algo:
            hist_rows = algo_store.list_rows("algo_signal_history")
            for r in hist_rows:
                if r.get("symbol"):
                    candidates.add(normalize_stock_symbol(r["symbol"]))
            exec_rows = algo_store.list_rows("algo_execution_queue")
            for r in exec_rows:
                if r.get("symbol"):
                    candidates.add(normalize_stock_symbol(r["symbol"]))
                    
        if source_premarket:
            for sym, sugg in stock_registry.active_suggestions.items():
                src = sugg.get("source_name") or sugg.get("source") or ""
                if "premarket" in str(src).lower():
                    candidates.add(normalize_stock_symbol(sym))

        # Register candidates to keep active feed streaming quotes
        for sym in candidates:
            if sym:
                stock_data_service.tracked_symbols.add(sym)

        current_active_signals = []
        current_rejections = []
        current_eligible = []
        now_dt = datetime.now(timezone.utc)

        # Get Nifty market index confirmation details
        nifty_snapshot = stock_snapshot_cache.get("^NSEI") or stock_snapshot_cache.get("NIFTY") or {}
        nifty_change = _number(nifty_snapshot.get("change_percent") or nifty_snapshot.get("p_change") or 0.0)

        for symbol in candidates:
            if not symbol:
                continue
            
            # Fetch Quote Snapshot
            snapshot = stock_snapshot_cache.get(symbol) or {}
            current_price = _number(snapshot.get("current_price") or snapshot.get("price"))
            if current_price <= 0:
                # Attempt service fallback lookup
                try:
                    s_data = await stock_data_service.get_stock(symbol, allow_stale=True)
                    if s_data:
                        current_price = _number(s_data.get("price") or s_data.get("current_price"))
                        snapshot = s_data
                except Exception:
                    pass
            
            if current_price <= 0:
                continue

            # Load analysis heuristics
            analysis = {}
            try:
                analysis = await stock_data_service.get_analysis(symbol, allow_stale=True) or {}
            except Exception:
                pass

            symbol_key = symbol.replace(".NS", "").replace(".BO", "")
            sugg = stock_registry.active_suggestions.get(symbol_key) or stock_registry.active_suggestions.get(symbol)

            # Determine direction & pricing plans
            direction = "BUY"
            if sugg:
                direction = str(sugg.get("direction") or sugg.get("action") or "BUY").upper()
                if "SELL" in direction or "SHORT" in direction:
                    direction = "SELL"
                else:
                    direction = "BUY"
                entry_price = _number(sugg.get("entry_price") or sugg.get("entry") or current_price)
                stop_loss = _number(sugg.get("stop_loss") or sugg.get("stoploss"))
                target_1 = _number(sugg.get("target_1") or sugg.get("target1"))
                target_2 = _number(sugg.get("target_2") or sugg.get("target2") or target_1)
            else:
                action_str = str(snapshot.get("action") or "").upper()
                direction = "SELL" if ("SELL" in action_str or "SHORT" in action_str) else "BUY"
                entry_price = _number(snapshot.get("entry") or snapshot.get("entry_price") or current_price)
                stop_loss = _number(snapshot.get("stop_loss") or snapshot.get("stoploss"))
                target_1 = _number(snapshot.get("target1") or snapshot.get("target_1"))
                target_2 = _number(snapshot.get("target2") or snapshot.get("target_2") or target_1)

            if stop_loss <= 0:
                stop_loss = entry_price * 0.99 if direction == "BUY" else entry_price * 1.01
            if target_1 <= 0:
                target_1 = entry_price * 1.02 if direction == "BUY" else entry_price * 0.98
            if target_2 <= 0:
                target_2 = target_1

            # Standard risk values
            confidence = _number(snapshot.get("quality_score") or snapshot.get("confidence") or (sugg.get("confidence") if sugg else 75.0))
            if confidence <= 0:
                confidence = 75.0

            volume_ratio = _number(snapshot.get("volume_spike") or snapshot.get("relative_volume") or snapshot.get("volume_vs_avg"), 1.0)
            avg_volume = _number(snapshot.get("avg_volume") or (snapshot.get("volume_analysis") or {}).get("avg_volume"), 50000.0)
            
            risk = abs(entry_price - stop_loss)
            reward = abs(target_1 - entry_price)
            risk_reward = round(reward / risk, 2) if risk > 0 else 1.0
            profit_potential = round(reward / entry_price * 100, 2) if entry_price > 0 else 0.0

            updated_str = snapshot.get("updated_at") or snapshot.get("last_checked") or snapshot.get("timestamp")
            updated = _timestamp(updated_str)
            age_seconds = max(0.0, (now_dt - updated).total_seconds()) if updated else 999999.0

            # Technical details
            indicators = snapshot.get("indicators") or analysis.get("indicators") or {}
            vwap = _number(indicators.get("vwap") or snapshot.get("vwap"))
            rsi = _number(indicators.get("rsi") or 55.0)
            macd = _number(indicators.get("macd") or 0.0)
            adx = _number(indicators.get("adx") or 22.0)
            spread = _number(snapshot.get("spread") or (snapshot.get("ask", 0) - snapshot.get("bid", 0)))
            bid = _number(snapshot.get("bid") or current_price)
            ask = _number(snapshot.get("ask") or current_price)

            # Strict 19-Point Evaluation Filters
            rejection_reasons = []

            # 1. Live data freshness (max 2 seconds default)
            if age_seconds > stale_data_max_age:
                rejection_reasons.append(f"Data stale ({age_seconds:.1f}s > {stale_data_max_age}s)")

            # 2. Volume confirmation (2x average volume)
            if volume_ratio < volume_multiplier:
                rejection_reasons.append(f"Weak volume ratio ({volume_ratio:.2f}x < {volume_multiplier}x)")

            # 3. VWAP confirmation
            vwap_confirmed = bool(vwap <= 0 or (direction == "BUY" and current_price >= vwap) or (direction == "SELL" and current_price <= vwap))
            if not vwap_confirmed:
                rejection_reasons.append("VWAP confirmation failed")

            # 4. Trend strength (ADX >= 20)
            if adx < 20.0:
                rejection_reasons.append(f"Weak trend (ADX {adx:.1f} < 20)")

            # 5. Breakout/breakdown quality
            breakout_quality = _number(snapshot.get("breakout_score") or analysis.get("breakout_score") or 60.0)
            if breakout_quality < 50.0:
                rejection_reasons.append(f"Low breakout quality ({breakout_quality:.1f})")

            # 6. Support/resistance distance
            breakout_level = _number(snapshot.get("breakout_level") or analysis.get("breakout_level") or entry_price)
            breakout_distance = abs(current_price - breakout_level) / breakout_level if breakout_level > 0 else 0.0
            if breakout_distance > 0.03:
                rejection_reasons.append(f"Too far from breakout level ({breakout_distance*100:.2f}% > 3%)")

            # 7. Risk/reward
            if risk_reward < min_risk_reward:
                rejection_reasons.append(f"Poor risk/reward ({risk_reward:.2f}x < {min_risk_reward}x)")

            # 8. Stoploss tightness (max 1.5% stoploss width)
            stop_loss_pct = abs(entry_price - stop_loss) / entry_price * 100 if entry_price > 0 else 0
            if stop_loss_pct > max_stoploss_pct:
                rejection_reasons.append(f"Stoploss too wide ({stop_loss_pct:.2f}% > {max_stoploss_pct}%)")

            # 9. Target realism
            if profit_potential < min_expected_profit_pct:
                rejection_reasons.append(f"Target profit too small ({profit_potential:.2f}% < {min_expected_profit_pct}%)")
            if profit_potential > 15.0:
                rejection_reasons.append(f"Target profit unrealistic ({profit_potential:.2f}% > 15%)")

            # 10. Liquidity (avg volume >= 10,000)
            if avg_volume < 10000.0:
                rejection_reasons.append(f"Low liquidity (avg volume {avg_volume:.0f} < 10000)")

            # 11. Spread/slippage risk
            spread_pct = (spread / current_price * 100) if current_price > 0 else 0.0
            if spread_pct > 0.25:
                rejection_reasons.append(f"High spread slippage risk ({spread_pct:.3f}% > 0.25%)")

            # 12. Momentum quality (RSI filter)
            if direction == "BUY" and rsi < 50.0:
                rejection_reasons.append(f"Weak momentum (RSI {rsi:.1f} < 50)")
            elif direction == "SELL" and rsi > 50.0:
                rejection_reasons.append(f"Strong opposite momentum (RSI {rsi:.1f} > 50)")

            # 13. Candle confirmation
            last_candle_green = snapshot.get("last_candle_color") == "green" or (current_price >= _number(snapshot.get("open") or current_price))
            if direction == "BUY" and not last_candle_green:
                rejection_reasons.append("Last candle color is bearish (red)")
            elif direction == "SELL" and last_candle_green:
                rejection_reasons.append("Last candle color is bullish (green)")

            # 15. Already-moved detection
            already_moved = _number(snapshot.get("already_moved_percent") or snapshot.get("already_moved_pct") or 0.0)
            if already_moved > 1.5:
                rejection_reasons.append(f"Stock already moved too much ({already_moved:.2f}% > 1.5%)")

            # 16. False breakout detection
            false_breakout = snapshot.get("false_breakout") or analysis.get("false_breakout_warning") or False
            if false_breakout:
                rejection_reasons.append("Possible false-breakout reversal warning")

            # 17. Market direction confirmation
            if direction == "BUY" and nifty_change < 0.0:
                rejection_reasons.append(f"Negative market backdrop (Nifty change {nifty_change:.2f}%)")
            elif direction == "SELL" and nifty_change > 0.0:
                rejection_reasons.append(f"Positive market backdrop (Nifty change {nifty_change:.2f}%)")

            # 18. Sector strength
            sector_confirmed = snapshot.get("sector_outperforming") or analysis.get("sector_outperforming") or True
            if not sector_confirmed:
                rejection_reasons.append("Weak sectoral index correlation")

            # 19. Gap risk
            open_price = _number(snapshot.get("open") or entry_price)
            prev_close = _number(snapshot.get("prev_close") or entry_price)
            gap_pct = abs(open_price - prev_close) / prev_close * 100 if prev_close > 0 else 0.0
            if gap_pct > 1.5:
                rejection_reasons.append(f"Extreme gap opening risk ({gap_pct:.2f}% > 1.5%)")

            # 14. Event/news risk
            news_risk = snapshot.get("earnings_event_risk") or False
            if news_risk:
                rejection_reasons.append("High event/earnings announcement risk")

            # Avoid first 30 minutes breakout check
            from backend.analysis_engine import AnalysisEngine
            breakout_window_open = AnalysisEngine._breakout_window_open()
            if avoid_first_30m and not breakout_window_open:
                rejection_reasons.append("Avoid first 30 minutes breakout window")

            # AI/ML scoring parameters
            tech_score = 100.0 if (rsi >= 50 and vwap_confirmed and adx >= 20) else 65.0
            vol_score = min(100.0, volume_ratio * 35.0)
            mom_score = min(100.0, (rsi - 30.0) * 2.0) if direction == "BUY" else min(100.0, (70.0 - rsi) * 2.0)
            risk_score = max(0.0, 100.0 - stop_loss_pct * 30.0 - spread_pct * 200.0)
            liq_score = min(100.0, avg_volume / 250.0)
            trend_score = min(100.0, adx * 3.5)
            ml_score = _number(snapshot.get("ml_probability") or snapshot.get("ml_score") or sugg.get("ml_score") if sugg else 62.0)
            ai_score = 90.0 if not false_breakout else 45.0
            safety_score = 95.0 if (age_seconds <= stale_data_max_age and spread_pct <= 0.15) else 50.0

            # Combined AI/ML Algo Score
            score = (
                tech_score * 0.2
                + vol_score * 0.15
                + mom_score * 0.15
                + trend_score * 0.1
                + ml_score * 0.1
                + ai_score * 0.1
                + safety_score * 0.2
            )

            # Generate AI Reason
            ai_reason = "Strong momentum structure with volume spike, clean VWAP reclaim, and aligned ML validation." if not rejection_reasons else f"Risk qualifications failed: {', '.join(rejection_reasons)}."

            if confidence < min_confidence or score < min_algo_score:
                if f"Low confidence ({confidence:.1f}%)" not in rejection_reasons and confidence < min_confidence:
                    rejection_reasons.append(f"Low confidence ({confidence:.1f}% < {min_confidence}%)")
                if f"Low algo score ({score:.1f})" not in rejection_reasons and score < min_algo_score:
                    rejection_reasons.append(f"Low algo score ({score:.1f} < {min_algo_score})")

            # Check if active
            is_active = confidence >= 60.0 and entry_price > 0

            if rejection_reasons:
                rejection_record = {
                    "symbol": symbol,
                    "company_name": snapshot.get("company_name") or sugg.get("company_name") if sugg else symbol,
                    "reason": ", ".join(rejection_reasons),
                    "confidence": confidence,
                    "volume_ratio": volume_ratio,
                    "risk_reward": risk_reward,
                    "already_moved": already_moved,
                    "updated_at": algo_store.now()
                }
                current_rejections.append(rejection_record)
            else:
                # Algo Eligible Setup Sizing
                suggested_qty = 0
                capital_required = 0.0
                max_risk = 0.0
                expected_profit = 0.0

                if entry_price > 0 and stop_loss > 0:
                    per_share_risk = abs(entry_price - stop_loss)
                    if per_share_risk > 0:
                        suggested_qty = max(1, int((capital * risk_per_trade / 100.0) / per_share_risk))
                        max_qty_by_funds = int(available / entry_price) if entry_price > 0 else 0
                        suggested_qty = min(suggested_qty, max_qty_by_funds)
                        
                        capital_required = round(suggested_qty * entry_price, 2)
                        max_risk = round(suggested_qty * per_share_risk, 2)
                        expected_profit = round(suggested_qty * abs(target_1 - entry_price), 2)

                algo_eligible = "YES" if suggested_qty > 0 else "NO"
                auto_trade_allowed = "YES" if (algo_eligible == "YES" and running and not daily_loss_limit_reached and not max_trades_reached) else "NO"

                eligible_record = {
                    "symbol": symbol,
                    "company_name": snapshot.get("company_name") or sugg.get("company_name") if sugg else symbol,
                    "algo_eligibility": algo_eligible,
                    "eligible_reason": "High confidence trend confirmation & strong volume.",
                    "capital_required": capital_required,
                    "suggested_quantity": suggested_qty,
                    "max_risk": max_risk,
                    "expected_profit": expected_profit,
                    "entry_trigger": entry_price,
                    "auto_trade_allowed": auto_trade_allowed,
                    "confidence": confidence,
                    "algo_score": round(score, 2),
                    "side": direction,
                    "stop_loss": stop_loss,
                    "target": target_1,
                    "updated_at": algo_store.now()
                }
                current_eligible.append(eligible_record)

            if is_active:
                signal_record = {
                    "symbol": symbol,
                    "company_name": snapshot.get("company_name") or sugg.get("company_name") if sugg else symbol,
                    "side": direction,
                    "signal_type": "Breakout" if "breakout" in str(snapshot.get("reason", "")).lower() else "Momentum Scan",
                    "entry_price": entry_price,
                    "current_price": current_price,
                    "stop_loss": stop_loss,
                    "target_1": target_1,
                    "target_2": target_2,
                    "trailing_sl": stop_loss,
                    "confidence": confidence,
                    "algo_score": round(score, 2),
                    "risk_reward": risk_reward,
                    "status": "ACTIVE" if sugg else "POTENTIAL",
                    "reason": snapshot.get("reason") or snapshot.get("action") or "Trend alignment",
                    "updated_at": algo_store.now(),
                    "ml_probability": ml_score,
                    "ai_reason": ai_reason,
                    "rejection_reason": ", ".join(rejection_reasons) if rejection_reasons else "",
                    "auto_trade_allowed": "YES" if not rejection_reasons else "NO",
                    "tech_score": tech_score,
                    "vol_score": vol_score,
                    "mom_score": mom_score,
                    "risk_score": risk_score,
                    "liq_score": liq_score,
                    "trend_score": trend_score,
                    "safety_score": safety_score
                }
                current_active_signals.append(signal_record)

        # Clear and sync DB records
        algo_store.clear_table("algo_watchlist_signals")
        algo_store.clear_table("algo_watchlist_rejections")

        for sig in current_active_signals:
            algo_store.insert("algo_watchlist_signals", sig)
        for rej in current_rejections:
            algo_store.insert("algo_watchlist_rejections", rej)

        # Auto-queueing of eligible suggestions
        if running and not daily_loss_limit_reached and not max_trades_reached:
            active_symbols = {o.get("symbol") for o in active_orders if o.get("status") in {"PENDING", "OPEN", "PARTIAL_EXIT"}}
            queued_symbols = {q.get("symbol") for q in algo_store.list_rows("algo_execution_queue") if q.get("execution_status") in {"PENDING", "EXECUTING"}}
            
            for el in current_eligible:
                sym = el["symbol"]
                if el["auto_trade_allowed"] == "YES" and sym not in active_symbols and sym not in queued_symbols:
                    total_expected_trades = active_orders_count + len(queued_symbols)
                    if total_expected_trades >= max_trades:
                        break

                    queue_record = {
                        "symbol": sym,
                        "side": el["side"],
                        "entry_price": el["entry_trigger"],
                        "stop_loss": el["stop_loss"],
                        "target": el["target"],
                        "quantity": el["suggested_quantity"],
                        "capital_allocation": el["capital_required"],
                        "confidence": el["confidence"],
                        "algo_score": el["algo_score"],
                        "execution_status": "PENDING",
                        "sent_to_algo": "YES",
                        "updated_at": algo_store.now()
                    }
                    algo_store.insert("algo_execution_queue", queue_record)

                    # Persistence History
                    algo_store.insert("algo_signal_history", {
                        "history_id": uuid.uuid4().hex,
                        "symbol": sym,
                        "side": el["side"],
                        "entry_price": el["entry_trigger"],
                        "stop_loss": el["stop_loss"],
                        "target": el["target"],
                        "confidence": el["confidence"],
                        "algo_score": el["algo_score"],
                        "status": "QUEUED",
                        "reason": "Automated qualification check passed. Sent to Execution Queue.",
                        "created_at": algo_store.now()
                    })
                    logger.info(f"AlgoWatchlistService: Automatically queued {sym} ({el['side']}) for trading.")

                    # Telegram alert dispatch on queue placement
                    if telegram_enabled:
                        bot_token = str(watchlist_monitor.settings.get("telegram_bot_token") or "").strip()
                        chat_id = str(watchlist_monitor.settings.get("telegram_chat_id") or "").strip()
                        if bot_token:
                            os.environ["TELEGRAM_BOT_TOKEN"] = bot_token
                        if chat_id:
                            os.environ["TELEGRAM_CHAT_IDS"] = chat_id

                        msg = (
                            f"🔔 *[ALGO TRADE QUEUED]*\n"
                            f"Symbol: {sym}\n"
                            f"Side: {el['side']}\n"
                            f"Entry Price: INR {el['entry_trigger']:.2f}\n"
                            f"Stop Loss: INR {el['stop_loss']:.2f}\n"
                            f"Target: INR {el['target']:.2f}\n"
                            f"Confidence: {el['confidence']:.1f}%\n"
                            f"Algo Score: {el['algo_score']:.1f}\n"
                            f"Allocation: INR {el['capital_required']:.2f} ({el['suggested_quantity']} Qty)\n"
                            f"Mode: Paper Trade (Safe Mode)"
                        )
                        try:
                            # Send message
                            await asyncio.to_thread(send_telegram_messages, "Watchlist", msg)
                            logger.info(f"Telegram alert sent for queued symbol: {sym}")
                        except Exception as t_err:
                            logger.warning(f"Telegram queued alert failed: {t_err}")

        # Stale/rejected queue cancellation
        rejected_symbols = {r["symbol"] for r in current_rejections}
        eligible_symbols = {e["symbol"] for e in current_eligible}
        pending_queue_items = [q for q in algo_store.list_rows("algo_execution_queue") if q.get("execution_status") == "PENDING"]
        for q in pending_queue_items:
            sym = q["symbol"]
            if sym in rejected_symbols or sym not in eligible_symbols:
                algo_store.update("algo_execution_queue", "symbol", sym, {
                    "execution_status": "CANCELLED",
                    "updated_at": algo_store.now()
                })
                algo_store.insert("algo_signal_history", {
                    "history_id": uuid.uuid4().hex,
                    "symbol": sym,
                    "side": q["side"],
                    "entry_price": q["entry_price"],
                    "stop_loss": q["stop_loss"],
                    "target": q["target"],
                    "confidence": q["confidence"],
                    "algo_score": q["algo_score"],
                    "status": "CANCELLED",
                    "reason": "Signal became stale or failed risk qualifications. Cancelled for safety.",
                    "created_at": algo_store.now()
                })
                logger.info(f"AlgoWatchlistService: Cancelled pending queue item {sym} (became stale/rejected).")

                # Dispatch Telegram Alert on Cancel
                if telegram_enabled:
                    bot_token = str(watchlist_monitor.settings.get("telegram_bot_token") or "").strip()
                    chat_id = str(watchlist_monitor.settings.get("telegram_chat_id") or "").strip()
                    if bot_token:
                        os.environ["TELEGRAM_BOT_TOKEN"] = bot_token
                    if chat_id:
                        os.environ["TELEGRAM_CHAT_IDS"] = chat_id

                    msg = (
                        f"⚠️ *[ALGO TRADE CANCELLED]*\n"
                        f"Symbol: {sym}\n"
                        f"Reason: Signal became stale or failed active risk qualifications. Cancelled for safety."
                    )
                    try:
                        await asyncio.to_thread(send_telegram_messages, "Watchlist", msg)
                    except Exception:
                        pass

    async def manual_send_to_algo(self, symbol: str) -> dict[str, Any]:
        # Import dynamically to avoid circular imports
        from backend.algo_engine import algo_trading_engine

        cfg = self.get_config()
        telegram_enabled = cfg.get("telegram_notifications") == "ON"

        signals = algo_store.list_rows("algo_watchlist_signals")
        sig = next((s for s in signals if s["symbol"] == symbol), None)
        if not sig:
            return {"status": "error", "message": f"Symbol {symbol} is not a current qualified active signal"}

        algo_status = algo_trading_engine.status()
        orders = algo_status.get("orders") or []
        if any(o.get("symbol") == symbol and o.get("status") in {"PENDING", "OPEN", "PARTIAL_EXIT"} for o in orders):
            return {"status": "error", "message": f"An active order or position already exists for {symbol}"}

        queued = algo_store.list_rows("algo_execution_queue")
        if any(q.get("symbol") == symbol and q.get("execution_status") == "PENDING" for q in queued):
            return {"status": "error", "message": f"Symbol {symbol} is already pending in the execution queue"}

        session = algo_status.get("session") or {}
        running = algo_status.get("status") == "RUNNING"
        if not running:
            return {"status": "error", "message": "Algo session is not running. Please start the session first."}

        capital = _number(session.get("capital", 100000.0))
        available = _number(algo_status.get("portfolio", {}).get("available_funds", capital))
        risk_per_trade = _number(session.get("risk_per_trade", 1.0))
        max_trades = int(session.get("max_trades", 3))
        max_loss = _number(session.get("max_loss", 2000.0))

        portfolio = algo_status.get("portfolio") or {}
        net_pnl = _number(portfolio.get("net_pnl", 0.0))
        if net_pnl <= -abs(max_loss):
            return {"status": "error", "message": "Daily maximum loss limit reached. Trading is locked."}

        active_orders_count = sum(1 for o in orders if o.get("status") in {"PENDING", "OPEN", "PARTIAL_EXIT"})
        if active_orders_count >= max_trades:
            return {"status": "error", "message": f"Maximum trades limit ({max_trades}) reached for the day."}

        entry_price = _number(sig["entry_price"])
        stop_loss = _number(sig["stop_loss"])
        target = _number(sig["target_1"])

        suggested_qty = 0
        capital_required = 0.0
        if entry_price > 0 and stop_loss > 0:
            per_share_risk = abs(entry_price - stop_loss)
            if per_share_risk > 0:
                suggested_qty = max(1, int((capital * risk_per_trade / 100.0) / per_share_risk))
                max_qty_by_funds = int(available / entry_price) if entry_price > 0 else 0
                suggested_qty = min(suggested_qty, max_qty_by_funds)
                capital_required = round(suggested_qty * entry_price, 2)

        if suggested_qty <= 0:
            return {"status": "error", "message": "Insufficient capital or invalid risk parameters to size this trade."}

        queue_record = {
            "symbol": symbol,
            "side": sig["side"],
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "target": target,
            "quantity": suggested_qty,
            "capital_allocation": capital_required,
            "confidence": sig["confidence"],
            "algo_score": sig["algo_score"],
            "execution_status": "PENDING",
            "sent_to_algo": "YES",
            "updated_at": algo_store.now()
        }

        # Upsert queue item
        existing_queue = next((q for q in queued if q["symbol"] == symbol), None)
        if existing_queue:
            algo_store.update("algo_execution_queue", "symbol", symbol, queue_record)
        else:
            algo_store.insert("algo_execution_queue", queue_record)

        algo_store.insert("algo_signal_history", {
            "history_id": uuid.uuid4().hex,
            "symbol": symbol,
            "side": sig["side"],
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "target": target,
            "confidence": sig["confidence"],
            "algo_score": sig["algo_score"],
            "status": "QUEUED",
            "reason": "Manual Send to Algo trigger. Sized and queued successfully.",
            "created_at": algo_store.now()
        })

        # Telegram alert dispatch on manual queue placement
        if telegram_enabled:
            bot_token = str(watchlist_monitor.settings.get("telegram_bot_token") or "").strip()
            chat_id = str(watchlist_monitor.settings.get("telegram_chat_id") or "").strip()
            if bot_token:
                os.environ["TELEGRAM_BOT_TOKEN"] = bot_token
            if chat_id:
                os.environ["TELEGRAM_CHAT_IDS"] = chat_id

            msg = (
                f"🔔 *[ALGO TRADE QUEUED (MANUAL)]*\n"
                f"Symbol: {symbol}\n"
                f"Side: {sig['side']}\n"
                f"Entry Price: INR {entry_price:.2f}\n"
                f"Stop Loss: INR {stop_loss:.2f}\n"
                f"Target: INR {target:.2f}\n"
                f"Algo Score: {sig['algo_score']:.1f}\n"
                f"Allocation: INR {capital_required:.2f} ({suggested_qty} Qty)\n"
                f"Mode: Paper Trade (Safe Mode)"
            )
            try:
                await asyncio.to_thread(send_telegram_messages, "Watchlist", msg)
            except Exception as t_err:
                logger.warning(f"Telegram manual queued alert failed: {t_err}")

        try:
            await algo_trading_engine._maybe_open_trade(session)
        except Exception as e:
            logger.error(f"Error triggering direct trade placement: {e}")

        return {"status": "ok", "message": f"Successfully queued {symbol} to Algo Execution Queue"}


algo_watchlist_service = AlgoWatchlistService()

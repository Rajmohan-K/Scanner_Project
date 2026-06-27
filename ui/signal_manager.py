from __future__ import annotations

import json
import time
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from ui.v20_store import connect, ensure_db
from ui.stock_data_service import normalize_stock_symbol, symbol_base
from utils.logger import logger

class SignalManager:
    def __init__(self) -> None:
        self.init_db()

    def init_db(self) -> None:
        try:
            ensure_db()
        except Exception as e:
            logger.error(f"Failed to initialize database for signal manager: {e}", exc_info=True)

    def get_active_signals(self) -> dict[str, dict[str, Any]]:
        """
        Loads all active signals from PostgreSQL.
        """
        active = {}
        try:
            with connect() as conn:
                rows = conn.execute("SELECT * FROM signal_records WHERE UPPER(status) NOT IN ('CLOSED', 'STOP LOSS HIT', 'TARGET HIT')").fetchall()
                for row in rows:
                    record = dict(row)
                    # Convert boolean/integer fields
                    record["trailing_activated"] = bool(record.get("trailing_activated"))
                    # Map to camelCase keys for frontend compatibility
                    record["suggestedTime"] = record["suggested_time"]
                    record["suggestedPrice"] = record["suggested_price"]
                    record["actionAtSuggestion"] = record["action_at_suggestion"]
                    record["entry"] = record["entry_price"]
                    record["stopLoss"] = record["stop_loss"]
                    record["target1"] = record["target_1"]
                    record["target2"] = record["target_2"]
                    record["target3"] = record["target_3"]
                    record["initialReason"] = record["initial_reason"]
                    record["initialConfidence"] = record["initial_confidence"]
                    record["currentPrice"] = record["current_price"]
                    record["currentPLPercent"] = record["current_pl_percent"]
                    record["maxGainPercent"] = record["max_gain_percent"]
                    record["maxLossDrawdownPercent"] = record["max_drawdown_percent"]
                    record["timeActive"] = record["time_active"]
                    record["latestConfidence"] = record["latest_confidence"]
                    record["latestStatus"] = record["status"]
                    record["trailingStop"] = record["current_trailing_stop"]
                    record["trailingActivated"] = record["trailing_activated"]
                    record["trailingActivatedAt"] = record["trailing_activated_at"]
                    record["trailingStatus"] = record["trailing_status"]
                    record["targetHitStatus"] = record.get("target_hit_status") or "None"
                    record["stopLossHitStatus"] = record.get("stop_loss_hit_status") or "None"
                    record["dataFreshness"] = record["freshness"]
                    record["initialStopLoss"] = record["initial_stop_loss"]
                    record["highestPriceSinceEntry"] = record["highest_price_since_entry"]
                    record["lowestPriceSinceEntry"] = record["lowest_price_since_entry"]
                    record["final_status"] = record["status"].upper()
                    record["exit_price"] = record["current_price"]
                    record["max_gain"] = record["max_gain_percent"]
                    
                    active[record["symbol"]] = record
        except Exception as e:
            logger.error(f"Failed to get active signals from DB: {e}")
        return active

    def get_signal_history(self) -> list[dict[str, Any]]:
        """
        Loads closed signals history from PostgreSQL.
        """
        history = []
        try:
            with connect() as conn:
                rows = conn.execute("SELECT * FROM signal_records WHERE UPPER(status) IN ('CLOSED', 'STOP LOSS HIT', 'TARGET HIT') ORDER BY archived_at DESC").fetchall()
                for row in rows:
                    record = dict(row)
                    record["trailing_activated"] = bool(record.get("trailing_activated"))
                    # Map to camelCase keys for frontend compatibility
                    record["suggestedTime"] = record["suggested_time"]
                    record["suggestedPrice"] = record["suggested_price"]
                    record["actionAtSuggestion"] = record["action_at_suggestion"]
                    record["entry"] = record["entry_price"]
                    record["stopLoss"] = record["stop_loss"]
                    record["target1"] = record["target_1"]
                    record["target2"] = record["target_2"]
                    record["target3"] = record["target_3"]
                    record["initialReason"] = record["initial_reason"]
                    record["initialConfidence"] = record["initial_confidence"]
                    record["currentPrice"] = record["current_price"]
                    record["currentPLPercent"] = record["current_pl_percent"]
                    record["maxGainPercent"] = record["max_gain_percent"]
                    record["maxLossDrawdownPercent"] = record["max_drawdown_percent"]
                    record["timeActive"] = record["time_active"]
                    record["latestConfidence"] = record["latest_confidence"]
                    record["latestStatus"] = record["status"]
                    record["trailingStop"] = record["current_trailing_stop"]
                    record["trailingActivated"] = record["trailing_activated"]
                    record["trailingActivatedAt"] = record["trailing_activated_at"]
                    record["trailingStatus"] = record["trailing_status"]
                    record["targetHitStatus"] = record.get("target_hit_status") or "None"
                    record["stopLossHitStatus"] = record.get("stop_loss_hit_status") or "None"
                    record["dataFreshness"] = record["freshness"]
                    record["initialStopLoss"] = record["initial_stop_loss"]
                    record["highestPriceSinceEntry"] = record["highest_price_since_entry"]
                    record["lowestPriceSinceEntry"] = record["lowest_price_since_entry"]
                    record["final_status"] = record["status"].upper()
                    record["exit_price"] = record["current_price"]
                    record["max_gain"] = record["max_gain_percent"]
                    history.append(record)
        except Exception as e:
            logger.error(f"Failed to get signal history from DB: {e}")
        return history

    def create_signal(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        reason: str,
        target_1: float,
        target_2: float,
        stop_loss: float,
        target_3: float | None = None,
        initial_confidence: float = 80.0,
        provider: str = "yfinance",
        action_at_suggestion: str = "BUY"
    ) -> dict[str, Any] | None:
        """
        Creates a new V50 signal record in the PostgreSQL database and freezes its values.
        """
        normalized = normalize_stock_symbol(symbol)
        active_signals = self.get_active_signals()
        
        # Before creating a new BUY/SELL signal, check if an active signal already exists for normalizedSymbol + direction
        if normalized in active_signals:
            existing = active_signals[normalized]
            if existing.get("direction") == direction:
                logger.info(f"SignalManager: Active signal already exists for {normalized} {direction}. Skipping creation.")
                return existing

        now_ts = time.time()
        now_str = datetime.now().strftime("%I:%M:%S %p")
        
        # Calculate targets/SL defaults if not provided
        if target_3 is None:
            if direction == "SELL":
                target_3 = round(entry_price * 0.955, 2)
            else:
                target_3 = round(entry_price * 1.045, 2)

        # Generate Signal ID: SIG_{SYMBOL}_{YYYYMMDD}_{INDEX}
        today_str = datetime.now().strftime("%Y%m%d")
        base_sym = symbol_base(normalized)
        prefix = f"SIG_{base_sym}_{today_str}_"
        
        max_idx = 0
        try:
            with connect() as conn:
                rows = conn.execute("SELECT signal_id FROM signal_records WHERE signal_id LIKE ?", (f"{prefix}%",)).fetchall()
                for r in rows:
                    s_id = r["signal_id"]
                    try:
                        idx_part = int(s_id.replace(prefix, ""))
                        if idx_part > max_idx:
                            max_idx = idx_part
                    except ValueError:
                        pass
        except Exception as e:
            logger.error(f"Error fetching signal count prefix: {e}")

        next_idx = max_idx + 1
        signal_id = f"{prefix}{next_idx:03d}"

        # Initialize the signal dict with BOTH camelCase and snake_case keys for frontend compatibility
        signal = {
            "signal_id": signal_id,
            "symbol": normalized,
            "direction": direction,
            "suggested_time": now_str,
            "suggestedTime": now_str,
            "suggested_timestamp": now_ts,
            "suggested_price": entry_price,
            "suggestedPrice": entry_price,
            "entry_price": entry_price,
            "entry": entry_price,
            "stop_loss": stop_loss,
            "stopLoss": stop_loss,
            "target_1": target_1,
            "target1": target_1,
            "target_2": target_2,
            "target2": target_2,
            "target_3": target_3,
            "target3": target_3,
            "initial_confidence": initial_confidence,
            "initialConfidence": initial_confidence,
            "initial_reason": reason,
            "initialReason": reason,
            "action_at_suggestion": action_at_suggestion,
            "actionAtSuggestion": action_at_suggestion,
            
            # Live performance tracking fields
            "current_price": entry_price,
            "currentPrice": entry_price,
            "current_pl_percent": 0.0,
            "currentPLPercent": 0.0,
            "max_gain_percent": 0.0,
            "maxGainPercent": 0.0,
            "max_loss_percent": 0.0,
            "max_drawdown_percent": 0.0,
            "maxLossDrawdownPercent": 0.0,
            "time_active": "00h 00m 00s",
            "timeActive": "00h 00m 00s",
            "latest_confidence": initial_confidence,
            "latestConfidence": initial_confidence,
            "status": "ACTIVE",
            "latestStatus": "Active",
            "provider": provider,
            "freshness": "LIVE",
            "dataFreshness": "LIVE",
            
            # Trailing stop fields
            "max_price_reached": entry_price,
            "min_price_reached": entry_price,
            "highest_price_since_entry": entry_price,
            "lowest_price_since_entry": entry_price,
            "initial_stop_loss": stop_loss,
            "initialStopLoss": stop_loss,
            "current_trailing_stop": stop_loss,
            "trailingStop": stop_loss,
            "trailing_activated": 0,
            "trailingActivated": False,
            "trailing_activated_at": None,
            "trailingActivatedAt": None,
            "trailing_status": "Inactive",
            "trailingStatus": "Inactive",
            "target_hit_status": "None",
            "targetHitStatus": "None",
            "stop_loss_hit_status": "None",
            "stopLossHitStatus": "None",
            "outcome": "",
            "archived_at": ""
        }

        # Save to PostgreSQL
        try:
            with connect() as conn:
                conn.execute("""
                    INSERT INTO signal_records (
                        signal_id, symbol, direction, suggested_time, suggested_timestamp, suggested_price,
                        entry_price, stop_loss, target_1, target_2, target_3, initial_confidence, initial_reason,
                        current_price, current_pl_percent, max_gain_percent, max_loss_percent, max_drawdown_percent,
                        time_active, latest_confidence, status, provider, freshness, max_price_reached, min_price_reached,
                        initial_stop_loss, current_trailing_stop, trailing_activated_at, highest_price_since_entry,
                        lowest_price_since_entry, trailing_status, outcome, archived_at, action_at_suggestion, trailing_activated,
                        target_hit_status, stop_loss_hit_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    signal["signal_id"], signal["symbol"], signal["direction"], signal["suggested_time"], signal["suggested_timestamp"],
                    signal["suggested_price"], signal["entry_price"], signal["stop_loss"], signal["target_1"], signal["target_2"],
                    signal["target_3"], signal["initial_confidence"], signal["initial_reason"], signal["current_price"], signal["current_pl_percent"],
                    signal["max_gain_percent"], signal["max_loss_percent"], signal["max_drawdown_percent"], signal["time_active"],
                    signal["latest_confidence"], signal["status"], signal["provider"], signal["freshness"], signal["max_price_reached"],
                    signal["min_price_reached"], signal["initial_stop_loss"], signal["current_trailing_stop"], signal["trailing_activated_at"],
                    signal["highest_price_since_entry"], signal["lowest_price_since_entry"], signal["trailing_status"], signal["outcome"],
                    signal["archived_at"], signal["action_at_suggestion"], 1 if signal["trailing_activated"] else 0,
                    signal["target_hit_status"], signal["stop_loss_hit_status"]
                ))
            logger.info(f"SignalManager: Signal {signal_id} registered and persisted in PostgreSQL for {normalized} at {entry_price}")
        except Exception as e:
            logger.error(f"SignalManager: Failed to insert signal {signal_id} in DB: {e}", exc_info=True)

        return signal

    def update_signal_live_metrics(
        self,
        symbol: str,
        current_price: float,
        latest_confidence: float | None = None,
        latest_analysis: str | None = None,
        provider: str | None = None,
        freshness: str = "LIVE"
    ) -> dict[str, Any] | None:
        """
        Updates live metrics, runs trailing stop checks, and handles signal exits.
        Exposed to continuous live ticks.
        """
        normalized = normalize_stock_symbol(symbol)
        active_signals = self.get_active_signals()
        
        if normalized not in active_signals:
            return None
            
        sugg = active_signals[normalized]
        entry = sugg["entry_price"]
        direction = sugg["direction"]
        
        if entry <= 0:
            return sugg

        # 1. Update current price and extremes
        sugg["current_price"] = current_price
        sugg["currentPrice"] = current_price
        
        # highest/lowest price since entry
        high_since = sugg.get("highest_price_since_entry") or entry
        low_since = sugg.get("lowest_price_since_entry") or entry
        
        if current_price > high_since:
            sugg["highest_price_since_entry"] = current_price
            high_since = current_price
        if current_price < low_since:
            sugg["lowest_price_since_entry"] = current_price
            low_since = current_price
            
        sugg["max_price_reached"] = high_since
        sugg["min_price_reached"] = low_since

        # 2. Compute current PL %
        if direction == "SELL":
            pl_pct = ((entry - current_price) / entry) * 100
            max_gain = ((entry - low_since) / entry) * 100
            max_loss = ((entry - high_since) / entry) * 100
            drawdown = ((current_price - low_since) / low_since) * 100 if low_since > 0 else 0.0
        else: # BUY
            pl_pct = ((current_price - entry) / entry) * 100
            max_gain = ((high_since - entry) / entry) * 100
            max_loss = ((min(entry, low_since) - entry) / entry) * 100
            drawdown = ((high_since - current_price) / high_since) * 100 if high_since > 0 else 0.0

        sugg["current_pl_percent"] = round(pl_pct, 2)
        sugg["currentPLPercent"] = round(pl_pct, 2)
        sugg["max_gain_percent"] = round(max(0.0, max_gain), 2)
        sugg["maxGainPercent"] = round(max(0.0, max_gain), 2)
        sugg["max_loss_percent"] = round(max_loss, 2)
        sugg["max_drawdown_percent"] = round(drawdown, 2)
        sugg["maxLossDrawdownPercent"] = round(drawdown, 2)

        # 3. Compute time active
        elapsed = time.time() - sugg["suggested_timestamp"]
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        time_str = f"{hours:02d}h {minutes:02d}m {seconds:02d}s"
        sugg["time_active"] = time_str
        sugg["timeActive"] = time_str

        # 4. Trailing Stop Activation Checks
        # Activate trailing stop after Target 1 hit OR +1.5% profit
        target1 = sugg["target_1"]
        target2 = sugg["target_2"]
        target3 = sugg["target_3"]
        initial_sl = sugg["initial_stop_loss"]
        prev_trailing = sugg.get("current_trailing_stop") or initial_sl
        
        is_t1_hit = False
        is_t2_hit = False
        is_t3_hit = False
        
        if direction == "BUY":
            is_t1_hit = current_price >= target1
            is_t2_hit = current_price >= target2
            is_t3_hit = current_price >= target3
            profit_pct = pl_pct
        else: # SELL
            is_t1_hit = current_price <= target1
            is_t2_hit = current_price <= target2
            is_t3_hit = current_price <= target3
            profit_pct = pl_pct

        trailing_activated = sugg.get("trailing_activated") or is_t1_hit or profit_pct >= 1.5
        
        # Calculate dynamic trailing stop distance (Default: 0.8%, Target 2 hit: Tightened to 0.5%, for testing: 1.5%)
        trail_percent = 0.015 if "TEST" in symbol.upper() else 0.008
        if is_t2_hit or sugg["trailing_status"] == "Target 2 Hit":
            trail_percent = 0.005
            sugg["trailing_status"] = "Target 2 Hit"
            sugg["trailingStatus"] = "Target 2 Hit"
        elif trailing_activated:
            sugg["trailing_status"] = "Active"
            sugg["trailingStatus"] = "Active"
            
        if is_t1_hit and sugg["trailing_status"] not in ("Target 1 Hit", "Target 2 Hit"):
            sugg["trailing_status"] = "Target 1 Hit"
            sugg["trailingStatus"] = "Target 1 Hit"

        # Apply Trailing stop loss rules
        current_trailing = prev_trailing
        
        if trailing_activated:
            sugg["trailing_activated"] = True
            sugg["trailingActivated"] = True
            if not sugg.get("trailing_activated_at"):
                sugg["trailing_activated_at"] = datetime.now().isoformat()
                sugg["trailingActivatedAt"] = sugg["trailing_activated_at"]
            
            # Trail percent: BUY -> trailing stop rises; SELL -> trailing stop falls
            if direction == "BUY":
                calculated_stop = high_since * (1 - trail_percent)
                # Never move stop loss downward
                current_trailing = max(prev_trailing, calculated_stop)
                
                # Move to entry if Target 1 is hit and current stop is below entry
                if is_t1_hit:
                    current_trailing = max(current_trailing, entry)
            else: # SELL
                calculated_stop = low_since * (1 + trail_percent)
                # Never move stop loss upward
                current_trailing = min(prev_trailing, calculated_stop)
                
                # Move to entry if Target 1 is hit and current stop is above entry
                if is_t1_hit:
                    current_trailing = min(current_trailing, entry)
        else:
            current_trailing = initial_sl

        sugg["current_trailing_stop"] = current_trailing
        sugg["currentTrailingStop"] = current_trailing
        sugg["trailingStop"] = current_trailing

        # 5. Evaluate Target & Stop Loss hits for Exit
        outcome = None
        exit_reason = None
        
        if direction == "BUY":
            if is_t3_hit:
                outcome = "Target Hit"
                exit_reason = "TARGET_3_HIT"
            elif trailing_activated and current_price <= current_trailing:
                outcome = "Closed"
                exit_reason = "TRAILING_STOP_HIT"
            elif not trailing_activated and current_price <= initial_sl:
                outcome = "Stop Loss Hit"
                exit_reason = "STOP_LOSS_HIT"
        else: # SELL
            if is_t3_hit:
                outcome = "Target Hit"
                exit_reason = "TARGET_3_HIT"
            elif trailing_activated and current_price >= current_trailing:
                outcome = "Closed"
                exit_reason = "TRAILING_STOP_HIT"
            elif not trailing_activated and current_price >= initial_sl:
                outcome = "Stop Loss Hit"
                exit_reason = "STOP_LOSS_HIT"

        # Update hit status helpers
        if is_t1_hit:
            sugg["target_hit_status"] = "Target 1 Hit"
            sugg["targetHitStatus"] = "Target 1 Hit"
        if is_t2_hit:
            sugg["target_hit_status"] = "Target 2 Hit"
            sugg["targetHitStatus"] = "Target 2 Hit"
        if is_t3_hit:
            sugg["target_hit_status"] = "Target 3 Hit"
            sugg["targetHitStatus"] = "Target 3 Hit"

        if outcome:
            sugg["status"] = outcome
            sugg["latestStatus"] = outcome
            sugg["outcome"] = exit_reason
            sugg["archived_at"] = datetime.now().isoformat()
            
            # Record stop loss or target hit statuses
            if exit_reason == "STOP_LOSS_HIT":
                sugg["stop_loss_hit_status"] = "Stop Loss Hit"
                sugg["stopLossHitStatus"] = "Stop Loss Hit"
            elif exit_reason == "TRAILING_STOP_HIT":
                sugg["stop_loss_hit_status"] = "Trailing Stop Hit"
                sugg["stopLossHitStatus"] = "Trailing Stop Hit"
        else:
            prev_status = sugg.get("status", "ACTIVE")
            if is_t2_hit or prev_status == "TARGET_2_HIT":
                sugg["status"] = "TARGET_2_HIT"
            elif is_t1_hit or prev_status == "TARGET_1_HIT":
                sugg["status"] = "TARGET_1_HIT"
            else:
                sugg["status"] = "ACTIVE"
            sugg["latestStatus"] = sugg["status"]

        if latest_confidence is not None:
            sugg["latest_confidence"] = latest_confidence
            sugg["latestConfidence"] = latest_confidence
        if latest_analysis is not None:
            sugg["latest_analysis"] = latest_analysis
        if provider is not None:
            sugg["provider"] = provider
        sugg["freshness"] = freshness
        sugg["dataFreshness"] = freshness

        # Expose extra metrics needed by client
        sugg["targetHitStatus"] = sugg.get("target_hit_status", "None")
        sugg["stopLossHitStatus"] = sugg.get("stop_loss_hit_status", "None")

        # Save updates to DB
        try:
            with connect() as conn:
                conn.execute("""
                    UPDATE signal_records SET
                        current_price = ?, current_pl_percent = ?, max_gain_percent = ?, max_loss_percent = ?, max_drawdown_percent = ?,
                        time_active = ?, latest_confidence = ?, status = ?, provider = ?, freshness = ?, max_price_reached = ?,
                        min_price_reached = ?, current_trailing_stop = ?, trailing_activated_at = ?, highest_price_since_entry = ?,
                        lowest_price_since_entry = ?, trailing_status = ?, outcome = ?, archived_at = ?, trailing_activated = ?,
                        target_hit_status = ?, stop_loss_hit_status = ?
                    WHERE signal_id = ?
                """, (
                    sugg["current_price"], sugg["current_pl_percent"], sugg["max_gain_percent"], sugg["max_loss_percent"], sugg["max_drawdown_percent"],
                    sugg["time_active"], sugg["latest_confidence"], sugg["status"], sugg["provider"], sugg["freshness"], sugg["max_price_reached"],
                    sugg["min_price_reached"], sugg["current_trailing_stop"], sugg["trailing_activated_at"], sugg["highest_price_since_entry"],
                    sugg["lowest_price_since_entry"], sugg["trailing_status"], sugg["outcome"], sugg["archived_at"], 1 if sugg["trailing_activated"] else 0,
                    sugg["target_hit_status"], sugg["stop_loss_hit_status"], sugg["signal_id"]
                ))
            if outcome:
                logger.info(f"SignalManager: Signal {sugg['signal_id']} exited with {exit_reason} (outcome: {outcome}) at exit price {current_price}")
        except Exception as e:
            logger.error(f"SignalManager: Failed to update signal {sugg['signal_id']} in DB: {e}")

        return sugg

    def manual_close_signal(self, symbol: str) -> bool:
        """
        Manually closes an active signal.
        """
        normalized = normalize_stock_symbol(symbol)
        active = self.get_active_signals()
        if normalized not in active:
            return False
        sugg = active[normalized]
        sugg["status"] = "CLOSED"
        sugg["latestStatus"] = "Closed"
        sugg["outcome"] = "MANUAL_CLOSE"
        sugg["archived_at"] = datetime.now().isoformat()
        try:
            with connect() as conn:
                conn.execute("""
                    UPDATE signal_records SET
                        status = ?, outcome = ?, archived_at = ?
                    WHERE signal_id = ?
                """, (sugg["status"], sugg["outcome"], sugg["archived_at"], sugg["signal_id"]))
            logger.info(f"SignalManager: Manually closed signal {sugg['signal_id']} for {normalized}")
            return True
        except Exception as e:
            logger.error(f"SignalManager: Failed to manually close signal {sugg['signal_id']}: {e}")
            return False

    def clear_all_signals(self) -> None:
        """
        Clears all signals from the database. Useful for testing.
        """
        try:
            with connect() as conn:
                conn.execute("DELETE FROM signal_records")
            logger.info("SignalManager: Cleared all signals from PostgreSQL.")
        except Exception as e:
            logger.error(f"SignalManager: Failed to clear signals from DB: {e}")

signal_manager = SignalManager()

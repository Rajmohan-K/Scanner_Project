from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from ui.stock_data_service import normalize_stock_symbol, stock_data_service
from utils.logger import logger
from utils.telegram import TelegramDeliveryError, send_telegram_messages


DATA_DIR = Path(__file__).resolve().parent / "data"
WATCHLIST_PATH = DATA_DIR / "watchlist_monitor.json"
ALERTS_PATH = DATA_DIR / "alert_history.json"
SETTINGS_PATH = DATA_DIR / "alert_settings.json"
WATCHLIST_AUDIT_PATH = DATA_DIR / "watchlist_audit_history.json"


DEFAULT_ALERT_SETTINGS: dict[str, Any] = {
    "desktop_enabled": True,
    "sound_enabled": True,
    "sound_type": "soft",
    "sound_volume": 35,
    "telegram_enabled": False,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "breakout_distance_pct": 2.0,
    "breakout_volume_multiplier": 2.0,
    "consecutive_candle_count": 3,
    "price_move_pct_threshold": 2.0,
    "half_percent_move_threshold": 0.5,
    "cooldown_seconds": 900,
    "intraday_monitoring": True,
    "swing_monitoring": True,
    "monitoring_interval_seconds": 10,
    "market_hours_only": False,
    "severity_filter": "all",
    "watchlist_monitoring_enabled": True,
    "groww_source_enabled": True,
    "no_breakout_first_30_minutes": True,
    "first_30_minutes_wait_until": "09:45",
    "wait_until_11am_confirmation": True,
    "confirmation_wait_until": "11:00",
    "stop_loss_min_pct": 1.0,
    "stop_loss_max_pct": 1.5,
    "default_stop_loss_pct": 1.2,
    "profit_booking_start_pct": 4.0,
    "profit_booking_end_pct": 5.0,
    "book_partial_quantity_pct": 50.0,
    "gtt_plan_enabled": True,
    "future_auto_trade_enabled": False,
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_json(path: Path, default: Any) -> Any:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_price(value: Any) -> str:
    number = _num(value)
    return f"{number:.2f}" if number else "-"


def _round_price(value: Any) -> float | None:
    number = _num(value)
    return round(number, 2) if number > 0 else None


class WatchlistMonitor:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.alerts: list[dict[str, Any]] = []
        self.audit_history: list[dict[str, Any]] = []
        self.settings: dict[str, Any] = {}
        self.status: dict[str, Any] = {"running": False, "last_checked": "", "enabled_symbols": 0}
        self.last_triggered: dict[str, float] = {}
        self._pending_alerts: list[dict[str, Any]] = []
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self.load()

    def load(self) -> None:
        raw_items = _read_json(WATCHLIST_PATH, [])
        self.items = {normalize_stock_symbol(row.get("symbol")): row for row in raw_items if row.get("symbol")}
        self.alerts = _read_json(ALERTS_PATH, [])
        self.audit_history = _read_json(WATCHLIST_AUDIT_PATH, [])
        self.settings = {**DEFAULT_ALERT_SETTINGS, **_read_json(SETTINGS_PATH, {})}

    def persist_items(self) -> None:
        _write_json(WATCHLIST_PATH, list(self.items.values()))

    def persist_alerts(self) -> None:
        _write_json(ALERTS_PATH, self.alerts[-500:])

    def persist_audit_history(self) -> None:
        _write_json(WATCHLIST_AUDIT_PATH, self.audit_history[-500:])

    def persist_settings(self) -> None:
        _write_json(SETTINGS_PATH, self.settings)

    def drain_pending_alerts(self) -> list[dict[str, Any]]:
        pending = list(self._pending_alerts)
        self._pending_alerts.clear()
        return pending

    def clear_alerts(self) -> None:
        self.alerts.clear()
        self._pending_alerts.clear()
        self.last_triggered.clear()
        self.persist_alerts()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._worker(), name="watchlist-monitor")

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    def list_items(self) -> list[dict[str, Any]]:
        return sorted(self.items.values(), key=lambda row: row.get("created_at", ""), reverse=False)

    async def add_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        symbol = normalize_stock_symbol(payload.get("symbol") or payload.get("name"))
        if not symbol:
            raise ValueError("symbol is required")
        stock = await stock_data_service.get_stock(symbol, allow_stale=True)
        now = _now()
        existing = self.items.get(symbol, {})
        item = {
            "symbol": symbol,
            "company_name": payload.get("company_name") or stock.get("name") or existing.get("company_name") or symbol,
            "exchange": payload.get("exchange") or stock.get("exchange") or existing.get("exchange") or "NSE",
            "monitoring_enabled": payload.get("monitoring_enabled", existing.get("monitoring_enabled", True)),
            "alerts_enabled": payload.get("alerts_enabled", existing.get("alerts_enabled", True)),
            "telegram_enabled": payload.get("telegram_enabled", existing.get("telegram_enabled", False)),
            "desktop_enabled": payload.get("desktop_enabled", existing.get("desktop_enabled", True)),
            "sound_enabled": payload.get("sound_enabled", existing.get("sound_enabled", False)),
            "notes": payload.get("notes", existing.get("notes", "")),
            "settings": {**existing.get("settings", {}), **payload.get("settings", {})},
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
            "last_checked": existing.get("last_checked", ""),
            "last_alert": existing.get("last_alert", ""),
            "snapshot": existing.get("snapshot", {}),
        }
        self.items[symbol] = item
        self.persist_items()
        stock_data_service.tracked_symbols.add(symbol)
        try:
            await self._analyze_item(item)
            item = self.items.get(symbol, item)
        except Exception as exc:
            item["snapshot"] = self._unavailable_snapshot(item, str(exc))
            item["last_checked"] = _now()
            item["updated_at"] = _now()
            item["monitoring_enabled"] = False
            self.items[symbol] = item
            self.persist_items()
        return item

    def remove_item(self, symbol: str) -> bool:
        normalized = normalize_stock_symbol(symbol)
        removed = self.items.pop(normalized, None) is not None
        if removed:
            self.persist_items()
        return removed

    async def update_item(self, symbol: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_stock_symbol(symbol)
        if normalized not in self.items:
            await self.add_item({"symbol": normalized})
        current = self.items[normalized]
        if "settings" in payload and isinstance(payload["settings"], dict):
            current["settings"] = {**current.get("settings", {}), **payload["settings"]}
        for key in (
            "monitoring_enabled",
            "alerts_enabled",
            "telegram_enabled",
            "desktop_enabled",
            "sound_enabled",
            "notes",
            "custom_breakout_price",
            "custom_support",
            "custom_resistance",
            "custom_price_up_pct",
            "custom_price_down_pct",
            "custom_candle_count",
            "intraday_alerts_enabled",
            "swing_alerts_enabled",
            "quantity_placeholder",
            "risk_amount_placeholder",
            "manual_trade_taken",
        ):
            if key in payload:
                current[key] = payload[key]
        current["updated_at"] = _now()
        self.items[normalized] = current
        self.persist_items()
        return current

    def get_settings(self) -> dict[str, Any]:
        return dict(self.settings)

    def update_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        for key, value in payload.items():
            if key in DEFAULT_ALERT_SETTINGS or key.startswith("telegram_"):
                self.settings[key] = False if key == "future_auto_trade_enabled" else value
        self.settings["future_auto_trade_enabled"] = False
        self.persist_settings()
        return self.get_settings()

    def alert_history(
        self,
        symbol: str = "",
        alert_type: str = "",
        severity: str = "",
        action: str = "",
        date: str = "",
        telegram_sent: str = "",
        trade_taken: str = "",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        rows = list(reversed(self.alerts))
        if symbol:
            rows = [row for row in rows if row.get("symbol") == normalize_stock_symbol(symbol)]
        if alert_type:
            rows = [row for row in rows if row.get("alert_type") == alert_type]
        if severity:
            rows = [row for row in rows if row.get("severity") == severity]
        if action:
            rows = [row for row in rows if str(row.get("action") or "").upper() == action.upper()]
        if date:
            rows = [row for row in rows if str(row.get("created_at") or "").startswith(date)]
        if telegram_sent:
            expected = telegram_sent.lower() in {"1", "true", "yes", "sent"}
            rows = [row for row in rows if bool(row.get("telegram_sent")) == expected]
        if trade_taken:
            expected = trade_taken.lower() in {"1", "true", "yes", "taken"}
            rows = [row for row in rows if bool(row.get("user_marked_as_taken") or row.get("user_action") == "taken") == expected]
        return rows[:limit]

    async def _worker(self) -> None:
        while True:
            try:
                await self.monitor_once()
            except Exception as exc:
                logger.warning(f"Watchlist monitor cycle failed: {exc}")
            await asyncio.sleep(max(3, int(_num(self.settings.get("monitoring_interval_seconds"), 10))))

    async def monitor_once(self) -> dict[str, Any]:
        # Auto-fetch Groww stocks if option is enabled
        now_ts = time.time()
        if self.settings.get("groww_source_enabled", False) and (now_ts - getattr(self, "last_groww_fetch", 0) > 300):
            self.last_groww_fetch = now_ts
            try:
                from ui.app import _fetch_groww_intraday_rows
                payload = _fetch_groww_intraday_rows(limit=40)
                rows = payload.get("rows", [])
                symbols_to_add = [row["symbol"] for row in rows if row.get("symbol")]
                if symbols_to_add:
                    logger.info(f"Auto-importing {len(symbols_to_add)} symbols from Groww source to watchlist")
                    for symbol in symbols_to_add:
                        if symbol not in self.items:
                            item_payload = {
                                "symbol": symbol,
                                "monitoring_enabled": True,
                                "alerts_enabled": True,
                                "settings": {"suggested_time": "After VWAP/volume confirmation; avoid fresh entry near close"}
                            }
                            await self.add_item(item_payload)
            except Exception as exc:
                logger.warning(f"Failed to auto-fetch stocks from Groww source: {exc}")

        enabled = [row for row in self.items.values() if row.get("monitoring_enabled", True)]
        self.status = {"running": bool(enabled), "last_checked": _now(), "enabled_symbols": len(enabled)}
        if not enabled:
            return self.status
        semaphore = asyncio.Semaphore(8)

        async def analyze(row: dict[str, Any]) -> None:
            async with semaphore:
                try:
                    await self._analyze_item(row)
                except Exception as exc:
                    symbol = row.get("symbol", "")
                    logger.debug(f"Watchlist analysis failed for {symbol}: {exc}")

        await asyncio.gather(*(analyze(row) for row in enabled), return_exceptions=True)
        self.persist_items()
        self.persist_alerts()
        return self.status

    async def _analyze_item(self, item: dict[str, Any]) -> None:
        symbol = normalize_stock_symbol(item.get("symbol"))
        analysis = await stock_data_service.get_analysis(symbol, allow_stale=True)
        if analysis.get("status") == "error":
            message = analysis.get("message") or "Stock data unavailable"
            item["snapshot"] = self._unavailable_snapshot(item, message)
            item["last_checked"] = _now()
            item["updated_at"] = _now()
            # Disable monitoring for invalid, delisted, or missing stocks to prevent continuous polling
            msg_lower = message.lower()
            if any(term in msg_lower for term in ("delisted", "not found", "invalid", "unavailable", "no candle data", "no market data")):
                item["monitoring_enabled"] = False
                logger.warning(f"Automatically disabled monitoring for {symbol} due to persistent data error: {message}")
            self.items[symbol] = item
            return
        stock = analysis.get("stock") or await stock_data_service.get_stock(symbol, allow_stale=True)
        quote = analysis.get("quote") or stock.get("quote") or {}
        candles = await stock_data_service.get_candles(symbol, "1D", allow_stale=True)
        snapshot = self._build_snapshot(item, stock, analysis, candles.get("candles") or [])
        item["snapshot"] = snapshot
        item["last_checked"] = _now()
        item["updated_at"] = _now()
        self.items[symbol] = item
        for alert in self._evaluate_alerts(item, snapshot):
            await self._record_alert(item, alert)
        await self._check_and_archive_hit(item, snapshot)

    def _build_snapshot(self, item: dict[str, Any], stock: dict[str, Any], analysis: dict[str, Any], candles: list[dict[str, Any]]) -> dict[str, Any]:
        quote = analysis.get("quote") or stock.get("quote") or {}
        price = _num(quote.get("current_price"))
        indicators = analysis.get("indicators") or {}
        resistance_levels = analysis.get("resistance_levels") or []
        support_levels = analysis.get("support_levels") or []
        resistance = _num(item.get("custom_resistance") or item.get("settings", {}).get("resistance") or (resistance_levels[-1] if resistance_levels else 0))
        support = _num(item.get("custom_support") or item.get("settings", {}).get("support") or (support_levels[-1] if support_levels else 0))
        breakout_level = _num(item.get("custom_breakout_price") or item.get("settings", {}).get("breakout_price") or resistance)
        distance = ((breakout_level - price) / breakout_level * 100) if breakout_level else 0
        volume_ratio = _num((analysis.get("volume_analysis") or {}).get("relative_volume"), 1)
        current_status = self._status_from_analysis(price, breakout_level, support, analysis, volume_ratio, distance)
        confidence = _num(analysis.get("confidence") or (analysis.get("master_analysis") or {}).get("confidence_percent") or 0)
        intraday_signal = str((analysis.get("intraday") or {}).get("recommendation") or analysis.get("intraday_view") or "WATCH").upper()
        swing_signal = str((analysis.get("swing") or {}).get("recommendation") or analysis.get("swing_view") or "WATCH").upper()
        risk = analysis.get("risk") or (analysis.get("master_analysis") or {}).get("risk_analysis", {}).get("riskRating") or ("High" if intraday_signal == "AVOID" and swing_signal == "AVOID" else "Medium")
        trade_state = self._trade_state(item, analysis, price, breakout_level, support, resistance, volume_ratio, distance, intraday_signal, confidence, risk)
        return {
            "symbol": item.get("symbol"),
            "company_name": item.get("company_name") or stock.get("name"),
            "exchange": item.get("exchange") or stock.get("exchange"),
            "current_price": price,
            "price_change_pct": _num(quote.get("change_pct")),
            "volume_spike": volume_ratio,
            "trend": analysis.get("trend") or "Unavailable",
            "breakout_level": breakout_level,
            "expected_breakout_price": breakout_level,
            "distance_to_breakout_pct": round(distance, 2),
            "current_status": current_status,
            "intraday_signal": intraday_signal,
            "swing_signal": swing_signal,
            "risk": risk,
            "confidence": round(confidence, 2),
            "last_alert": item.get("last_alert", ""),
            "last_alert_price": item.get("last_alert_price"),
            "last_checked": item.get("last_checked", ""),
            "support": support,
            "resistance": resistance,
            "vwap": indicators.get("vwap"),
            "ema20": indicators.get("ema20"),
            "ema50": indicators.get("ema50"),
            "ema200": indicators.get("ema200"),
            "reason": analysis.get("finalExplanation") or analysis.get("reason", ""),
            "candles": candles[-10:],
            "stale": bool(analysis.get("stale") or stock.get("stale")),
            **trade_state,
        }

    def _unavailable_snapshot(self, item: dict[str, Any], message: str) -> dict[str, Any]:
        return {
            "symbol": item.get("symbol"),
            "company_name": item.get("company_name") or item.get("symbol"),
            "exchange": item.get("exchange") or "NSE",
            "current_price": None,
            "price_change_pct": None,
            "volume_spike": None,
            "trend": "Unavailable",
            "breakout_level": None,
            "expected_breakout_price": None,
            "distance_to_breakout_pct": None,
            "current_status": "Unavailable",
            "intraday_signal": "UNAVAILABLE",
            "swing_signal": "UNAVAILABLE",
            "risk": "Unavailable",
            "confidence": 0,
            "last_alert": item.get("last_alert", ""),
            "last_alert_price": item.get("last_alert_price"),
            "last_checked": _now(),
            "support": None,
            "resistance": None,
            "vwap": None,
            "ema20": None,
            "ema50": None,
            "ema200": None,
            "reason": message or "Stock data unavailable",
            "candles": [],
            "stale": True,
            "trade_readiness": "Avoid",
            "action": "AVOID",
            "entry": None,
            "stop_loss": None,
            "target1": None,
            "target2": None,
            "target3": None,
            "gtt_plan": None,
            "profit_booking_status": "Unavailable",
            "suggested_time": "Unavailable",
            "manual_confirmation_required": True,
            "auto_trade_enabled": False,
        }

    def _trade_state(
        self,
        item: dict[str, Any],
        analysis: dict[str, Any],
        price: float,
        breakout_level: float,
        support: float,
        resistance: float,
        volume_ratio: float,
        distance: float,
        intraday_signal: str,
        confidence: float,
        risk: str,
    ) -> dict[str, Any]:
        now = datetime.now().time()
        wait_first_30 = bool(self.settings.get("no_breakout_first_30_minutes", True)) and now < datetime.strptime(str(self.settings.get("first_30_minutes_wait_until") or "09:45"), "%H:%M").time()
        wait_11am = bool(self.settings.get("wait_until_11am_confirmation", True)) and now < datetime.strptime(str(self.settings.get("confirmation_wait_until") or "11:00"), "%H:%M").time()
        min_volume = _num(self.settings.get("breakout_volume_multiplier"), 2.0)
        sl_min = _num(self.settings.get("stop_loss_min_pct"), 1.0)
        sl_max = _num(self.settings.get("stop_loss_max_pct"), 1.5)
        sl_pct = min(max(_num(self.settings.get("default_stop_loss_pct"), 1.2), sl_min), sl_max)
        entry = _round_price(max(price, breakout_level) if breakout_level and price >= breakout_level else price)
        stop_loss = _round_price((entry or price) * (1 - sl_pct / 100)) if entry else None
        target1 = _round_price((entry or price) * 1.02) if entry else None
        target2 = _round_price((entry or price) * 1.04) if entry else None
        target3 = _round_price((entry or price) * 1.06) if entry else None
        trade_plan = (analysis.get("intraday") or {}).get("tradePlan") or analysis.get("intraday_trade_plan") or {}
        if intraday_signal == "BUY":
            entry = _round_price(trade_plan.get("entry_price") or trade_plan.get("entry_trigger") or entry)
            stop_loss = _round_price(trade_plan.get("stop_loss") or stop_loss)
            target1 = _round_price(trade_plan.get("target1") or target1)
            target2 = _round_price(trade_plan.get("target2") or target2)
            target3 = _round_price(trade_plan.get("target3") or target3)
        risk_pct = ((entry - stop_loss) / entry * 100) if entry and stop_loss else 999
        volume_ok = volume_ratio >= min_volume
        above_vwap = price >= _num((analysis.get("indicators") or {}).get("vwap"))
        above_support = support <= 0 or price >= support
        above_resistance = breakout_level > 0 and price >= breakout_level
        near_breakout = breakout_level > 0 and 0 <= distance <= _num(self.settings.get("breakout_distance_pct"), 2.0)
        reason_parts: list[str] = []
        readiness = "Not Ready"
        action = "WATCH"
        time_rule_status = "Ready"
        if intraday_signal == "AVOID":
            readiness = "Avoid"
            action = "AVOID"
            reason_parts.append("Centralized intraday analysis is AVOID")
        elif wait_first_30 and (near_breakout or above_resistance):
            readiness = "Opening Volatility - Wait"
            action = "WAIT"
            time_rule_status = "Opening volatility - wait"
            reason_parts.append("No breakout buy before configured opening wait window ends")
        elif wait_11am and price >= _num((analysis.get("indicators") or {}).get("vwap")) and price >= support:
            readiness = "Waiting Until 11 AM"
            action = "WAIT"
            time_rule_status = "Momentum seen, waiting for 11 AM confirmation"
            reason_parts.append("Momentum seen, waiting for 11 AM confirmation")
        elif not volume_ok:
            readiness = "Volume Pending"
            action = "ALERT ONLY"
            reason_parts.append(f"Volume {volume_ratio:.2f}x is below required {min_volume:.2f}x")
        elif risk_pct > sl_max:
            readiness = "Avoid"
            action = "AVOID"
            reason_parts.append(f"Stop loss risk {risk_pct:.2f}% exceeds max {sl_max:.2f}%")
        elif above_resistance and above_vwap and above_support:
            readiness = "Trade Ready"
            action = "BUY READY"
            reason_parts.append("Breakout confirmed with VWAP/support hold and volume confirmation")
        elif near_breakout:
            readiness = "Near Breakout"
            action = "WATCH"
            reason_parts.append("Near breakout, confirmation pending")
        elif intraday_signal == "BUY":
            readiness = "Breakout Confirmed" if volume_ok else "Volume Pending"
            action = "BUY READY" if volume_ok else "ALERT ONLY"
            reason_parts.append("Centralized intraday analysis is BUY")
        else:
            readiness = "Not Ready"
            action = "WATCH"
            reason_parts.append("Centralized intraday analysis is WATCH")
        entry_price = _num(item.get("entry_price") or item.get("last_trade_entry") or entry)
        profit_pct = ((price - entry_price) / entry_price * 100) if entry_price else 0
        book_start = _num(self.settings.get("profit_booking_start_pct"), 4)
        book_end = _num(self.settings.get("profit_booking_end_pct"), 5)
        profit_booking_status = "Not started"
        if profit_pct >= book_start and item.get("partial_booked"):
            readiness = "Trade Ready"
            action = "TRAIL SL"
            profit_booking_status = "Trailing SL active"
        elif profit_pct >= book_start:
            action = "BOOK 50%"
            profit_booking_status = f"Book {self.settings.get('book_partial_quantity_pct', 50)}% profit"
        elif profit_pct > 0:
            profit_booking_status = f"{profit_pct:.2f}% open gain"
        gtt_plan = None
        if self.settings.get("gtt_plan_enabled", True) and entry and stop_loss and target1:
            gtt_plan = {
                "entry": entry,
                "stop_loss": stop_loss,
                "target1": target1,
                "target2": target2,
                "target3": target3,
                "quantity_placeholder": item.get("quantity_placeholder") or "",
                "risk_amount_placeholder": item.get("risk_amount_placeholder") or "",
                "note": "Use Groww GTT manually for Target/SL",
            }
        suggested_time = item.get("suggested_time") or item.get("settings", {}).get("suggested_time")
        if not suggested_time:
            first_ends = self.settings.get("first_30_minutes_wait_until") or "09:45"
            confirm_after = self.settings.get("confirmation_wait_until") or "11:00"
            if self.settings.get("wait_until_11am_confirmation", True):
                suggested_time = f"After {confirm_after} (11 AM confirmation window)"
            elif self.settings.get("no_breakout_first_30_minutes", True):
                suggested_time = f"After {first_ends} (opening wait window)"
            else:
                suggested_time = "09:15 - 11:30 (Opening momentum window)"
        return {
            "trade_readiness": readiness,
            "action": action,
            "time_rule_status": time_rule_status,
            "volume_confirmed": volume_ok,
            "entry": entry if action != "AVOID" else None,
            "stop_loss": stop_loss if action != "AVOID" else None,
            "target1": target1 if action != "AVOID" else None,
            "target2": target2 if action != "AVOID" else None,
            "target3": target3 if action != "AVOID" else None,
            "gtt_plan": gtt_plan if action != "AVOID" else None,
            "profit_booking_status": profit_booking_status,
            "suggested_time": suggested_time,
            "manual_confirmation_required": True,
            "auto_trade_enabled": False,
            "trade_reason": "; ".join(reason_parts),
            "risk_percent": round(risk_pct, 2) if risk_pct < 999 else None,
            "risk": risk,
            "confidence": round(confidence, 2),
        }

    def _status_from_analysis(self, price: float, breakout_level: float, support: float, analysis: dict[str, Any], volume_ratio: float, distance: float) -> str:
        breakout_status = analysis.get("breakout_status")
        if support and price < support:
            return "Breakdown Risk"
        if breakout_level and price > breakout_level and volume_ratio >= _num(self.settings.get("breakout_volume_multiplier"), 1.5):
            return "Just Breakout"
        if breakout_status == "About to breakout":
            return "About To Breakout"
        if 0 <= distance <= _num(self.settings.get("breakout_distance_pct"), 2):
            return "Near Breakout"
        if breakout_status == "Rejected":
            return "Failed Breakout"
        if analysis.get("trend") == "Sideways":
            return "Consolidating"
        if analysis.get("trend") == "Bearish":
            return "Avoid"
        return "Pullback" if price < _num((analysis.get("indicators") or {}).get("ema20")) else "Consolidating"

    def _evaluate_alerts(self, item: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        if not item.get("alerts_enabled", True):
            return []
        alerts: list[dict[str, Any]] = []
        symbol = item.get("symbol")
        price = _num(snapshot.get("current_price"))
        if not price:
            return []
        breakout_level = _num(snapshot.get("breakout_level"))
        support = _num(snapshot.get("support"))
        distance = _num(snapshot.get("distance_to_breakout_pct"))
        volume_spike = _num(snapshot.get("volume_spike"), 1)
        candles = snapshot.get("candles") or []
        breakout_distance = _num(item.get("settings", {}).get("breakout_distance_pct"), _num(self.settings.get("breakout_distance_pct"), 2))
        volume_confirm = _num(self.settings.get("breakout_volume_multiplier"), 2.0)
        action = str(snapshot.get("action") or "WATCH")
        readiness = str(snapshot.get("trade_readiness") or "Not Ready")
        trade_reason = str(snapshot.get("trade_reason") or snapshot.get("reason") or "")
        if readiness == "Opening Volatility - Wait":
            alerts.append(self._alert(symbol, "OPENING_VOLATILITY_WAIT", "low", price, breakout_level, trade_reason, action="WAIT", snapshot=snapshot))
        if readiness == "Waiting Until 11 AM":
            alerts.append(self._alert(symbol, "BREAKOUT_AFTER_11AM", "medium", price, breakout_level, trade_reason, action="WAIT", snapshot=snapshot))
        if readiness == "Volume Pending":
            alerts.append(self._alert(symbol, "VOLUME_NOT_CONFIRMED", "low", price, breakout_level, trade_reason, action="ALERT ONLY", snapshot=snapshot))
        if bool(snapshot.get("volume_confirmed")):
            alerts.append(self._alert(symbol, "VOLUME_2X_CONFIRMED", "medium", price, breakout_level, f"{symbol} volume is {volume_spike:.2f}x average.", action="WATCH", snapshot=snapshot))
        if breakout_level and 0 <= distance <= breakout_distance:
            alerts.append(self._alert(symbol, "NEAR_BREAKOUT", "medium", price, breakout_level, f"{symbol} is {distance:.2f}% from breakout level {_format_price(breakout_level)}.", action="WATCH", snapshot=snapshot))
        if breakout_level and price > breakout_level and volume_spike >= volume_confirm:
            alert_type = "BREAKOUT_AFTER_11AM" if not str(snapshot.get("time_rule_status") or "").startswith("Momentum seen") else "BREAKOUT_CONFIRMED"
            alerts.append(self._alert(symbol, alert_type, "high", price, breakout_level, f"{symbol} broke above {_format_price(breakout_level)} with {volume_spike:.2f}x volume.", action=action, snapshot=snapshot))
        if action == "BUY READY" and snapshot.get("gtt_plan"):
            alerts.append(self._alert(symbol, "GTT_PLAN_READY", "high", price, breakout_level, "Trade-ready alert generated. Use Groww GTT manually for Target/SL.", action=action, snapshot=snapshot))
        if action == "BOOK 50%":
            alerts.append(self._alert(symbol, "BOOK_50_PERCENT_PROFIT", "high", price, breakout_level, str(snapshot.get("profit_booking_status") or "Book partial profit."), action=action, snapshot=snapshot))
        if action == "TRAIL SL":
            alerts.append(self._alert(symbol, "TRAIL_SL_UPDATE", "medium", price, breakout_level, "Trail stop loss for remaining quantity.", action=action, snapshot=snapshot))
        if support and price < support:
            alerts.append(self._alert(symbol, "STOP_LOSS_HIT_WARNING", "high", price, breakout_level, f"{symbol} broke below support {_format_price(support)}.", action="EXIT", snapshot=snapshot))
        if snapshot.get("current_status") == "Failed Breakout":
            alerts.append(self._alert(symbol, "BREAKOUT_FAILED", "medium", price, breakout_level, f"{symbol} failed breakout confirmation.", action="AVOID", snapshot=snapshot))
        if action == "AVOID":
            alerts.append(self._alert(symbol, "AVOID_TRADE", "low", price, breakout_level, trade_reason or f"{symbol} is not trade-ready.", action="AVOID", snapshot=snapshot))
        gtt = snapshot.get("gtt_plan") or {}
        for label, alert_type in (("target1", "TARGET_1_REACHED"), ("target2", "TARGET_2_REACHED"), ("target3", "TARGET_3_REACHED")):
            target = _num(gtt.get(label) or snapshot.get(label))
            if target and price >= target:
                alerts.append(self._alert(symbol, alert_type, "high", price, breakout_level, f"{symbol} reached {label.upper()} {_format_price(target)}.", action="BOOK 50%" if label == "target1" else "TRAIL SL", snapshot=snapshot))
        alerts.extend(self._candle_alerts(symbol, price, breakout_level, candles, item))
        half_move_threshold = _num(self.settings.get("half_percent_move_threshold"), 0.5)
        last_alert_price = _num(item.get("last_alert_price") or snapshot.get("last_alert_price"))
        if last_alert_price:
            half_move = (price - last_alert_price) / last_alert_price * 100
            if half_move >= half_move_threshold:
                alerts.append(self._alert(symbol, "PRICE_UP_0_5_PERCENT", "medium", price, breakout_level, f"{symbol} moved up {half_move:.2f}% from last alert price.", action="WATCH", snapshot=snapshot, percentage_move=round(half_move, 2), last_alert_price=last_alert_price))
            if half_move <= -abs(half_move_threshold):
                alerts.append(self._alert(symbol, "PRICE_DOWN_0_5_PERCENT", "medium", price, breakout_level, f"{symbol} moved down {half_move:.2f}% from last alert price.", action="WATCH", snapshot=snapshot, percentage_move=round(half_move, 2), last_alert_price=last_alert_price))
        price_move = _num(item.get("custom_price_up_pct") or self.settings.get("price_move_pct_threshold"), 2)
        previous = _num((candles[-2] or {}).get("close")) if len(candles) > 1 else 0
        if previous:
            move_pct = (price - previous) / previous * 100
            if move_pct >= price_move:
                alerts.append(self._alert(symbol, "PRICE_UP_0_5_PERCENT", "medium", price, breakout_level, f"{symbol} moved up {move_pct:.2f}% from previous candle.", action="WATCH", snapshot=snapshot, percentage_move=round(move_pct, 2)))
            if move_pct <= -abs(_num(item.get("custom_price_down_pct") or price_move)):
                alerts.append(self._alert(symbol, "PRICE_DOWN_0_5_PERCENT", "medium", price, breakout_level, f"{symbol} moved down {move_pct:.2f}% from previous candle.", action="WATCH", snapshot=snapshot, percentage_move=round(move_pct, 2)))
        return alerts

    def _candle_alerts(self, symbol: str, price: float, breakout_level: float, candles: list[dict[str, Any]], item: dict[str, Any]) -> list[dict[str, Any]]:
        count = int(_num(item.get("custom_candle_count") or self.settings.get("consecutive_candle_count"), 3))
        if len(candles) < count:
            return []
        recent = candles[-count:]
        closes = [_num(row.get("close")) for row in recent]
        opens = [_num(row.get("open")) for row in recent]
        volumes = [_num(row.get("volume")) for row in recent]
        rising = all(closes[index] > closes[index - 1] for index in range(1, len(closes)))
        falling = all(closes[index] < closes[index - 1] for index in range(1, len(closes)))
        increasing_volume = all(volumes[index] >= volumes[index - 1] for index in range(1, len(volumes)))
        bullish = all(closes[index] > opens[index] for index in range(len(closes)))
        bearish = all(closes[index] < opens[index] for index in range(len(closes)))
        alerts: list[dict[str, Any]] = []
        if rising:
            alerts.append(self._alert(symbol, "NEAR_BREAKOUT", "medium", price, breakout_level, f"{symbol} has {count} consecutive rising candles.", action="WATCH"))
        if falling:
            alerts.append(self._alert(symbol, "AVOID_TRADE", "medium", price, breakout_level, f"{symbol} has {count} consecutive falling candles.", action="AVOID"))
        if rising and increasing_volume:
            alerts.append(self._alert(symbol, "VOLUME_2X_CONFIRMED", "high", price, breakout_level, f"{symbol} is rising for {count} candles with increasing volume.", action="WATCH"))
        if falling and increasing_volume:
            alerts.append(self._alert(symbol, "AVOID_TRADE", "high", price, breakout_level, f"{symbol} is falling for {count} candles with increasing volume.", action="AVOID"))
        if bullish:
            alerts.append(self._alert(symbol, "NEAR_BREAKOUT", "medium", price, breakout_level, f"{symbol} printed {count} bullish candles.", action="WATCH"))
        if bearish:
            alerts.append(self._alert(symbol, "AVOID_TRADE", "medium", price, breakout_level, f"{symbol} printed {count} bearish candles.", action="AVOID"))
        return alerts

    def _alert(self, symbol: str, alert_type: str, severity: str, price: float, breakout_level: float, reason: str, action: str = "WATCH", snapshot: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
        snapshot = snapshot or {}
        gtt = snapshot.get("gtt_plan") or {}
        return {
            "symbol": symbol,
            "alert_type": alert_type,
            "action": action,
            "severity": severity,
            "trigger_price": round(price, 2),
            "last_alert_price": extra.get("last_alert_price") or snapshot.get("last_alert_price"),
            "percentage_move": extra.get("percentage_move"),
            "breakout_level": round(breakout_level, 2) if breakout_level else None,
            "message": reason,
            "reason": reason,
            "entry": gtt.get("entry") or snapshot.get("entry"),
            "stop_loss": gtt.get("stop_loss") or snapshot.get("stop_loss"),
            "target1": gtt.get("target1") or snapshot.get("target1"),
            "target2": gtt.get("target2") or snapshot.get("target2"),
            "target3": gtt.get("target3") or snapshot.get("target3"),
            "volume_ratio": snapshot.get("volume_spike"),
            "volume_confirmation": snapshot.get("volume_confirmed"),
            "time_rule_status": snapshot.get("time_rule_status"),
            "gtt_plan": gtt or None,
            "risk": snapshot.get("risk"),
            "confidence": snapshot.get("confidence") or (75 if severity == "high" else 60),
            "manual_confirmation_required": True,
            "auto_trade_enabled": False,
        }

    async def _record_alert(self, item: dict[str, Any], alert: dict[str, Any]) -> None:
        key = f"{alert['symbol']}:{alert['alert_type']}:{alert.get('breakout_level') or ''}"
        cooldown = max(30, int(_num(self.settings.get("cooldown_seconds"), 900)))
        now_ts = time.time()
        if now_ts - self.last_triggered.get(key, 0) < cooldown:
            return
        self.last_triggered[key] = now_ts
        record = {
            "alert_id": uuid.uuid4().hex,
            **alert,
            "created_at": _now(),
            "delivery_status": "pending",
            "telegram_sent": False,
            "desktop_sent": bool(item.get("desktop_enabled", self.settings.get("desktop_enabled", True))),
            "sound_played": bool(item.get("sound_enabled", self.settings.get("sound_enabled", False))),
            "user_action": "",
            "user_marked_as_taken": False,
            "user_notes": "",
        }
        telegram_enabled = bool(self.settings.get("telegram_enabled") and item.get("telegram_enabled", False))
        if telegram_enabled:
            try:
                bot_token = str(self.settings.get("telegram_bot_token") or "").strip()
                chat_id = str(self.settings.get("telegram_chat_id") or "").strip()
                if bot_token:
                    os.environ["TELEGRAM_BOT_TOKEN"] = bot_token
                if chat_id:
                    os.environ["TELEGRAM_CHAT_IDS"] = chat_id
                await asyncio.to_thread(send_telegram_messages, "Watchlist", self._telegram_message(record))
                record["telegram_sent"] = True
                record["delivery_status"] = "sent"
            except (TelegramDeliveryError, Exception) as exc:
                record["delivery_status"] = f"telegram_failed: {exc}"
        else:
            record["delivery_status"] = "pending_ui" if record["desktop_sent"] else "stored"
        self.alerts.append(record)
        self._pending_alerts.append(record)
        item["last_alert"] = record["message"]
        item["last_alert_at"] = record["created_at"]
        item["last_alert_price"] = record.get("trigger_price")

    def _telegram_message(self, record: dict[str, Any]) -> str:
        targets = [
            ("Target 1", record.get("target1")),
            ("Target 2", record.get("target2")),
            ("Target 3", record.get("target3")),
        ]
        return (
            f"Stock Alert: {record.get('symbol')}\n\n"
            f"Action: {record.get('action')}\n"
            f"Price: Rs {_format_price(record.get('trigger_price'))}\n"
            f"Change: {record.get('percentage_move') if record.get('percentage_move') is not None else '-'}%\n"
            f"Volume: {record.get('volume_ratio') if record.get('volume_ratio') is not None else '-'}x avg\n\n"
            f"Reason:\n- {record.get('reason')}\n"
            f"- Time rule: {record.get('time_rule_status') or 'Ready'}\n"
            f"- Volume confirmation: {record.get('volume_confirmation')}\n\n"
            f"Groww GTT Plan:\n"
            f"Entry: Rs {_format_price(record.get('entry'))}\n"
            f"SL: Rs {_format_price(record.get('stop_loss'))}\n"
            + "".join(f"{label}: Rs {_format_price(value)}\n" for label, value in targets)
            + "\nNote:\nAuto buy/sell disabled. Place order manually in Groww if you accept the trade."
        )

    async def _check_and_archive_hit(self, item: dict[str, Any], snapshot: dict[str, Any]) -> bool:
        symbol = normalize_stock_symbol(item.get("symbol"))
        breakout_level = _num(snapshot.get("breakout_level"))
        price = _num(snapshot.get("current_price"))
        if price <= 0:
            return False

        # State machine to determine if trade has been entered (triggered)
        if not item.get("trade_entered"):
            should_enter = False
            if not breakout_level:
                should_enter = True
            elif price >= breakout_level:
                should_enter = True
            elif item.get("manual_trade_taken"):
                should_enter = True

            if should_enter:
                item["trade_entered"] = True
                item["trade_entry_price"] = price
                item["trade_entered_at"] = _now()
                self.items[symbol] = item
                logger.info(f"Watchlist trade automatically entered for {symbol} at {price}")

        if item.get("trade_entered"):
            entry_price = _num(item.get("trade_entry_price") or snapshot.get("entry") or price)
            stop_loss = _num(snapshot.get("stop_loss"))
            target1 = _num(snapshot.get("target1"))
            target2 = _num(snapshot.get("target2"))
            target3 = _num(snapshot.get("target3"))

            is_sl_hit = stop_loss > 0 and price <= stop_loss
            is_target_hit = target1 > 0 and price >= target1

            if is_sl_hit or is_target_hit:
                outcome = "Target Hit" if is_target_hit else "Stoploss Hit"
                hit_details = ""
                if is_sl_hit:
                    hit_details = f"Stoploss hit at {price:.2f} (SL: {stop_loss:.2f})"
                else:
                    reached_targets = []
                    if target1 > 0 and price >= target1: reached_targets.append(f"T1 ({target1:.2f})")
                    if target2 > 0 and price >= target2: reached_targets.append(f"T2 ({target2:.2f})")
                    if target3 > 0 and price >= target3: reached_targets.append(f"T3 ({target3:.2f})")
                    hit_details = f"Target reached: {', '.join(reached_targets)} at {price:.2f}"

                pl_pct = ((price - entry_price) / entry_price * 100) if entry_price else 0.0

                audit_record = {
                    "audit_id": uuid.uuid4().hex,
                    "symbol": symbol,
                    "company_name": item.get("company_name") or snapshot.get("company_name") or symbol,
                    "outcome": outcome,
                    "entry_price": entry_price,
                    "exit_price": price,
                    "stop_loss": stop_loss,
                    "target1": target1,
                    "target2": target2,
                    "target3": target3,
                    "profit_loss_pct": round(pl_pct, 2),
                    "volume_spike": snapshot.get("volume_spike"),
                    "trade_reason": snapshot.get("trade_reason") or snapshot.get("reason") or "",
                    "entered_at": item.get("trade_entered_at") or item.get("created_at") or _now(),
                    "archived_at": _now(),
                    "hit_details": hit_details,
                    "suggested_time": snapshot.get("suggested_time") or "09:45 AM - 11:00 AM",
                }

                self.audit_history.append(audit_record)
                self.persist_audit_history()

                # Generate high-severity alert for trade outcome
                hit_alert = self._alert(
                    symbol,
                    "TRADE_COMPLETED_AUDIT",
                    "high",
                    price,
                    breakout_level or 0.0,
                    f"TRADE COMPLETED: {symbol} archived with {outcome}. {hit_details}. Net PnL: {pl_pct:.2f}%.",
                    action="EXIT",
                    snapshot=snapshot
                )
                await self._record_alert(item, hit_alert)

                # Remove from active watchlist
                self.remove_item(symbol)
                logger.info(f"Watchlist item {symbol} archived to outcomes audit history due to {outcome}")
                return True
        return False


watchlist_monitor = WatchlistMonitor()

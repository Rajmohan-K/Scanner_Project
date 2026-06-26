from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from ui.stock_data_service import normalize_stock_symbol, stock_data_service, humanize_symbol, exchange_from_symbol
from ui.stock_registry import stock_registry
from utils.logger import logger
from utils.telegram import TelegramDeliveryError, send_telegram_messages


DATA_DIR = Path(__file__).resolve().parent / "data"
WATCHLIST_PATH = DATA_DIR / "watchlist_monitor.json"
ALERTS_PATH = DATA_DIR / "alert_history.json"
SETTINGS_PATH = DATA_DIR / "alert_settings.json"
WATCHLIST_AUDIT_PATH = DATA_DIR / "watchlist_audit_history.json"


DEFAULT_ALERT_SETTINGS: dict[str, Any] = {
    "desktop_enabled": True,
    "browser_alerts_enabled": True,
    "volume_alerts_enabled": True,
    "target_alerts_enabled": True,
    "stop_loss_alerts_enabled": True,
    "buy_alerts_enabled": True,
    "sell_alerts_enabled": True,
    "sound_enabled": True,
    "sound_type": "soft",
    "sound_volume": 35,
    "telegram_enabled": False,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "min_profit_pct": 1.5,
    "breakout_distance_pct": 2.0,
    "breakout_volume_multiplier": 1.5,
    "consecutive_candle_count": 3,
    "price_move_pct_threshold": 1.5,
    "price_surge_pct": 0.75,
    "half_percent_move_threshold": 0.5,
    "cooldown_seconds": 900,
    "intraday_monitoring": True,
    "swing_monitoring": True,
    "monitoring_interval_seconds": 5,
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
    "default_stop_loss_pct": 1.0,
    "profit_booking_start_pct": 1.5,
    "profit_booking_end_pct": 3.0,
    "book_partial_quantity_pct": 50.0,
    "gtt_plan_enabled": True,
    "future_auto_trade_enabled": False,
    "avoid_negative_alerts": True,
    "auto_add_candidates": False,
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _is_synthetic_identifier(value: Any) -> bool:
    return str(value or "").strip().upper().startswith("SYN_")


def _tradeable_identifier(item: dict[str, Any]) -> str:
    for key in ("nse_ticker", "bse_ticker", "symbol", "isin"):
        value = str(item.get(key) or "").strip().upper()
        if value and not _is_synthetic_identifier(value):
            return value
    return ""


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
        self.user_deleted_symbols: set[str] = set()
        self._items_cache_signature = ""
        self._items_cache: list[dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        raw_items = _read_json(WATCHLIST_PATH, [])
        self.items = {}
        discarded = False
        for row in raw_items:
            symbol = row.get("symbol")
            if not symbol:
                continue
            isin = row.get("isin")
            if not isin:
                from ui.stock_registry import resolve_stock_identifier
                resolved = resolve_stock_identifier(symbol, allow_remote=False)
                if resolved:
                    isin = resolved["isin"]
                    row["isin"] = isin
                    row["company_name"] = resolved["company_name"]
                    row["exchange"] = resolved["preferred_exchange"]
                    row["nse_symbol"] = resolved.get("nse_symbol")
                    row["bse_symbol"] = resolved.get("bse_symbol")
                    row["nse_ticker"] = resolved.get("nse_ticker")
                    row["bse_ticker"] = resolved.get("bse_ticker")
                    row["preferred_exchange"] = resolved.get("preferred_exchange") or "NSE"
                    row["active_quote_source"] = resolved.get("active_quote_source") or "NSE"
                    row["fallback_reason"] = resolved.get("fallback_reason")
                else:
                    isin = normalize_stock_symbol(symbol)
            
            # Strict Indian stock validation check on startup (discard non-Indian)
            from ui.stock_registry import is_indian_stock, resolve_stock_identifier
            resolved_chk = resolve_stock_identifier(symbol, allow_remote=False)
            chk_target = resolved_chk if resolved_chk is not None else row
            if not is_indian_stock(chk_target):
                logger.info(f"Watchlist loader: Discarding non-Indian stock {symbol} from active watchlist")
                discarded = True
                continue
                
            self.items[isin] = row

        self.alerts = _read_json(ALERTS_PATH, [])
        self.audit_history = _read_json(WATCHLIST_AUDIT_PATH, [])
        self.settings = {**DEFAULT_ALERT_SETTINGS, **_read_json(SETTINGS_PATH, {})}
        self.user_deleted_symbols = set(_read_json(DATA_DIR / "user_deleted_symbols.json", []))
        
        if discarded:
            logger.info("Watchlist loader: Persisting cleaned watchlist to disk")
            self.persist_items()
        
        # One-time migration to default existing watchlist items to telegram_enabled = True
        if not self.settings.get("telegram_defaults_migrated"):
            for item in self.items.values():
                item["telegram_enabled"] = True
            self.settings["telegram_defaults_migrated"] = True
            self.persist_items()
            self.persist_settings()

    def persist_items(self) -> None:
        self._items_cache_signature = ""
        self._items_cache = []
        _write_json(WATCHLIST_PATH, list(self.items.values()))

    def persist_user_deleted_symbols(self) -> None:
        _write_json(DATA_DIR / "user_deleted_symbols.json", list(self.user_deleted_symbols))

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
        signature = "|".join(
            f"{key}:{row.get('updated_at', '')}:{row.get('last_checked', '')}:{(row.get('snapshot') or {}).get('current_price', '')}"
            for key, row in sorted(self.items.items())
        )
        if signature and signature == self._items_cache_signature:
            return [dict(row) for row in self._items_cache]

        # Pre-pass: map normalized names of resolved/real stocks to their real ISINs
        name_to_real_isin = {}
        for item in self.items.values():
            isin = item.get("isin")
            symbol = item.get("symbol") or ""
            company_name = item.get("company_name") or ""
            
            norm_name = company_name.lower()
            for suffix in (" limited", " ltd.", " ltd", " corp.", " corp", " corporation", " holdings", " holding", " industries", " industry"):
                if norm_name.endswith(suffix):
                    norm_name = norm_name[:-len(suffix)].strip()
            norm_name = "".join(c for c in norm_name if c.isalnum())
            
            real_isin = None
            if isin and not isin.startswith("SYN_"):
                real_isin = isin
            elif symbol:
                try:
                    from ui.stock_registry import resolve_stock_identifier
                    resolved = resolve_stock_identifier(symbol, allow_remote=False)
                    if resolved and resolved.get("isin"):
                        real_isin = resolved["isin"]
                except Exception:
                    pass
            
            if real_isin and norm_name:
                name_to_real_isin[norm_name] = real_isin

        merged: dict[str, dict[str, Any]] = {}
        for item in sorted(self.items.values(), key=lambda row: row.get("created_at", ""), reverse=False):
            isin = item.get("isin")
            company_name = item.get("company_name") or ""
            symbol = item.get("symbol") or ""
            
            # Normalize company name: strip common suffixes
            norm_name = company_name.lower()
            for suffix in (" limited", " ltd.", " ltd", " corp.", " corp", " corporation", " holdings", " holding", " industries", " industry"):
                if norm_name.endswith(suffix):
                    norm_name = norm_name[:-len(suffix)].strip()
            norm_name = "".join(c for c in norm_name if c.isalnum())
            
            # Find/resolve real ISIN
            real_isin = None
            if isin and not isin.startswith("SYN_"):
                real_isin = isin
            else:
                # Try from symbol resolution
                if symbol:
                    try:
                        from ui.stock_registry import resolve_stock_identifier
                        resolved = resolve_stock_identifier(symbol, allow_remote=False)
                        if resolved and resolved.get("isin"):
                            real_isin = resolved["isin"]
                    except Exception:
                        pass
                
                # If still not found, try from norm_name mapping
                if not real_isin and norm_name and norm_name in name_to_real_isin:
                    real_isin = name_to_real_isin[norm_name]
                    
            if real_isin:
                isin = real_isin
            
            base_symbol = symbol.split(".")[0].split(":")[0].strip().upper()
            
            if isin and not isin.startswith("SYN_"):
                group_key = f"isin_{isin}"
            elif norm_name:
                group_key = f"name_{norm_name}"
            elif base_symbol:
                group_key = f"sym_{base_symbol}"
            else:
                group_key = f"raw_{isin or symbol}"
                
            if group_key not in merged:
                merged[group_key] = dict(item)
            else:
                existing = merged[group_key]
                # Merge symbols
                for k in ("nse_symbol", "bse_symbol", "nse_ticker", "bse_ticker"):
                    if not existing.get(k) and item.get(k):
                        existing[k] = item[k]
                
                # Preferred exchange selection update
                if not existing.get("exchange") and item.get("exchange"):
                    existing["exchange"] = item["exchange"]
                if not existing.get("active_quote_source") and item.get("active_quote_source"):
                    existing["active_quote_source"] = item["active_quote_source"]
                
                # If existing has synthetic ISIN and this item has a real ISIN, upgrade the base info
                if existing.get("isin", "").startswith("SYN_") and isin and not isin.startswith("SYN_"):
                    temp = dict(item)
                    for k in ("nse_symbol", "bse_symbol", "nse_ticker", "bse_ticker"):
                        if not temp.get(k) and existing.get(k):
                            temp[k] = existing[k]
                    temp["created_at"] = existing.get("created_at") or temp.get("created_at")
                    merged[group_key] = temp
                else:
                    if item.get("created_at") and existing.get("created_at"):
                        if item["created_at"] < existing["created_at"]:
                            existing["created_at"] = item["created_at"]
                            
        rows = sorted(merged.values(), key=lambda row: row.get("created_at", ""), reverse=False)
        self._items_cache_signature = signature
        self._items_cache = [dict(row) for row in rows]
        return rows

    async def add_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        symbol_input = payload.get("symbol") or payload.get("name")
        if not symbol_input:
            raise ValueError("symbol is required")
        
        from ui.stock_registry import resolve_stock_identifier
        resolved = await asyncio.to_thread(resolve_stock_identifier, symbol_input, allow_remote=False)
        if not resolved:
            raise ValueError(f"Could not resolve stock identifier: {symbol_input}")
            
        isin = resolved["isin"]
        symbol = resolved.get("nse_ticker") or resolved.get("bse_ticker") or isin
        
        # Remove from manual deletion tracking if explicitly added back
        self.user_deleted_symbols.discard(symbol_input.strip().upper())
        normalized_input = normalize_stock_symbol(symbol_input)
        if normalized_input:
            self.user_deleted_symbols.discard(normalized_input)
        self.user_deleted_symbols.discard(isin)
        self.user_deleted_symbols.discard(symbol.upper())
        if resolved.get("nse_ticker"):
            self.user_deleted_symbols.discard(resolved["nse_ticker"].upper())
        if resolved.get("bse_ticker"):
            self.user_deleted_symbols.discard(resolved["bse_ticker"].upper())
        self.persist_user_deleted_symbols()
        
        now = _now()
        existing = self.items.get(isin, {})
        
        # Determine source
        source = payload.get("source") or existing.get("source")
        if not source:
            notes = payload.get("notes") or existing.get("notes") or ""
            if "groww" in str(notes).lower():
                source = "GROWW"
            else:
                source = "CUSTOM"

        item = {
            "symbol": symbol,
            "isin": isin,
            "company_name": resolved.get("company_name") or existing.get("company_name") or humanize_symbol(symbol),
            "exchange": resolved.get("preferred_exchange") or existing.get("exchange") or exchange_from_symbol(symbol),
            "nse_symbol": resolved.get("nse_symbol"),
            "bse_symbol": resolved.get("bse_symbol"),
            "nse_ticker": resolved.get("nse_ticker"),
            "bse_ticker": resolved.get("bse_ticker"),
            "preferred_exchange": resolved.get("preferred_exchange") or "NSE",
            "active_quote_source": resolved.get("active_quote_source") or "NSE",
            "fallback_reason": resolved.get("fallback_reason") or existing.get("fallback_reason"),
            "source": source,
            "monitoring_enabled": payload.get("monitoring_enabled", existing.get("monitoring_enabled", True)),
            "alerts_enabled": payload.get("alerts_enabled", existing.get("alerts_enabled", True)),
            "telegram_enabled": payload.get("telegram_enabled", existing.get("telegram_enabled", True)),
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
        self.items[isin] = item
        self.persist_items()
        refresh_symbol = _tradeable_identifier(item) or isin
        stock_data_service.tracked_symbols.add(refresh_symbol)
        
        async def run_bg_analysis() -> None:
            try:
                # Perform the yfinance verification and data warming in the background
                stock = await stock_data_service.get_stock(refresh_symbol, allow_stale=True)
                if stock.get("status") == "error":
                    raise ValueError(stock.get("message") or f"Invalid stock name: {symbol}")
                
                # Fetch fresh snapshot metadata
                current_item = self.items.get(isin, item)
                current_item["company_name"] = stock.get("name") or current_item["company_name"]
                current_item["exchange"] = stock.get("exchange") or current_item["exchange"]
                
                await self._analyze_item(current_item)
                self.persist_items()
            except Exception as exc:
                logger.warning(f"Background watchlist analysis failed for {isin}: {exc}")
                current = self.items.get(isin, item)
                current["snapshot"] = self._unavailable_snapshot(current, str(exc))
                current["last_checked"] = _now()
                current["updated_at"] = _now()
                # Disable monitoring ONLY if stock is confirmed invalid or delisted
                msg_lower = str(exc).lower()
                if any(term in msg_lower for term in ("delisted", "not found", "invalid symbol")):
                    current["monitoring_enabled"] = False
                    logger.warning(f"Automatically disabled monitoring for {isin} due to delisting/invalid symbol: {exc}")
                self.items[isin] = current
                self.persist_items()

        asyncio.create_task(run_bg_analysis(), name=f"watchlist-analyze-{isin}")
        return item

    def remove_item(self, symbol: str) -> bool:
        # Normalize the input symbol for matching
        sym_upper = symbol.strip().upper()
        norm_input = normalize_stock_symbol(symbol)
        norm_input_upper = norm_input.upper() if norm_input else ""
        
        # Track manual deletion to prevent auto-adding back
        self.user_deleted_symbols.add(sym_upper)
        if norm_input_upper:
            self.user_deleted_symbols.add(norm_input_upper)
            
        # 1. Find the target item in self.items by matching symbol, tickers, or ISIN
        target_isin = None
        target_item = None
        
        for isin_key, item in list(self.items.items()):
            item_symbol = str(item.get("symbol") or "").upper()
            item_isin = str(item.get("isin") or "").upper()
            item_nse_ticker = str(item.get("nse_ticker") or "").upper()
            item_bse_ticker = str(item.get("bse_ticker") or "").upper()
            item_nse_symbol = str(item.get("nse_symbol") or "").upper()
            item_bse_symbol = str(item.get("bse_symbol") or "").upper()
            
            # Helper to check if normalized string equals normalized target
            def match(val):
                if not val:
                    return False
                val_norm = normalize_stock_symbol(val).upper()
                return val_norm == norm_input_upper or val.upper() == sym_upper
                
            if (isin_key.upper() == sym_upper or
                item_isin == sym_upper or
                match(item_symbol) or
                match(item_nse_ticker) or
                match(item_bse_ticker) or
                match(item_nse_symbol) or
                match(item_bse_symbol)):
                target_isin = isin_key
                target_item = item
                break

        if target_item:
            # Add all known identifiers of this item to user_deleted_symbols
            item_symbol = target_item.get("symbol")
            if item_symbol:
                self.user_deleted_symbols.add(item_symbol.upper())
            item_isin = target_item.get("isin")
            if item_isin:
                self.user_deleted_symbols.add(item_isin.upper())
            item_nse_ticker = target_item.get("nse_ticker")
            if item_nse_ticker:
                self.user_deleted_symbols.add(item_nse_ticker.upper())
            item_bse_ticker = target_item.get("bse_ticker")
            if item_bse_ticker:
                self.user_deleted_symbols.add(item_bse_ticker.upper())
            item_nse_symbol = target_item.get("nse_symbol")
            if item_nse_symbol:
                self.user_deleted_symbols.add(item_nse_symbol.upper())
            item_bse_symbol = target_item.get("bse_symbol")
            if item_bse_symbol:
                self.user_deleted_symbols.add(item_bse_symbol.upper())
                
            self.persist_user_deleted_symbols()
            
            # Pop the item from self.items using the actual key
            self.items.pop(target_isin, None)
            self.persist_items()
            
            # Stop background tracking
            stock_data_service.tracked_symbols.discard(target_isin)
            if item_isin:
                stock_data_service.tracked_symbols.discard(item_isin)
            if item_symbol:
                stock_data_service.tracked_symbols.discard(item_symbol)
            return True

        # Fallback: if not found, still persist user_deleted_symbols
        self.persist_user_deleted_symbols()
        return False

    async def update_item(self, symbol: str, payload: dict[str, Any]) -> dict[str, Any]:
        from ui.stock_registry import resolve_stock_identifier
        resolved = await asyncio.to_thread(resolve_stock_identifier, symbol, allow_remote=False)
        if not resolved:
            raise ValueError(f"Could not resolve stock: {symbol}")
        
        isin = resolved["isin"]
        if isin not in self.items:
            await self.add_item({"symbol": isin})
        current = self.items[isin]
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
            "custom_price_alert",
            "intraday_alerts_enabled",
            "swing_alerts_enabled",
            "quantity_placeholder",
            "risk_amount_placeholder",
            "manual_trade_taken",
        ):
            if key in payload:
                current[key] = payload[key]
        current["updated_at"] = _now()
        self.items[isin] = current
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
        timeframe: str = "",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        rows = list(reversed(self.alerts))
        if symbol:
            rows = [row for row in rows if row.get("symbol") == normalize_stock_symbol(symbol)]
        if alert_type:
            rows = [row for row in rows if row.get("alert_type") == alert_type]
        if severity:
            rows = [row for row in rows if str(row.get("severity") or "").upper() == severity.upper()]
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
        if timeframe:
            now_dt = datetime.now()
            timeframe_lower = timeframe.lower()
            filtered_rows = []
            for row in rows:
                created_at_str = row.get("created_at")
                if not created_at_str:
                    continue
                try:
                    created_dt = datetime.fromisoformat(created_at_str)
                    if timeframe_lower == "today":
                        if created_dt.date() == now_dt.date():
                            filtered_rows.append(row)
                    elif timeframe_lower == "week":
                        delta = now_dt - created_dt
                        if delta.days <= 7:
                            filtered_rows.append(row)
                    elif timeframe_lower == "month":
                        delta = now_dt - created_dt
                        if delta.days <= 30:
                            filtered_rows.append(row)
                    else:
                        filtered_rows.append(row)
                except Exception:
                    filtered_rows.append(row)
            rows = filtered_rows
        return rows[:limit]

    async def _worker(self) -> None:
        while True:
            try:
                await self.monitor_once()
            except Exception as exc:
                logger.warning(f"Watchlist monitor cycle failed: {exc}")
            await asyncio.sleep(max(5, int(_num(self.settings.get("monitoring_interval_seconds"), 5))))

    async def monitor_once(self) -> dict[str, Any]:
        # Auto-fetch Groww stocks if both auto_add and groww_source option are enabled (Rule: stop auto-add by default)
        now_ts = time.time()
        if self.settings.get("auto_add_candidates", False) and self.settings.get("groww_source_enabled", False) and (now_ts - getattr(self, "last_groww_fetch", 0) > 300):
            self.last_groww_fetch = now_ts
            try:
                from ui.app import _fetch_groww_intraday_rows
                payload = _fetch_groww_intraday_rows(limit=40)
                rows = payload.get("rows", [])
                
                # Sync Groww list with stock registry to resolve classification bug
                from ui.stock_registry import stock_registry
                await stock_registry.update_groww_stocks(rows)
                
                symbols_to_add = [row["symbol"] for row in rows if row.get("symbol")]
                if symbols_to_add:
                    logger.info(f"Auto-importing {len(symbols_to_add)} symbols from Groww source to watchlist")
                    for symbol in symbols_to_add:
                        sym_upper = symbol.strip().upper()
                        # Resolve ISIN to check thoroughly
                        from ui.stock_registry import resolve_stock_identifier
                        resolved_groww = resolve_stock_identifier(sym_upper, allow_remote=False)
                        groww_isin = resolved_groww["isin"] if resolved_groww else normalize_stock_symbol(sym_upper)
                        
                        # Check if already in items
                        if groww_isin in self.items or sym_upper in self.items:
                            continue
                            
                        # Check if user explicitly deleted it
                        if (sym_upper in self.user_deleted_symbols or 
                            groww_isin in self.user_deleted_symbols or 
                            normalize_stock_symbol(sym_upper) in self.user_deleted_symbols):
                            logger.debug(f"Skipping auto-import of {sym_upper} (user manually deleted it)")
                            continue
                            
                        item_payload = {
                            "symbol": symbol,
                            "monitoring_enabled": True,
                            "alerts_enabled": True,
                            "settings": {"suggested_time": "After VWAP/volume confirmation; avoid fresh entry near close"}
                        }
                        await self.add_item(item_payload)
            except Exception as exc:
                logger.warning(f"Failed to auto-fetch stocks from Groww source: {exc}")

        enabled = [row for row in self.list_items() if row.get("monitoring_enabled", True)]
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
        original_key = str(item.get("isin") or "").strip().upper()
        isin = original_key
        if not isin or _is_synthetic_identifier(isin):
            symbol = normalize_stock_symbol(item.get("symbol"))
            from ui.stock_registry import resolve_stock_identifier
            resolved = resolve_stock_identifier(symbol, allow_remote=False)
            if resolved:
                isin = resolved["isin"]
                item["isin"] = isin
                if original_key and original_key != isin:
                    self.items.pop(original_key, None)
            else:
                isin = _tradeable_identifier(item) or symbol
                
        analysis_symbol = _tradeable_identifier(item) or isin
        analysis = await stock_data_service.get_analysis(analysis_symbol, allow_stale=True)
        if analysis.get("status") == "error":
            message = analysis.get("message") or "Stock data unavailable"
            item["snapshot"] = self._unavailable_snapshot(item, message)
            item["last_checked"] = _now()
            item["updated_at"] = _now()
            # Disable monitoring ONLY for invalid, delisted, or missing stocks
            msg_lower = message.lower()
            if any(term in msg_lower for term in ("delisted", "not found", "invalid symbol")):
                item["monitoring_enabled"] = False
                logger.warning(f"Automatically disabled monitoring for {isin} due to persistent delisting/invalid symbol: {message}")
            self.items[isin] = item
            return
            
        stock = analysis.get("stock") or await stock_data_service.get_stock(analysis_symbol, allow_stale=True)
        candles = await stock_data_service.get_candles(analysis_symbol, "1D", allow_stale=True)
        snapshot = self._build_snapshot(item, stock, analysis, candles.get("candles") or [])
        
        price = snapshot.get("current_price") or 0.0
        
        # Register suggestion if BUY READY or SELL READY and it is a genuine high-profitable stock
        quality_score = snapshot.get("quality_score") or 0
        expected_profit = snapshot.get("expected_profit_percent") or 0.0
        risk_reward = snapshot.get("risk_reward_ratio") or 0.0
        volume_ratio = snapshot.get("volume_spike") or 1.0
        
        is_highly_profitable = (
            quality_score >= 80 and
            expected_profit >= 1.5 and
            risk_reward >= 1.8 and
            volume_ratio >= 1.5
        )

        symbol_key = normalize_stock_symbol(item.get("symbol"))

        if snapshot.get("action") in ("BUY READY", "SELL READY", "STRONG BUY", "STRONG SELL") and is_highly_profitable:
            direction = "SELL" if "SELL" in snapshot.get("action") else "BUY"
            await stock_registry.register_suggestion(
                symbol=symbol_key,
                entry_price=snapshot.get("entry") or price,
                reason=snapshot.get("reason") or snapshot.get("action"),
                target_1=snapshot.get("target1") or (price * 0.985 if direction == "SELL" else price * 1.015),
                target_2=snapshot.get("target2") or (price * 0.970 if direction == "SELL" else price * 1.03),
                stop_loss=snapshot.get("stop_loss") or (price * 1.012 if direction == "SELL" else price * 0.988),
                direction=direction,
            )

        # Update suggestion stats (e.g. current_gain_loss_percent, max_gain, max_loss, status)
        was_active_before = item.get("was_active_suggestion", False)
        active_before_id = item.get("alerted_signal_id")
        
        if symbol_key in stock_registry.active_suggestions:
            item["was_active_suggestion"] = True
            await stock_registry.update_suggestion_prices(symbol_key, price)
            sugg = stock_registry.active_suggestions.get(symbol_key)
            if sugg:
                item["alerted_signal_id"] = sugg.get("signal_id")
                snapshot.update({
                    "suggested_at": sugg.get("suggested_time"),
                    "suggested_entry_price": sugg.get("entry_price"),
                    "current_gain_loss_percent": sugg.get("current_pl_percent"),
                    "max_gain_after_suggestion": sugg.get("max_gain_percent"),
                    "max_loss_after_suggestion": sugg.get("max_loss_percent"),
                    "time_since_suggestion": sugg.get("time_active"),
                    "suggestion_status": sugg.get("status"),
                    "suggested_time": (
                        f"support breakdown at {datetime.fromisoformat(sugg.get('suggested_time')).strftime('%I:%M:%S %p')}"
                        if sugg.get('direction') == 'SELL'
                        else f"volume, resistance breakout at {datetime.fromisoformat(sugg.get('suggested_time')).strftime('%I:%M:%S %p')}"
                    ) if sugg.get('suggested_time') and 'T' in str(sugg.get('suggested_time')) else (
                        f"support breakdown at {sugg.get('suggested_time')}"
                        if sugg.get('direction') == 'SELL'
                        else f"volume, resistance breakout at {sugg.get('suggested_time')}"
                    ),
                    "entry": sugg.get("entry_price"),
                    "stop_loss": sugg.get("stop_loss"),
                    "target1": sugg.get("target_1"),
                    "target2": sugg.get("target_2"),
                    "target3": sugg.get("target_3"),
                })
        elif was_active_before:
            # Signal was active but has exited
            item["was_active_suggestion"] = False
            
            # Retrieve exited signal
            exited_sugg = None
            if hasattr(stock_registry, "suggestion_history") and stock_registry.suggestion_history:
                for hist_sugg in stock_registry.suggestion_history:
                    if normalize_stock_symbol(hist_sugg.get("symbol")) == symbol_key:
                        if not active_before_id or hist_sugg.get("signal_id") == active_before_id:
                            exited_sugg = hist_sugg
                            break
            
            if not exited_sugg:
                try:
                    from ui.signal_manager import signal_manager
                    hist_list = signal_manager.get_signal_history()
                    for hist_sugg in hist_list:
                        if normalize_stock_symbol(hist_sugg.get("symbol")) == symbol_key:
                            if not active_before_id or hist_sugg.get("signal_id") == active_before_id:
                                exited_sugg = hist_sugg
                                break
                except Exception:
                    pass
                    
            if exited_sugg:
                outcome = exited_sugg.get("status") or exited_sugg.get("outcome") or "Closed"
                exit_price = exited_sugg.get("current_price") or exited_sugg.get("exit_price") or price
                entry_price = exited_sugg.get("entry_price") or price
                pl_pct = exited_sugg.get("current_pl_percent") or 0.0
                t1 = exited_sugg.get("target_1") or 0.0
                t2 = exited_sugg.get("target_2") or 0.0
                t3 = exited_sugg.get("target_3") or 0.0
                sl = exited_sugg.get("stop_loss") or exited_sugg.get("initial_stop_loss") or 0.0
                
                audited_list = item.setdefault("audited_signal_ids", [])
                sugg_id = exited_sugg.get("signal_id")
                if sugg_id not in audited_list:
                    audited_list.append(sugg_id)
                    
                    import uuid
                    # Log to Watchlist Audit
                    audit_record = {
                        "audit_id": uuid.uuid4().hex,
                        "symbol": item.get("symbol"),
                        "company_name": item.get("company_name") or snapshot.get("company_name") or item.get("symbol"),
                        "outcome": outcome,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "stop_loss": sl,
                        "target1": t1,
                        "target2": t2,
                        "target3": t3,
                        "profit_loss_pct": round(pl_pct, 2),
                        "volume_spike": snapshot.get("volume_spike") or exited_sugg.get("volume_spike"),
                        "trade_reason": exited_sugg.get("initial_reason") or "",
                        "entered_at": exited_sugg.get("suggested_time") or item.get("created_at") or _now(),
                        "archived_at": _now(),
                        "hit_details": f"Signal exited due to {outcome} at Rs {exit_price:.2f}",
                        "suggested_time": exited_sugg.get("suggested_time") or "09:45 AM - 11:00 AM",
                    }
                    self.audit_history.append(audit_record)
                    self.persist_audit_history()
                    
                    # Generate priority alert for trade exit
                    exit_alert = self._alert(
                        symbol=item.get("symbol"),
                        alert_type="TRADE_COMPLETED_AUDIT",
                        severity="high",
                        price=exit_price,
                        breakout_level=_num(snapshot.get("breakout_level")),
                        reason=f"TRADE COMPLETED: Active Suggestion for {item.get('symbol')} was closed/archived with {outcome}. Entry: Rs {entry_price:.2f}, Exit: Rs {exit_price:.2f}, Net PnL: {pl_pct:+.2f}%.",
                        action="EXIT",
                        snapshot=snapshot
                    )
                    await self._record_alert(item, exit_alert)
                    
                    # Remove from active watchlist
                    self.remove_item(item.get("symbol"))
                    return
        
        item["snapshot"] = snapshot
        item["last_checked"] = _now()
        item["updated_at"] = _now()
        self.items[isin] = item
        for alert in self._evaluate_alerts(item, snapshot):
            await self._record_alert(item, alert)
        await self._check_and_archive_hit(item, snapshot)

    def _build_snapshot(self, item: dict[str, Any], stock: dict[str, Any], analysis: dict[str, Any], candles: list[dict[str, Any]]) -> dict[str, Any]:
        isin = item.get("isin") or item.get("symbol")
        quote = analysis.get("quote") or stock.get("quote") or {}
        price = _num(analysis.get("current_price") or quote.get("current_price"))
        indicators = analysis.get("indicators") or {}
        
        breakout_level = _num(analysis.get("breakout_level"))
        distance = _num(analysis.get("distance_to_breakout_percent"))
        volume_ratio = _num(analysis.get("volume_vs_avg"), 1)
        support = _num(analysis.get("support_levels")[-1] if analysis.get("support_levels") else price * 0.98)
        
        # Pull details from centralized decision engine
        decision = analysis.get("decision") or "AVOID"
        action = analysis.get("action") or "AVOID"
        reason = analysis.get("reason") or ""
        direction_val = analysis.get("direction") or "BUY"
        market_condition = analysis.get("market_condition") or "Sideways"
        
        expected_profit = _num(analysis.get("expected_profit_percent"))
        expected_loss = _num(analysis.get("expected_loss_percent"))
        risk_reward = _num(analysis.get("risk_reward_ratio"))
        quality_score = _num(analysis.get("quality_score"))
        quality_label = analysis.get("quality_label") or "Avoid"
        
        entry = _num(analysis.get("entry_price"))
        stop_loss = _num(analysis.get("stop_loss"))
        target1 = _num(analysis.get("target1"))
        target2 = _num(analysis.get("target2"))
        target3 = _num(analysis.get("target3"))

        # Expose extra metrics from quantitative analysis
        distance_from_vwap = _num(analysis.get("distance_from_vwap_percent"))
        distance_from_high = _num(analysis.get("distance_from_intraday_high_percent"))
        already_moved = _num(analysis.get("already_moved_percent"))
        remaining_upside = _num(analysis.get("remaining_upside_percent"))

        # Resolve signals with fallbacks for tests or schema-mapped payloads
        intraday_signal = analysis.get("intraday_view")
        if not intraday_signal and isinstance(analysis.get("intraday"), dict):
            intraday_signal = analysis.get("intraday", {}).get("recommendation")
        if not intraday_signal:
            intraday_signal = "BUY" if action == "BUY READY" else "SELL" if action == "SELL READY" else "WATCH" if action == "WAIT" else "AVOID"
            
        swing_signal = analysis.get("swing_view")
        if not swing_signal and isinstance(analysis.get("swing"), dict):
            swing_signal = analysis.get("swing", {}).get("recommendation")
        if not swing_signal:
            swing_signal = "BUY" if (action == "BUY READY" and quality_score >= 80) else "SELL" if (action == "SELL READY" and quality_score >= 80) else "WATCH" if action == "WAIT" else "AVOID"

        # Check suggestions from registry
        sugg_data = {}
        symbol_key = normalize_stock_symbol(item.get("symbol"))
        sugg = stock_registry.active_suggestions.get(symbol_key)
        
        # Determine trade readiness and action based on active suggestion status or current decision
        readiness = decision
        if sugg:
            sugg_status = sugg.get("status", "ACTIVE")
            if "HIT" in sugg_status:
                readiness = sugg_status
                action = sugg_status
            elif sugg_status == "CLOSED":
                readiness = "CLOSED"
                action = "CLOSED"
            else:
                readiness = f"{sugg.get('direction', 'BUY')} READY"
                action = f"{sugg.get('direction', 'BUY')} READY"
                
            # Freeze Suggested Time and targets/entry permanently for the active signal (Rule 1)
            ts_str = sugg.get('suggested_time') or datetime.now().strftime('%I:%M:%S %p')
            if ts_str and 'T' in str(ts_str):
                try:
                    ts_str = datetime.fromisoformat(str(ts_str)).strftime('%I:%M:%S %p')
                except Exception:
                    pass
            
            if sugg.get('direction') == 'SELL':
                suggested_time = f"Price breakdown (LTP: {price:.2f}, Sup: {support:.2f}), Vol Surge ({volume_ratio:.1f}x) at {ts_str}"
            else:
                suggested_time = f"Price breakout (LTP: {price:.2f}, Res: {breakout_level:.2f}), Vol Surge ({volume_ratio:.1f}x) at {ts_str}"
            entry = sugg.get("entry_price", entry)
            stop_loss = sugg.get("stop_loss", stop_loss)
            target1 = sugg.get("target_1", target1)
            target2 = sugg.get("target_2", target2)
            target3 = sugg.get("target_3", target3)
            
            sugg_data = {
                "suggested_at": sugg.get("suggested_time"),
                "suggested_entry_price": sugg.get("entry_price"),
                "current_gain_loss_percent": sugg.get("current_pl_percent"),
                "max_gain_after_suggestion": sugg.get("max_gain_percent"),
                "max_loss_after_suggestion": sugg.get("max_loss_percent"),
                "time_since_suggestion": sugg.get("time_active"),
                "suggestion_status": sugg.get("status"),
                "initialStopLoss": sugg.get("initialStopLoss"),
                "trailingStop": sugg.get("trailingStop"),
                "trailingActivated": sugg.get("trailingActivated"),
                "highestPriceSinceEntry": sugg.get("highestPriceSinceEntry"),
                "lowestPriceSinceEntry": sugg.get("lowestPriceSinceEntry"),
                "trailingStatus": sugg.get("trailingStatus"),
                "targetHitStatus": sugg.get("targetHitStatus"),
                "stopLossHitStatus": sugg.get("stopLossHitStatus"),
                "outcome": sugg.get("outcome"),
            }
        else:
            suggested_time = reason
            
            is_buy_signal = "BUY" in action or "BUY" in decision or "BUY NOW" in reason or direction_val == "BUY"
            is_sell_signal = "SELL" in action or "SELL" in decision or "SELL NOW" in reason or direction_val == "SELL"
            
            # Let's extract the timestamp from reason if possible, or fallback to current time
            ts_str = datetime.now().strftime('%I:%M:%S %p')
            if reason and "at " in reason:
                parts = reason.split("at ")
                if len(parts) > 1:
                    ts_str = parts[-1].strip()
            
            if action in ("BUY READY", "SELL READY", "STRONG BUY", "STRONG SELL") or "BUY NOW" in reason or "SELL NOW" in reason:
                if is_sell_signal:
                    suggested_time = f"Price breakdown (LTP: {price:.2f}, Sup: {support:.2f}), Vol Surge ({volume_ratio:.1f}x) at {ts_str}"
                else:
                    suggested_time = f"Price breakout (LTP: {price:.2f}, Res: {breakout_level:.2f}), Vol Surge ({volume_ratio:.1f}x) at {ts_str}"
            else:
                if suggested_time:
                    suggested_time = suggested_time.replace("BUY NOW at", "volume, resistance breakout at").replace("SELL NOW at", "support breakdown at")
            entry = None
            stop_loss = None
            target1 = None
            target2 = None
            target3 = None
            sugg_data = {
                "initialStopLoss": None,
                "trailingStop": None,
                "trailingActivated": False,
                "highestPriceSinceEntry": None,
                "lowestPriceSinceEntry": None,
                "trailingStatus": "Inactive",
                "targetHitStatus": "None",
                "stopLossHitStatus": "None",
                "outcome": "",
            }

        # Determine if high priority alert criteria is met
        is_high_alert = False
        if quality_score >= 80 and expected_profit >= 1.5 and risk_reward >= 1.8 and volume_ratio >= 2.0:
            if direction_val == "BUY":
                if already_moved <= 3.5 and (price >= breakout_level or distance <= 0.3):
                    is_high_alert = True
            else: # SELL
                if already_moved >= -3.5 and (price <= breakout_level or distance <= 0.3):
                    is_high_alert = True

        # Resolve sector
        sector_val = "Unclassified"
        try:
            from ui.v20_store import connect
            with connect() as conn:
                r_sect = conn.execute("SELECT sector FROM company_symbol_registry WHERE isin = ?", (isin,)).fetchone()
                if r_sect and r_sect[0]:
                    sector_val = r_sect[0]
                else:
                    s_sect = conn.execute("SELECT sector FROM stocks WHERE symbol = ? OR symbol = ? OR symbol = ?", (isin, item.get("nse_ticker"), item.get("bse_ticker"))).fetchone()
                    if s_sect and s_sect[0]:
                        sector_val = s_sect[0]
        except Exception:
            pass

        return {
            "symbol": item.get("symbol"),
            "company_name": item.get("company_name") or stock.get("name") or analysis.get("company_name"),
            "exchange": item.get("exchange") or stock.get("exchange") or analysis.get("exchange"),
            "isin": isin,
            "sector": sector_val,
            "nse_symbol": item.get("nse_symbol") or analysis.get("nse_symbol"),
            "bse_symbol": item.get("bse_symbol") or analysis.get("bse_symbol"),
            "nse_ticker": item.get("nse_ticker") or analysis.get("nse_ticker"),
            "bse_ticker": item.get("bse_ticker") or analysis.get("bse_ticker"),
            "preferred_exchange": item.get("preferred_exchange") or analysis.get("preferred_exchange"),
            "active_quote_source": analysis.get("active_quote_source") or stock.get("active_quote_source") or "NSE",
            "fallback_reason": analysis.get("fallback_reason") or stock.get("fallback_reason"),
            "current_price": price,
            "price_change_pct": _num(quote.get("change_pct")),
            "volume_spike": volume_ratio,
            "trend": analysis.get("trend") or "Unavailable",
            "breakout_level": breakout_level,
            "expected_breakout_price": breakout_level,
            "distance_to_breakout_pct": distance,
            "current_status": market_condition,
            "intraday_signal": intraday_signal,
            "swing_signal": swing_signal,
            "risk": "Low" if quality_score >= 75 else "High",
            "confidence": quality_score,
            "last_alert": item.get("last_alert", ""),
            "last_alert_price": item.get("last_alert_price"),
            "last_checked": item.get("last_checked", ""),
            "support": support,
            "resistance": breakout_level,
            "vwap": indicators.get("vwap"),
            "ema20": indicators.get("ema20"),
            "ema50": indicators.get("ema50"),
            "ema200": indicators.get("ema200"),
            "reason": reason,
            "candles": candles[-10:],
            "stale": bool(analysis.get("stale") or stock.get("stale")),
            
            # Decisions and plans
            "trade_readiness": readiness,
            "distance_from_vwap_percent": distance_from_vwap,
            "distance_from_intraday_high_percent": distance_from_high,
            "already_moved_percent": already_moved,
            "remaining_upside_percent": remaining_upside,
            "action": action,
            "entry": entry,
            "stop_loss": stop_loss,
            "target1": target1,
            "target2": target2,
            "target3": target3,
            "expected_profit_percent": expected_profit,
            "expected_loss_percent": expected_loss,
            "risk_reward_ratio": risk_reward,
            "quality_score": quality_score,
            "quality_label": quality_label,
            "suggested_time": suggested_time,
            "profit_booking_status": sugg.get("status") if sugg else "Not started",
            "manual_confirmation_required": True,
            "auto_trade_enabled": False,
            "direction": direction_val,
            "is_high_alert": is_high_alert,
            "custom_price_alert": _num(item.get("custom_price_alert")),
            
            # Suggestion fields
            **sugg_data,
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
            "custom_price_alert": _num(item.get("custom_price_alert")),
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
        min_profit = _num(self.settings.get("min_profit_pct"), 1.5)
        target1 = _round_price((entry or price) * (1 + min_profit / 100)) if entry else None
        target2 = _round_price((entry or price) * (1 + min_profit * 2 / 100)) if entry else None
        target3 = _round_price((entry or price) * (1 + min_profit * 3 / 100)) if entry else None
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
        alerts = []
        symbol = snapshot.get("symbol")
        price = _num(snapshot.get("current_price"))
        if price <= 0:
            return alerts
            
        prev_snapshot = item.get("snapshot") or {}
        prev_action = prev_snapshot.get("action") or "AVOID"
        curr_action = snapshot.get("action") or "AVOID"
        
        # Ensure we have a dict to store triggered alert levels in the item
        alert_levels = item.setdefault("alert_levels_triggered", {})
        
        symbol_key = normalize_stock_symbol(symbol)
        from ui.stock_registry import stock_registry
        is_active_signal = symbol_key in stock_registry.active_suggestions
        sugg = stock_registry.active_suggestions.get(symbol_key) if is_active_signal else None

        # 1. Signal Activation Alerting (Ready to trade / added to High-Profitable Trade Suggestions)
        if sugg:
            sugg_id = sugg.get("signal_id") or f"SIG_{symbol_key}"
            if item.get("alerted_signal_id") != sugg_id:
                item["alerted_signal_id"] = sugg_id
                direction = sugg.get("direction", "BUY")
                entry_val = sugg.get("entry_price") or price
                sl_val = sugg.get("stop_loss") or sugg.get("initial_stop_loss") or 0.0
                t1_val = sugg.get("target_1") or 0.0
                t2_val = sugg.get("target_2") or 0.0
                t3_val = sugg.get("target_3") or 0.0
                
                reason_msg = (
                    f"HIGH-PROFITABLE TRADE SUGGESTION: {symbol} is ready to trade ({direction}) "
                    f"and added to Active Signals. Entry: Rs {entry_val:.2f}, Stop Loss: Rs {sl_val:.2f}, "
                    f"Target 1: Rs {t1_val:.2f}, Target 2: Rs {t2_val:.2f}, Target 3: Rs {t3_val:.2f}."
                )
                activation_alert = self._alert(
                    symbol=symbol,
                    alert_type="SIGNAL_ADDED",
                    severity="high",
                    price=price,
                    breakout_level=_num(snapshot.get("breakout_level")),
                    reason=reason_msg,
                    action=f"{direction} READY",
                    snapshot=snapshot
                )
                alerts.append(activation_alert)

        # 2. Watch/Wait Stocks Breakout/Near Breakout Alerting
        if not is_active_signal and curr_action in ("WATCH", "WAIT", "AVOID"):
            breakout_level = _num(snapshot.get("breakout_level"))
            support = _num(snapshot.get("support"))
            distance = _num(snapshot.get("distance_to_breakout_pct"))
            direction_val = snapshot.get("direction") or "BUY"
            
            # Breakout logic for watch/wait stock (strictly price breakout AND volume surge)
            is_breakout = False
            breakout_msg = ""
            vol_mult = _num(self.settings.get("breakout_volume_multiplier", 1.5))
            volume_ratio = _num(snapshot.get("volume_spike"))
            if direction_val == "BUY" and breakout_level > 0 and price >= breakout_level:
                if volume_ratio >= vol_mult:
                    is_breakout = True
                    breakout_msg = f"Watch Stock Breakout: {symbol} broke above resistance level of {breakout_level:.2f} with volume surge ({volume_ratio:.1f}x vs {vol_mult:.1f}x multiplier)."
            elif direction_val == "SELL" and support > 0 and price <= support:
                if volume_ratio >= vol_mult:
                    is_breakout = True
                    breakout_msg = f"Watch Stock Breakdown: {symbol} broke below support level of {support:.2f} with volume surge ({volume_ratio:.1f}x vs {vol_mult:.1f}x multiplier)."
                
            if is_breakout:
                bo_key = f"watch_breakout_{breakout_level or support}"
                if not alert_levels.get(bo_key):
                    alert_levels[bo_key] = True
                    alerts.append(self._alert(
                        symbol=symbol,
                        alert_type="BREAKOUT_EVENT",
                        severity="high",
                        price=price,
                        breakout_level=breakout_level,
                        reason=breakout_msg,
                        action="WATCH",
                        snapshot=snapshot
                    ))
            
            # Near breakout logic for watch/wait stock (distance <= 0.5%)
            is_near_breakout = False
            near_msg = ""
            if direction_val == "BUY" and breakout_level > price and 0 < breakout_level - price <= price * 0.005:
                is_near_breakout = True
                near_msg = f"Watch Stock Near Breakout: {symbol} is approaching resistance at {breakout_level:.2f} (within 0.5%)."
            elif direction_val == "SELL" and support > 0 and price > support and 0 < price - support <= price * 0.005:
                is_near_breakout = True
                near_msg = f"Watch Stock Near Breakdown: {symbol} is approaching support at {support:.2f} (within 0.5%)."
                
            if is_near_breakout:
                near_key = f"watch_near_breakout_{breakout_level or support}"
                last_sent = alert_levels.get(near_key, 0)
                # Keep sending alerts with a cooldown of 60 seconds
                if time.time() - last_sent > 60:
                    alert_levels[near_key] = time.time()
                    alerts.append(self._alert(
                        symbol=symbol,
                        alert_type="NEAR_BREAKOUT_EVENT",
                        severity="high",
                        price=price,
                        breakout_level=breakout_level,
                        reason=near_msg,
                        action="WATCH",
                        snapshot=snapshot
                    ))

        # 3. State Transitions: WATCH -> READY, WAIT -> READY
        if prev_action in ("WATCH", "WAIT") and curr_action in ("BUY READY", "SELL READY"):
            transition_alert = self._alert(
                symbol=symbol,
                alert_type="STATE_TRANSITION",
                severity="high",
                price=price,
                breakout_level=_num(snapshot.get("breakout_level")),
                reason=f"State transitioned from {prev_action} to {curr_action} for {symbol} at {price:.2f}.",
                action=curr_action,
                snapshot=snapshot
            )
            alerts.append(transition_alert)

        # 2. BUY READY Alert (kept for legacy/backward compatibility)
        if self.settings.get("buy_alerts_enabled", True) and prev_action != "BUY READY" and curr_action == "BUY READY":
            quality_score = _num(snapshot.get("quality_score"))
            expected_profit = _num(snapshot.get("expected_profit_percent"))
            risk_reward = _num(snapshot.get("risk_reward_ratio"))
            volume_ratio = _num(snapshot.get("volume_spike"))
            vwap = snapshot.get("vwap")
            already_moved = _num(snapshot.get("already_moved_percent"))
            target1 = _num(snapshot.get("target1"))
            
            if (quality_score >= 80 and
                expected_profit >= 1.5 and
                risk_reward >= 1.8 and
                volume_ratio >= 2.0 and
                vwap is not None and price > vwap and
                already_moved <= 3.5 and
                (target1 <= 0 or price < target1)):
                
                reason_msg = f"BUY SIGNAL: Breakout confirmed with {volume_ratio:.1f}x volume and VWAP support."
                buy_alert = self._alert(
                    symbol=symbol,
                    alert_type="BUY_READY",
                    severity="high",
                    price=price,
                    breakout_level=_num(snapshot.get("breakout_level")),
                    reason=reason_msg,
                    action="BUY READY",
                    snapshot=snapshot
                )
                alerts.append(buy_alert)

        # 3. SELL READY Alert (kept for legacy/backward compatibility)
        if self.settings.get("sell_alerts_enabled", True) and prev_action != "SELL READY" and curr_action == "SELL READY":
            quality_score = _num(snapshot.get("quality_score"))
            expected_downside = _num(snapshot.get("expected_profit_percent"))
            risk_reward = _num(snapshot.get("risk_reward_ratio"))
            volume_ratio = _num(snapshot.get("volume_spike"))
            vwap = snapshot.get("vwap")
            already_moved = _num(snapshot.get("already_moved_percent"))
            target1 = _num(snapshot.get("target1"))
            
            if (quality_score >= 80 and
                expected_downside >= 1.5 and
                risk_reward >= 1.8 and
                volume_ratio >= 2.0 and
                vwap is not None and price < vwap and
                already_moved >= -3.5 and
                (target1 <= 0 or price > target1)):
                
                reason_msg = f"SELL SIGNAL: Breakdown confirmed with {volume_ratio:.1f}x volume and price below VWAP."
                sell_alert = self._alert(
                    symbol=symbol,
                    alert_type="SELL_READY",
                    severity="high",
                    price=price,
                    breakout_level=_num(snapshot.get("breakout_level")),
                    reason=reason_msg,
                    action="SELL READY",
                    snapshot=snapshot
                )
                alerts.append(sell_alert)

        # 4. Target Approaching Alerts
        if self.settings.get("target_alerts_enabled", True) and (item.get("trade_entered") or is_active_signal):
            entry_price = _num(item.get("trade_entry_price") or snapshot.get("entry") or price)
            target1 = _num(snapshot.get("target1"))
            direction = snapshot.get("direction") or "BUY"
            
            if entry_price > 0 and target1 > 0:
                completion_pct = 0.0
                if direction == "BUY" and target1 > entry_price and price >= entry_price:
                    completion_pct = (price - entry_price) / (target1 - entry_price) * 100
                elif direction == "SELL" and entry_price > target1 and price <= entry_price:
                    completion_pct = (entry_price - price) / (entry_price - target1) * 100
                
                if completion_pct > 0:
                    for level in (80, 90, 95):
                        level_key = f"target_{level}"
                        last_sent = alert_levels.get(level_key, 0)
                        if completion_pct >= level and (time.time() - last_sent > 60):
                            alert_levels[level_key] = time.time()
                            target_alert = self._alert(
                                symbol=symbol,
                                alert_type="TARGET_APPROACHING",
                                severity="high" if is_active_signal else "medium",
                                price=price,
                                breakout_level=_num(snapshot.get("breakout_level")),
                                reason=f"Target Approaching: {symbol} is {level}% toward Target 1 ({target1:.2f}) at {price:.2f}.",
                                action="WATCH",
                                snapshot=snapshot,
                                level_pct=level
                            )
                            alerts.append(target_alert)

        # 5. Stop Loss Approaching Alerts
        if self.settings.get("stop_loss_alerts_enabled", True) and (item.get("trade_entered") or is_active_signal):
            entry_price = _num(item.get("trade_entry_price") or snapshot.get("entry") or price)
            stop_loss = _num(snapshot.get("stop_loss"))
            direction = snapshot.get("direction") or "BUY"
            
            if entry_price > 0 and stop_loss > 0:
                sl_pct = 0.0
                if direction == "BUY" and entry_price > stop_loss and price <= entry_price:
                    sl_pct = (entry_price - price) / (entry_price - stop_loss) * 100
                elif direction == "SELL" and stop_loss > entry_price and price >= entry_price:
                    sl_pct = (price - entry_price) / (stop_loss - entry_price) * 100
                
                if sl_pct > 0:
                    for level in (50, 75, 90):
                        level_key = f"sl_{level}"
                        last_sent = alert_levels.get(level_key, 0)
                        if sl_pct >= level and (time.time() - last_sent > 60):
                            alert_levels[level_key] = time.time()
                            sl_alert = self._alert(
                                symbol=symbol,
                                alert_type="STOP_LOSS_APPROACHING",
                                severity="high" if is_active_signal else "medium",
                                price=price,
                                breakout_level=_num(snapshot.get("breakout_level")),
                                reason=f"Stop Loss Approaching: {symbol} is {level}% toward Stop Loss ({stop_loss:.2f}) at {price:.2f}.",
                                action="WATCH",
                                snapshot=snapshot,
                                level_pct=level
                            )
                            alerts.append(sl_alert)

        # 6. Volume Surge Alert
        if self.settings.get("volume_alerts_enabled", True):
            volume_ratio = _num(snapshot.get("volume_spike"))
            price_change = _num(snapshot.get("price_change_pct"))
            quality_score = _num(snapshot.get("quality_score"))
            if volume_ratio >= 3.0 and abs(price_change) > 0.5 and quality_score > 70:
                vol_alert = self._alert(
                    symbol=symbol,
                    alert_type="VOLUME_SURGE",
                    severity="high",
                    price=price,
                    breakout_level=_num(snapshot.get("breakout_level")),
                    reason=f"Volume Surge: {symbol} volume is {volume_ratio:.1f}x average with {price_change:+.2f}% price move.",
                    action="WATCH",
                    snapshot=snapshot
                )
                alerts.append(vol_alert)

        # 7. Breakdown Confirmed Alert
        if self.settings.get("sell_alerts_enabled", True) and self.settings.get("volume_alerts_enabled", True):
            support = _num(snapshot.get("support"))
            volume_ratio = _num(snapshot.get("volume_spike"))
            if support > 0 and price < support and volume_ratio >= 2.0:
                bd_alert = self._alert(
                    symbol=symbol,
                    alert_type="BREAKDOWN_CONFIRMED",
                    severity="high",
                    price=price,
                    breakout_level=_num(snapshot.get("breakout_level")),
                    reason=f"Breakdown Confirmed: {symbol} broke support of {support:.2f} with {volume_ratio:.1f}x volume.",
                    action="SELL READY",
                    snapshot=snapshot
                )
                alerts.append(bd_alert)

        # 8. Consecutive Candles Alert
        if self.settings.get("volume_alerts_enabled", True):
            candles = snapshot.get("candles") or []
            N = int(self.settings.get("consecutive_candle_count", 3))
            if len(candles) >= N:
                last_N = candles[-N:]
                is_bullish = True
                is_bearish = True
                increasing_volume = True
                for i in range(N):
                    c = last_N[i]
                    o = _num(c.get("open"))
                    cl = _num(c.get("close"))
                    v = _num(c.get("volume"))
                    
                    if o <= 0 or cl <= 0 or v <= 0:
                        is_bullish = False
                        is_bearish = False
                        increasing_volume = False
                        break
                    
                    if cl <= o:
                        is_bullish = False
                    if cl >= o:
                        is_bearish = False
                        
                    if i > 0:
                        prev_v = _num(last_N[i-1].get("volume"))
                        if v <= prev_v:
                            increasing_volume = False
                
                if increasing_volume and (is_bullish or is_bearish):
                    direction_str = "bullish" if is_bullish else "bearish"
                    momentum_alert = self._alert(
                        symbol=symbol,
                        alert_type="MOMENTUM",
                        severity="high",
                        price=price,
                        breakout_level=_num(snapshot.get("breakout_level")),
                        reason=f"Momentum: {symbol} has {N} consecutive {direction_str} candles with increasing volume.",
                        action="BUY READY" if is_bullish else "SELL READY",
                        snapshot=snapshot
                    )
                    alerts.append(momentum_alert)

        # 9. Custom Price Alert
        alert_price = _num(item.get("custom_price_alert") or snapshot.get("custom_price_alert"))
        if alert_price > 0:
            prev_price = _num(prev_snapshot.get("current_price"))
            curr_price = _num(snapshot.get("current_price"))
            if prev_price > 0 and curr_price > 0:
                crossed_above = prev_price < alert_price <= curr_price
                crossed_below = prev_price > alert_price >= curr_price
                if crossed_above or crossed_below:
                    level_key = f"price_alert_{alert_price}"
                    if not alert_levels.get(level_key):
                        alert_levels[level_key] = True
                        direction_str = "above" if crossed_above else "below"
                        price_alert = self._alert(
                            symbol=symbol,
                            alert_type="PRICE_ALERT",
                            severity="high",
                            price=price,
                            breakout_level=_num(snapshot.get("breakout_level")),
                            reason=f"Price Alert: {symbol} reached/crossed alert price {alert_price:.2f} (moved {direction_str} from {prev_price:.2f} to {curr_price:.2f}).",
                            action="ALERT ONLY",
                            snapshot=snapshot,
                            level_pct=alert_price
                        )
                        alerts.append(price_alert)

        # 10. Price Surge Alert
        price_surge_threshold = _num(self.settings.get("price_surge_pct", 0.75))
        if price_surge_threshold > 0:
            price_change = _num(snapshot.get("price_change_pct"))
            if abs(price_change) >= price_surge_threshold:
                ps_key = f"price_surge_{price_surge_threshold}"
                last_sent = alert_levels.get(ps_key, 0)
                cooldown = _num(self.settings.get("cooldown_seconds", 900))
                if time.time() - last_sent > cooldown:
                    alert_levels[ps_key] = time.time()
                    direction_str = "upside" if price_change > 0 else "downside"
                    price_surge_alert = self._alert(
                        symbol=symbol,
                        alert_type="PRICE_SURGE",
                        severity="high",
                        price=price,
                        breakout_level=_num(snapshot.get("breakout_level")),
                        reason=f"Price Surge: {symbol} has a price change of {price_change:+.2f}% ({direction_str}) exceeding threshold of {price_surge_threshold:.2f}%.",
                        action="WATCH",
                        snapshot=snapshot
                    )
                    alerts.append(price_surge_alert)

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
        alert_type = alert.get("alert_type")
        symbol = alert.get("symbol")
        key = f"{symbol}:{alert_type}"
        cooldown = max(30, int(_num(self.settings.get("cooldown_seconds"), 900)))
        
        if alert_type == "BUY_READY":
            cooldown = 900
        elif alert_type == "SELL_READY":
            cooldown = 900
        elif alert_type == "VOLUME_SURGE":
            cooldown = 600
        elif alert_type == "PRICE_SURGE":
            cooldown = 600
        elif alert_type == "MOMENTUM":
            cooldown = 600
        elif alert_type in ("TARGET_APPROACHING", "STOP_LOSS_APPROACHING", "PRICE_ALERT"):
            level_val = alert.get("level_pct") or ""
            key = f"{symbol}:{alert_type}:{level_val}"
            cooldown = 0
            
        now_ts = time.time()
        if now_ts - self.last_triggered.get(key, 0) < cooldown:
            return
        self.last_triggered[key] = now_ts
        
        severity = str(alert.get("severity") or "low").upper()
        is_priority = severity in ("CRITICAL", "HIGH")
        
        if is_priority:
            desktop_sent = bool(self.settings.get("desktop_enabled", True))
            sound_played = bool(self.settings.get("sound_enabled", True))
            telegram_enabled = bool(self.settings.get("telegram_enabled", False))
        else:
            desktop_sent = False
            sound_played = False
            telegram_enabled = False
            
        record = {
            "alert_id": uuid.uuid4().hex,
            **alert,
            "created_at": _now(),
            "delivery_status": "pending",
            "telegram_sent": False,
            "desktop_sent": desktop_sent,
            "sound_played": sound_played,
            "user_action": "",
            "user_marked_as_taken": False,
            "user_notes": "",
        }
        if telegram_enabled:
            try:
                bot_token = str(self.settings.get("telegram_bot_token") or "").strip()
                chat_id = str(self.settings.get("telegram_chat_id") or "").strip()
                if bot_token:
                    os.environ["TELEGRAM_BOT_TOKEN"] = bot_token
                if chat_id:
                    os.environ["TELEGRAM_CHAT_IDS"] = chat_id
                
                from ui.stock_registry import stock_registry
                symbol_key = normalize_stock_symbol(record.get("symbol"))
                is_suggestion = symbol_key in stock_registry.active_suggestions
                category_val = "Intraday" if is_suggestion else "Watchlist"
                
                await asyncio.to_thread(send_telegram_messages, category_val, self._telegram_message(record))
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
        from ui.stock_registry import stock_registry
        symbol = record.get("symbol")
        symbol_key = normalize_stock_symbol(symbol)
        is_suggestion = symbol_key in stock_registry.active_suggestions
        
        msg = (
            f"Stock Alert: {symbol}\n\n"
            f"Action: {record.get('action')}\n"
            f"Price: Rs {_format_price(record.get('trigger_price'))}\n"
            f"Change: {record.get('percentage_move') if record.get('percentage_move') is not None else '-'}%\n"
            f"Volume: {record.get('volume_ratio') if record.get('volume_ratio') is not None else '-'}x avg\n\n"
            f"Reason:\n- {record.get('reason')}\n"
            f"- Time rule: {record.get('time_rule_status') or 'Ready'}\n"
            f"- Volume confirmation: {record.get('volume_confirmation')}\n\n"
        )
        if is_suggestion:
            targets = [
                ("Target 1", record.get("target1")),
                ("Target 2", record.get("target2")),
            ]
            msg += (
                f"Groww GTT Plan:\n"
                f"Entry: Rs {_format_price(record.get('entry'))}\n"
                f"SL: Rs {_format_price(record.get('stop_loss'))}\n"
                + "".join(f"{label}: Rs {_format_price(value)}\n" for label, value in targets)
                + "\nNote:\nAuto buy/sell disabled. Place order manually in Groww if you accept the trade."
            )
        else:
            msg += "Note:\nAuto buy/sell disabled. Monitor setup parameters in Watchlist."
            
        return msg

    async def _check_and_archive_hit(self, item: dict[str, Any], snapshot: dict[str, Any]) -> bool:
        symbol = normalize_stock_symbol(item.get("symbol"))
        breakout_level = _num(snapshot.get("breakout_level"))
        price = _num(snapshot.get("current_price"))
        if price <= 0:
            return False

        direction = snapshot.get("direction") or "BUY"

        # State machine to determine if trade has been entered (triggered)
        if not item.get("trade_entered"):
            should_enter = False
            if direction == "BUY":
                if not breakout_level:
                    should_enter = True
                elif price >= breakout_level:
                    should_enter = True
            else: # direction == "SELL"
                if not breakout_level:
                    should_enter = True
                elif price <= breakout_level:
                    should_enter = True
            
            if item.get("manual_trade_taken"):
                should_enter = True

            if should_enter:
                item["trade_entered"] = True
                item["trade_entry_price"] = price
                item["trade_entered_at"] = _now()
                self.items[symbol] = item
                logger.info(f"Watchlist trade automatically entered for {symbol} at {price} ({direction})")

        if item.get("trade_entered"):
            entry_price = _num(item.get("trade_entry_price") or snapshot.get("entry") or price)
            stop_loss = _num(snapshot.get("stop_loss"))
            target1 = _num(snapshot.get("target1"))
            target2 = _num(snapshot.get("target2"))
            target3 = _num(snapshot.get("target3"))

            if direction == "SELL":
                is_sl_hit = stop_loss > 0 and price >= stop_loss
                is_target_hit = target1 > 0 and price <= target1
                pl_pct = ((entry_price - price) / entry_price * 100) if entry_price else 0.0
            else:
                is_sl_hit = stop_loss > 0 and price <= stop_loss
                is_target_hit = target1 > 0 and price >= target1
                pl_pct = ((price - entry_price) / entry_price * 100) if entry_price else 0.0

            if is_sl_hit or is_target_hit:
                outcome = "Target Hit" if is_target_hit else "Stoploss Hit"
                hit_details = ""
                if is_sl_hit:
                    hit_details = f"Stoploss hit at {price:.2f} (SL: {stop_loss:.2f})"
                else:
                    reached_targets = []
                    if direction == "SELL":
                        if target1 > 0 and price <= target1: reached_targets.append(f"T1 ({target1:.2f})")
                        if target2 > 0 and price <= target2: reached_targets.append(f"T2 ({target2:.2f})")
                        if target3 > 0 and price <= target3: reached_targets.append(f"T3 ({target3:.2f})")
                    else:
                        if target1 > 0 and price >= target1: reached_targets.append(f"T1 ({target1:.2f})")
                        if target2 > 0 and price >= target2: reached_targets.append(f"T2 ({target2:.2f})")
                        if target3 > 0 and price >= target3: reached_targets.append(f"T3 ({target3:.2f})")
                    hit_details = f"Target reached: {', '.join(reached_targets)} at {price:.2f}"

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

                entered_at_str = item.get("trade_entered_at") or item.get("created_at")
                holding_str = "Unknown"
                if entered_at_str:
                    try:
                        entered_dt = datetime.fromisoformat(entered_at_str)
                        duration = datetime.now() - entered_dt
                        hours, remainder = divmod(duration.total_seconds(), 3600)
                        minutes, seconds = divmod(remainder, 60)
                        holding_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
                    except Exception:
                        pass

                # Generate high-severity alert for trade outcome
                severity_val = "critical" if is_sl_hit else "high"
                hit_alert = self._alert(
                    symbol,
                    "TRADE_COMPLETED_AUDIT",
                    severity_val,
                    price,
                    breakout_level or 0.0,
                    f"TRADE COMPLETED: {symbol} archived with {outcome}. {hit_details}. Net PnL: {pl_pct:.2f}%. Holding Time: {holding_str}.",
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

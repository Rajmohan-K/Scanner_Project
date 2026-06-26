from __future__ import annotations

import asyncio
import contextlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from utils.logger import logger


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_stock_symbol(value: Any) -> str:
    raw = str(value or "").strip().upper().replace(" ", "")
    if not raw:
        return ""
    if raw.startswith("^"):
        return raw
    if raw.startswith("SYN_"):
        return ""
    if raw.endswith(".NS") or raw.endswith(".BO"):
        return raw[:-3]
    if "." in raw:
        return raw.split(".")[0]
    return raw


def _symbol_keys(symbol: str, payload: dict[str, Any] | None = None) -> set[str]:
    payload = payload or {}
    keys = {str(symbol or "").strip().upper()}
    for key in ("symbol", "isin", "nse_symbol", "bse_symbol", "nse_ticker", "bse_ticker"):
        value = str(payload.get(key) or "").strip().upper()
        if value:
            keys.add(value)
            normalized = normalize_stock_symbol(value)
            if normalized:
                keys.add(normalized)
    normalized_symbol = normalize_stock_symbol(symbol)
    if normalized_symbol:
        keys.add(normalized_symbol)
    return {key for key in keys if key}


@dataclass
class LiveSnapshotCache:
    """Single in-memory source of truth for latest stock snapshots."""

    snapshots: dict[str, dict[str, Any]] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    failed_symbols: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_updated: float = 0.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def update(
        self,
        symbol: str,
        quote: dict[str, Any] | None = None,
        analysis: dict[str, Any] | None = None,
        *,
        source: str | None = None,
        status: str = "live",
    ) -> dict[str, Any]:
        now_str = _now()
        quote = quote or {}
        analysis = analysis or {}
        primary = normalize_stock_symbol(symbol) or str(symbol or "").strip().upper()
        price = quote.get("current_price", quote.get("price"))
        previous = quote.get("previous_close") or price
        change = quote.get("change")
        if change is None and price is not None and previous:
            change = _number(price) - _number(previous)
        change_percent = quote.get("change_percent", quote.get("change_pct"))
        if change_percent is None and change is not None and previous:
            change_percent = (_number(change) / max(abs(_number(previous)), 0.00001)) * 100

        existing = self.snapshots.get(primary, {})
        snapshot = {
            **existing,
            "symbol": primary,
            "quote": {**existing.get("quote", {}), **quote, "updated_at": quote.get("updated_at") or now_str},
            "analysis": analysis or existing.get("analysis") or {},
            "price": price if price is not None else existing.get("price"),
            "current_price": price if price is not None else existing.get("current_price"),
            "previous_close": previous if previous is not None else existing.get("previous_close"),
            "change": change if change is not None else existing.get("change"),
            "change_pct": round(_number(change_percent), 2) if change_percent is not None else existing.get("change_pct"),
            "change_percent": round(_number(change_percent), 2) if change_percent is not None else existing.get("change_percent"),
            "volume": quote.get("volume", existing.get("volume", 0)),
            "last_updated": now_str,
            "updated_at": now_str,
            "source": source or quote.get("source") or quote.get("provider") or existing.get("source") or "memory",
            "status": status,
        }
        for key in (
            "isin",
            "nse_symbol",
            "bse_symbol",
            "nse_ticker",
            "bse_ticker",
            "preferred_exchange",
            "active_quote_source",
            "fallback_reason",
            "name",
        ):
            if quote.get(key) is not None:
                snapshot[key] = quote.get(key)
            elif analysis.get(key) is not None:
                snapshot[key] = analysis.get(key)

        async with self._lock:
            self.snapshots[primary] = snapshot
            for alias in _symbol_keys(primary, snapshot):
                self.aliases[alias] = primary
            self.failed_symbols.pop(primary, None)
            self.last_updated = time.time()
        return snapshot

    async def mark_failed(self, symbol: str, error: Any) -> None:
        primary = normalize_stock_symbol(symbol) or str(symbol or "").strip().upper()
        payload = {"symbol": primary, "last_error": str(error), "updated_at": _now()}
        async with self._lock:
            self.failed_symbols[primary] = payload

    def get(self, symbol: str) -> dict[str, Any] | None:
        key = str(symbol or "").strip().upper()
        primary = self.aliases.get(key) or self.aliases.get(normalize_stock_symbol(key)) or normalize_stock_symbol(key) or key
        snapshot = self.snapshots.get(primary)
        return dict(snapshot) if snapshot else None

    def all(self) -> dict[str, dict[str, Any]]:
        return {symbol: dict(snapshot) for symbol, snapshot in self.snapshots.items()}

    def delta(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "stock_update",
            "symbol": snapshot.get("symbol"),
            "isin": snapshot.get("isin"),
            "nse_symbol": snapshot.get("nse_symbol"),
            "bse_symbol": snapshot.get("bse_symbol"),
            "nse_ticker": snapshot.get("nse_ticker"),
            "bse_ticker": snapshot.get("bse_ticker"),
            "price": snapshot.get("price"),
            "change_percent": snapshot.get("change_percent", snapshot.get("change_pct")),
            "change_pct": snapshot.get("change_pct", snapshot.get("change_percent")),
            "volume": snapshot.get("volume"),
            "analysis": snapshot.get("analysis") or {},
            "updated_at": snapshot.get("updated_at") or snapshot.get("last_updated"),
            "status": snapshot.get("status") or "live",
        }


class LiveConnectionRegistry:
    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[dict[str, Any]]] = set()
        self._lock = asyncio.Lock()

    async def register(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        async with self._lock:
            self._queues.add(queue)
        return queue

    async def unregister(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            self._queues.discard(queue)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            queues = list(self._queues)
        for queue in queues:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(payload)

    async def heartbeat_loop(self, queue: asyncio.Queue[dict[str, Any]], interval: float = 5.0) -> None:
        while True:
            await asyncio.sleep(interval)
            await queue.put({"type": "heartbeat", "updated_at": _now()})


class DatabaseWriter:
    """Background DB writer. It never blocks quote fetches or streaming."""

    def __init__(self, min_interval_seconds: float = 15.0, batch_size: int = 80) -> None:
        self.min_interval_seconds = min_interval_seconds
        self.batch_size = batch_size
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=5000)
        self._task: asyncio.Task | None = None
        self._last_written: dict[str, float] = {}
        self.last_error = ""

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name="live-db-writer")

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    def enqueue(self, snapshot: dict[str, Any], *, important: bool = False) -> None:
        symbol = str(snapshot.get("symbol") or "").upper()
        now_ts = time.time()
        if not important and symbol and now_ts - self._last_written.get(symbol, 0.0) < self.min_interval_seconds:
            return
        try:
            self.queue.put_nowait({"snapshot": snapshot, "important": important, "attempt": 0})
        except asyncio.QueueFull:
            logger.warning("Live DB writer queue full; dropping non-critical snapshot")

    async def _run(self) -> None:
        while True:
            first = await self.queue.get()
            batch = [first]
            deadline = time.time() + 0.25
            while len(batch) < self.batch_size and time.time() < deadline:
                try:
                    batch.append(self.queue.get_nowait())
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.02)
            await self._flush(batch)

    async def _flush(self, items: list[dict[str, Any]]) -> None:
        if not items:
            return
        try:
            await asyncio.to_thread(self._write_batch, items)
            now_ts = time.time()
            for item in items:
                symbol = str((item.get("snapshot") or {}).get("symbol") or "").upper()
                if symbol:
                    self._last_written[symbol] = now_ts
            self.last_error = ""
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning(f"Live DB writer batch failed; retrying later: {exc}")
            for item in items:
                attempt = int(item.get("attempt") or 0) + 1
                if attempt > 3:
                    continue
                item["attempt"] = attempt
                await asyncio.sleep(min(0.5 * attempt, 2.0))
                with contextlib.suppress(asyncio.QueueFull):
                    self.queue.put_nowait(item)

    def _write_batch(self, items: list[dict[str, Any]]) -> None:
        from ui.v20_store import connect, now

        timestamp = now()
        with connect() as conn:
            for item in items:
                snapshot = item.get("snapshot") or {}
                symbol = str(snapshot.get("symbol") or "").upper()
                if not symbol:
                    continue
                quote = snapshot.get("quote") or {}
                price = snapshot.get("price", quote.get("current_price"))
                change_pct = snapshot.get("change_pct", snapshot.get("change_percent", quote.get("change_pct", 0.0)))
                volume = snapshot.get("volume", quote.get("volume", 0.0))
                conn.execute(
                    """
                    INSERT INTO stocks(symbol, name, sector, industry, market_cap, created_at, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at
                    """,
                    (
                        symbol,
                        snapshot.get("name") or symbol,
                        quote.get("sector") or snapshot.get("sector") or "Unclassified",
                        "",
                        _number(quote.get("market_cap")),
                        timestamp,
                        timestamp,
                    ),
                )
                stock_row = conn.execute("SELECT id FROM stocks WHERE symbol = ?", (symbol,)).fetchone()
                if stock_row:
                    conn.execute(
                        "INSERT INTO stock_prices(stock_id, price, change_pct, volume, price_date, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
                        (stock_row["id"], _number(price), _number(change_pct), _number(volume), timestamp[:10], timestamp, timestamp),
                    )
                conn.execute(
                    """
                    INSERT INTO live_quotes(
                        symbol, price, previous_close, change_pct, volume, provider, market_status,
                        open, day_high, day_low, fifty_day_average, two_hundred_day_average,
                        year_high, year_low, market_cap, pe_ratio, dividend_yield, updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET
                        price=excluded.price, previous_close=excluded.previous_close,
                        change_pct=excluded.change_pct, volume=excluded.volume, provider=excluded.provider,
                        market_status=excluded.market_status, open=excluded.open, day_high=excluded.day_high,
                        day_low=excluded.day_low, fifty_day_average=excluded.fifty_day_average,
                        two_hundred_day_average=excluded.two_hundred_day_average, year_high=excluded.year_high,
                        year_low=excluded.year_low, market_cap=excluded.market_cap, pe_ratio=excluded.pe_ratio,
                        dividend_yield=excluded.dividend_yield, updated_at=excluded.updated_at
                    """,
                    (
                        symbol,
                        _number(price),
                        _number(snapshot.get("previous_close", quote.get("previous_close"))),
                        _number(change_pct),
                        _number(volume),
                        snapshot.get("source") or quote.get("provider") or "live-cache",
                        snapshot.get("status") or "tracked",
                        quote.get("open"),
                        quote.get("day_high") or quote.get("high"),
                        quote.get("day_low") or quote.get("low"),
                        quote.get("fifty_day_average"),
                        quote.get("two_hundred_day_average"),
                        quote.get("year_high"),
                        quote.get("year_low"),
                        quote.get("market_cap"),
                        quote.get("pe_ratio"),
                        quote.get("dividend_yield"),
                        timestamp,
                    ),
                )


stock_snapshot_cache = LiveSnapshotCache()
live_connection_registry = LiveConnectionRegistry()
database_writer = DatabaseWriter()

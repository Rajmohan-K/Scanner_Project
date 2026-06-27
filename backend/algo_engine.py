from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any

from backend import algo_store
from backend.analysis_engine import analysis_engine
from backend.brokers.dummy_broker import DummyBroker
from backend.brokers.kotak_neo_broker import real_trading_enabled
from ui.live_state import stock_snapshot_cache
from utils.logger import logger


ACTIVE_ORDER_STATUSES = {"PENDING", "OPEN", "PARTIAL_EXIT"}
CLOSED_ORDER_STATUSES = {"TARGET_HIT", "STOPLOSS_HIT", "TRAILING_SL_HIT", "CLOSED", "CANCELLED"}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def calculate_quantity(capital: float, available: float, entry: float, stop_loss: float, risk_pct: float) -> int:
    per_share_risk = abs(entry - stop_loss)
    if min(capital, available, entry, per_share_risk, risk_pct) <= 0:
        return 0
    by_risk = int((capital * risk_pct / 100) / per_share_risk)
    by_cash = int(available / entry)
    return max(0, min(by_risk, by_cash))


class AlgoTradingEngine:
    def __init__(self) -> None:
        self.session_id: str | None = None
        self.broker: DummyBroker | None = None
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        algo_store.ensure_schema()

    def _session(self) -> dict[str, Any] | None:
        if self.session_id:
            return algo_store.get_one("algo_sessions", "session_id", self.session_id)
        return next(iter(algo_store.session_rows()), None)

    def _data_health(self) -> dict[str, Any]:
        age = max(0.0, datetime.now().timestamp() - stock_snapshot_cache.last_updated) if stock_snapshot_cache.last_updated else 999999.0
        return {"connected": age <= 30, "age_seconds": round(age, 1), "source": "yfinance"}

    def status(self) -> dict[str, Any]:
        session = self._session()
        session_id = (session or {}).get("session_id")
        return {
            "status": (session or {}).get("status", "IDLE"),
            "session": session,
            "selected_trade": json.loads((session or {}).get("selected_trade_json") or "null"),
            "paper_mode": True,
            "real_trading_enabled": real_trading_enabled(),
            "real_orders_disabled": not real_trading_enabled(),
            "kotak_neo_connected": False,
            "market_data": self._data_health(),
            "portfolio": self.portfolio(),
            "orders": algo_store.order_rows(session_id),
            "trades_today": algo_store.trade_rows(today_only=True),
            "performance": self.performance(),
        }

    async def start(self, config: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            current = self._session()
            if current and current.get("status") in {"RUNNING", "STARTING"}:
                return self.status()
            capital = _number(config.get("capital"))
            max_trades = int(config.get("max_trades") or 3)
            max_loss = _number(config.get("max_loss"))
            risk_pct = _number(config.get("risk_per_trade"), 1.0)
            if capital <= 0 or max_trades <= 0 or max_loss <= 0 or not 0 < risk_pct <= 5:
                raise ValueError("Valid capital, max trades, max loss, and risk percentage are required")
            if config.get("real_trading"):
                if not real_trading_enabled():
                    raise PermissionError("Real trading is disabled by REAL_TRADING_ENABLED")
                raise PermissionError("Realtime algo execution is paper-only in this release")
            if config.get("dummy_trading") is False:
                raise PermissionError("Dummy trading must remain enabled")
            self.session_id = uuid.uuid4().hex
            timestamp = algo_store.now()
            algo_store.insert("algo_sessions", {
                "session_id": self.session_id, "mode": "PAPER", "status": "STARTING", "capital": capital,
                "available_funds": capital, "max_trades": max_trades, "max_loss": max_loss,
                "risk_per_trade": risk_pct, "selected_trade_json": None, "stop_reason": "",
                "started_at": timestamp, "stopped_at": None, "created_at": timestamp, "updated_at": timestamp,
            })
            self.broker = DummyBroker(self.session_id, capital)
            algo_store.insert("broker_accounts", {
                "account_id": f"PAPER-{self.session_id[:12]}", "broker": "kotak_neo", "mode": "PAPER",
                "connected": 1, "details_json": json.dumps({"execution": "dummy", "market_data": "yfinance"}),
                "created_at": timestamp, "updated_at": timestamp,
            })
            algo_store.update("algo_sessions", "session_id", self.session_id, {"status": "RUNNING", "updated_at": algo_store.now()})
            self._task = asyncio.create_task(self._run_loop(), name=f"algo-paper-{self.session_id[:8]}")
            return self.status()

    async def stop(self, reason: str = "Stopped by user") -> dict[str, Any]:
        async with self._lock:
            if self.broker:
                for order in self.broker.get_orders():
                    if order.get("status") not in ACTIVE_ORDER_STATUSES:
                        continue
                    price = self._quote_price(str(order.get("symbol") or "")) or _number(order.get("current_price")) or _number(order.get("entry_price"))
                    side_sign = 1 if order.get("side") == "BUY" else -1
                    remaining = int(order.get("remaining_quantity") or 0)
                    pnl = (price - _number(order.get("entry_price"))) * remaining * side_sign
                    closed = self.broker.modify_order(str(order["order_id"]), {
                        "current_price": price, "pnl": round(pnl, 2), "status": "CLOSED",
                        "exit_reason": reason, "closed_at": algo_store.now(),
                    })
                    self._record_trade(closed)
            if self.session_id:
                algo_store.update("algo_sessions", "session_id", self.session_id, {
                    "status": "STOPPED", "stop_reason": reason, "stopped_at": algo_store.now(), "updated_at": algo_store.now(),
                })
            task = self._task
            self._task = None
            if task and task is not asyncio.current_task() and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            return self.status()

    async def shutdown(self) -> None:
        await self.stop("Backend shutdown")

    async def _run_loop(self) -> None:
        try:
            while True:
                session = self._session()
                if not session or session.get("status") != "RUNNING":
                    return
                if not self._data_health()["connected"]:
                    await self.stop("Live Yahoo market data disconnected or stale")
                    return
                await self._update_positions(session)
                await self._maybe_open_trade(session)
                self._refresh_performance(session)
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"Paper algo loop stopped safely: {exc}", exc_info=True)
            if self.session_id:
                algo_store.update("algo_sessions", "session_id", self.session_id, {
                    "status": "STOPPED", "stop_reason": f"Safety stop: {exc}", "stopped_at": algo_store.now(), "updated_at": algo_store.now(),
                })

    def _quote_price(self, symbol: str) -> float:
        snapshot = stock_snapshot_cache.get(symbol) or {}
        return _number(snapshot.get("current_price") or snapshot.get("price") or (snapshot.get("quote") or {}).get("current_price"))

    async def _maybe_open_trade(self, session: dict[str, Any]) -> None:
        if not self.broker:
            return
        orders = self.broker.get_orders()
        if any(row.get("status") in ACTIVE_ORDER_STATUSES for row in orders):
            return
        trades = algo_store.trade_rows(today_only=True)
        todays_orders = [row for row in algo_store.order_rows() if str(row.get("created_at") or "").startswith(date.today().isoformat())]
        if len(todays_orders) >= int(session.get("max_trades") or 0):
            await self.stop("Maximum trades per day reached")
            return
        if sum(_number(row.get("net_pnl")) for row in trades) <= -abs(_number(session.get("max_loss"))):
            await self.stop("Daily maximum loss lock triggered")
            return
        # Select PENDING trades from execution queue where sent_to_algo = YES
        queue_items = [
            row for row in algo_store.list_rows("algo_execution_queue")
            if row.get("execution_status") == "PENDING" and row.get("sent_to_algo") == "YES"
        ]
        if not queue_items:
            return

        # Execute the highest score queue item
        queue_items.sort(key=lambda r: _number(r.get("algo_score")), reverse=True)
        candidate = queue_items[0]
        symbol = candidate["symbol"]

        if any(row.get("symbol") == symbol for row in orders):
            algo_store.update("algo_execution_queue", "symbol", symbol, {
                "execution_status": "CANCELLED",
                "updated_at": algo_store.now()
            })
            return

        funds = self.broker.get_funds()
        quantity = int(candidate.get("quantity") or calculate_quantity(
            _number(session.get("capital")), _number(funds.get("available")), candidate["entry_price"],
            candidate["stop_loss"], _number(session.get("risk_per_trade")),
        ))
        if quantity <= 0:
            algo_store.update("algo_execution_queue", "symbol", symbol, {
                "execution_status": "FAILED",
                "updated_at": algo_store.now()
            })
            return

        order = self.broker.place_order({
            "symbol": symbol,
            "side": candidate["side"],
            "entry_price": candidate["entry_price"],
            "stop_loss": candidate["stop_loss"],
            "target": candidate["target"],
            "quantity": quantity,
            "confidence": candidate["confidence"],
            "strategy_reason": f"Execution Queue Rank: {candidate.get('algo_score')}"
        })

        algo_store.update("algo_execution_queue", "symbol", symbol, {
            "execution_status": "EXECUTED",
            "updated_at": algo_store.now()
        })

        selected_trade = {
            "symbol": symbol,
            "side": candidate["side"],
            "entry_price": candidate["entry_price"],
            "stop_loss": candidate["stop_loss"],
            "target": candidate["target"],
            "confidence": candidate["confidence"],
            "selection_score": candidate["algo_score"],
            "risk_reward": round(abs(candidate["target"] - candidate["entry_price"]) / max(0.01, abs(candidate["entry_price"] - candidate["stop_loss"])), 2),
            "strategy_reason": f"Execution Queue Order"
        }

        algo_store.update("algo_sessions", "session_id", self.session_id, {
            "selected_trade_json": json.dumps(selected_trade), "available_funds": self.broker.get_funds()["available"], "updated_at": algo_store.now(),
        })
        logger.info(f"Paper algo opened queue trade {order.get('side')} {order.get('symbol')} x {order.get('quantity')}")

    async def _update_positions(self, session: dict[str, Any]) -> None:
        if not self.broker:
            return
        for order in self.broker.get_orders():
            if order.get("status") not in ACTIVE_ORDER_STATUSES:
                continue
            price = self._quote_price(str(order.get("symbol") or ""))
            if price <= 0:
                continue
            side = str(order.get("side") or "BUY")
            entry = _number(order.get("entry_price"))
            remaining = int(order.get("remaining_quantity") or 0)
            sign = 1 if side == "BUY" else -1
            unrealized = (price - entry) * remaining * sign
            profit_pct = ((price - entry) / entry * 100 * sign) if entry else 0
            stop = _number(order.get("stop_loss"))
            new_stop = stop
            if profit_pct >= 2:
                locked = entry * (1.01 if side == "BUY" else 0.99)
                new_stop = max(stop, locked) if side == "BUY" else min(stop, locked)
            elif profit_pct >= 1:
                new_stop = max(stop, entry) if side == "BUY" else min(stop, entry)
            patch: dict[str, Any] = {"current_price": price, "pnl": round(unrealized, 2), "stop_loss": round(new_stop, 2), "trailing_stop_loss": round(new_stop, 2)}
            target_hit = (side == "BUY" and price >= _number(order.get("target"))) or (side == "SELL" and price <= _number(order.get("target")))
            stop_hit = (side == "BUY" and price <= new_stop) or (side == "SELL" and price >= new_stop)
            if profit_pct >= 4 and remaining == int(order.get("quantity") or 0) and remaining > 1 and not target_hit:
                exit_qty = max(1, remaining // 2)
                partial_pnl = (price - entry) * exit_qty * sign
                patch.update({"remaining_quantity": remaining - exit_qty, "realized_pnl": round(partial_pnl, 2), "status": "PARTIAL_EXIT"})
            if target_hit or stop_hit:
                status = "TARGET_HIT" if target_hit else ("TRAILING_SL_HIT" if new_stop != _number(order.get("initial_stop_loss")) else "STOPLOSS_HIT")
                reason = "Target reached" if target_hit else ("Trailing stop reached" if status == "TRAILING_SL_HIT" else "Initial stop loss reached")
                patch.update({"status": status, "exit_reason": reason, "closed_at": algo_store.now()})
            updated = self.broker.modify_order(str(order["order_id"]), patch)
            if updated.get("status") in CLOSED_ORDER_STATUSES:
                self._record_trade(updated)

    def _record_trade(self, order: dict[str, Any]) -> None:
        if algo_store.get_one("algo_trades", "order_id", order["order_id"]):
            return
        side_sign = 1 if order.get("side") == "BUY" else -1
        quantity = int(order.get("quantity") or 0)
        entry = _number(order.get("entry_price"))
        exit_price = _number(order.get("current_price"))
        remaining = int(order.get("remaining_quantity") or quantity)
        gross = _number(order.get("realized_pnl")) + (exit_price - entry) * remaining * side_sign
        charges = round((entry + exit_price) * quantity * 0.0005, 2)
        net = round(gross - charges, 2)
        won = net > 0
        improvement = {
            "selection": order.get("strategy_reason") or "Highest-confidence watchlist setup",
            "outcome": "Momentum and risk controls held" if won else "Price invalidated the selected setup",
            "entry_late": abs(exit_price - entry) / entry * 100 > 3 if entry else False,
            "stop_assessment": "Review stop width" if order.get("status") == "STOPLOSS_HIT" else "Stop protected the position",
            "target_assessment": "Target was reached" if order.get("status") == "TARGET_HIT" else "Revalidate target against current volatility",
            "volume_confirmation": "Strong" if _number(order.get("confidence")) >= 80 else "Moderate",
            "next_improvement": "Require renewed VWAP and volume confirmation before the next similar entry",
            "avoid_similar_setup": not won,
        }
        algo_store.insert("algo_trades", {
            "trade_id": uuid.uuid4().hex, "order_id": order["order_id"], "session_id": order["session_id"],
            "symbol": order["symbol"], "side": order["side"], "quantity": quantity, "entry_price": entry,
            "exit_price": exit_price, "gross_pnl": round(gross, 2), "charges": charges, "net_pnl": net,
            "exit_reason": order.get("exit_reason"), "confidence": _number(order.get("confidence")),
            "strategy_reason": order.get("strategy_reason"), "improvement_json": json.dumps(improvement),
            "opened_at": order.get("created_at"), "closed_at": algo_store.now(),
        })

    def _refresh_performance(self, session: dict[str, Any]) -> None:
        trades = algo_store.trade_rows(today_only=True)
        orders = algo_store.order_rows(self.session_id)
        unrealized = sum(_number(row.get("pnl")) for row in orders if row.get("status") in ACTIVE_ORDER_STATUSES)
        realized = sum(_number(row.get("gross_pnl")) for row in trades)
        charges = sum(_number(row.get("charges")) for row in trades)
        payload = {
            "trade_date": date.today().isoformat(), "capital": _number(session.get("capital")), "total_trades": len(trades),
            "winning_trades": sum(1 for row in trades if _number(row.get("net_pnl")) > 0),
            "losing_trades": sum(1 for row in trades if _number(row.get("net_pnl")) <= 0),
            "realized_pnl": round(realized, 2), "unrealized_pnl": round(unrealized, 2), "charges": round(charges, 2),
            "net_pnl": round(realized + unrealized - charges, 2),
            "snapshots_json": json.dumps([{"time": algo_store.now(), "pnl": round(realized + unrealized - charges, 2)}]),
            "updated_at": algo_store.now(),
        }
        existing = algo_store.get_one("algo_daily_performance", "trade_date", payload["trade_date"])
        if existing:
            try:
                history = json.loads(existing.get("snapshots_json") or "[]")[-119:]
            except (TypeError, json.JSONDecodeError):
                history = []
            history.extend(json.loads(payload["snapshots_json"]))
            payload["snapshots_json"] = json.dumps(history)
            algo_store.update("algo_daily_performance", "trade_date", payload["trade_date"], payload)
        else:
            algo_store.insert("algo_daily_performance", payload)
        if self.broker:
            algo_store.update("algo_sessions", "session_id", self.session_id, {
                "available_funds": self.broker.get_funds()["available"], "updated_at": algo_store.now(),
            })

    def portfolio(self) -> dict[str, Any]:
        session = self._session() or {}
        orders = algo_store.order_rows(session.get("session_id")) if session else []
        trades = algo_store.trade_rows(today_only=True)
        open_orders = [row for row in orders if row.get("status") in ACTIVE_ORDER_STATUSES]
        used = sum(_number(row.get("current_price")) * int(row.get("remaining_quantity") or 0) for row in open_orders)
        realized = sum(_number(row.get("gross_pnl")) for row in trades)
        unrealized = sum(_number(row.get("pnl")) for row in open_orders)
        charges = sum(_number(row.get("charges")) for row in trades)
        capital = _number(session.get("capital"))
        return {
            "capital_allocated": capital, "available_funds": max(0.0, capital + realized - charges - used), "used_margin": round(used, 2),
            "open_positions": len(open_orders), "closed_positions": len(trades), "total_trades": len(trades),
            "winning_trades": sum(1 for row in trades if _number(row.get("net_pnl")) > 0),
            "losing_trades": sum(1 for row in trades if _number(row.get("net_pnl")) <= 0),
            "overall_pnl": round(realized + unrealized, 2), "realized_pnl": round(realized, 2),
            "unrealized_pnl": round(unrealized, 2), "charges": round(charges, 2), "net_pnl": round(realized + unrealized - charges, 2),
        }

    def performance(self) -> dict[str, Any]:
        row = algo_store.get_one("algo_daily_performance", "trade_date", date.today().isoformat()) or {}
        try:
            row["snapshots"] = json.loads(row.get("snapshots_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            row["snapshots"] = []
        return row

    def place_dummy_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.broker:
            raise ValueError("Start a paper algo session first")
        return self.broker.place_order(payload)

    def modify_dummy_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.broker:
            raise ValueError("Start a paper algo session first")
        return self.broker.modify_order(str(payload.get("order_id") or ""), payload)

    def cancel_dummy_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.broker:
            raise ValueError("Start a paper algo session first")
        return self.broker.cancel_order(str(payload.get("order_id") or ""))


algo_trading_engine = AlgoTradingEngine()

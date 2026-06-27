from __future__ import annotations

import uuid
from typing import Any

from backend import algo_store
from backend.brokers.base_broker import BaseBroker, BrokerError


class DummyBroker(BaseBroker):
    name = "dummy"
    paper_mode = True

    def __init__(self, session_id: str, capital: float) -> None:
        self.session_id = session_id
        self.capital = float(capital)

    def login(self) -> dict[str, Any]:
        return {"status": "connected", "broker": self.name, "mode": "paper"}

    def refresh_token(self) -> dict[str, Any]:
        return {"status": "not_required", "broker": self.name}

    def get_profile(self) -> dict[str, Any]:
        return {"account_id": f"PAPER-{self.session_id[:8]}", "broker": self.name, "mode": "paper"}

    def get_funds(self) -> dict[str, Any]:
        open_orders = [row for row in self.get_orders() if row.get("status") in {"OPEN", "PARTIAL_EXIT"}]
        used = sum(float(row.get("current_price") or row.get("entry_price") or 0) * int(row.get("remaining_quantity") or 0) for row in open_orders)
        realized = sum(float(row.get("net_pnl") or 0) for row in algo_store.trade_rows(session_id=self.session_id))
        return {"capital": self.capital, "available": max(0.0, self.capital + realized - used), "used_margin": used}

    def get_positions(self) -> list[dict[str, Any]]:
        return algo_store.position_rows(self.session_id)

    def get_holdings(self) -> list[dict[str, Any]]:
        return []

    def get_orders(self) -> list[dict[str, Any]]:
        return algo_store.order_rows(self.session_id)

    def place_order(self, order: dict[str, Any]) -> dict[str, Any]:
        symbol = str(order.get("symbol") or "").strip().upper()
        side = str(order.get("side") or "BUY").strip().upper()
        quantity = int(order.get("quantity") or 0)
        entry = float(order.get("entry_price") or 0)
        if not symbol or side not in {"BUY", "SELL"} or quantity <= 0 or entry <= 0:
            raise BrokerError("A valid symbol, side, quantity, and entry price are required")
        active = [row for row in self.get_orders() if row.get("symbol") == symbol and row.get("status") in {"PENDING", "OPEN", "PARTIAL_EXIT"}]
        if active:
            raise BrokerError(f"An active paper order already exists for {symbol}")
        timestamp = algo_store.now()
        order_id = uuid.uuid4().hex
        row = {
            "order_id": order_id, "session_id": self.session_id, "symbol": symbol, "side": side,
            "quantity": quantity, "remaining_quantity": quantity, "entry_price": entry, "current_price": entry,
            "initial_stop_loss": float(order.get("stop_loss") or entry), "stop_loss": float(order.get("stop_loss") or entry),
            "trailing_stop_loss": float(order.get("stop_loss") or entry), "target": float(order.get("target") or entry),
            "status": "PENDING", "pnl": 0.0, "realized_pnl": 0.0, "charges": 0.0, "exit_reason": "",
            "confidence": float(order.get("confidence") or 0), "strategy_reason": str(order.get("strategy_reason") or ""),
            "broker": self.name, "source": "yfinance", "created_at": timestamp, "updated_at": timestamp, "closed_at": None,
        }
        algo_store.insert("algo_orders", row)
        algo_store.update("algo_orders", "order_id", order_id, {"status": "OPEN", "updated_at": algo_store.now()})
        algo_store.insert("algo_positions", {
            "position_id": uuid.uuid4().hex, "order_id": order_id, "session_id": self.session_id,
            "symbol": symbol, "side": side, "quantity": quantity, "remaining_quantity": quantity,
            "average_price": entry, "current_price": entry, "unrealized_pnl": 0.0, "realized_pnl": 0.0,
            "status": "OPEN", "created_at": timestamp, "updated_at": timestamp,
        })
        return self.get_order_status(order_id)

    def modify_order(self, order_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        allowed = {key: changes[key] for key in ("quantity", "remaining_quantity", "stop_loss", "trailing_stop_loss", "target", "current_price", "pnl", "realized_pnl", "charges", "status", "exit_reason", "closed_at") if key in changes}
        allowed["updated_at"] = algo_store.now()
        updated = algo_store.update("algo_orders", "order_id", order_id, allowed)
        if not updated:
            raise BrokerError("Paper order not found")
        position_changes = {key: value for key, value in {
            "remaining_quantity": allowed.get("remaining_quantity"), "current_price": allowed.get("current_price"),
            "unrealized_pnl": allowed.get("pnl"), "realized_pnl": allowed.get("realized_pnl"), "status": allowed.get("status"),
            "updated_at": allowed.get("updated_at"),
        }.items() if value is not None}
        if position_changes:
            algo_store.update("algo_positions", "order_id", order_id, position_changes)
        return updated

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        order = self.get_order_status(order_id)
        if not order:
            raise BrokerError("Paper order not found")
        if order.get("status") not in {"PENDING", "OPEN"}:
            raise BrokerError("Only pending or open paper orders can be cancelled")
        return self.modify_order(order_id, {"status": "CANCELLED", "exit_reason": "Cancelled by user", "closed_at": algo_store.now()})

    def place_gtt(self, order: dict[str, Any]) -> dict[str, Any]:
        return {"status": "simulated", "type": "GTT", **order}

    def modify_gtt(self, order_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        return {"status": "simulated", "order_id": order_id, **changes}

    def cancel_gtt(self, order_id: str) -> dict[str, Any]:
        return {"status": "cancelled", "order_id": order_id}

    def get_order_status(self, order_id: str) -> dict[str, Any]:
        return algo_store.get_one("algo_orders", "order_id", order_id) or {}

    def get_trade_book(self) -> list[dict[str, Any]]:
        return algo_store.trade_rows(session_id=self.session_id)

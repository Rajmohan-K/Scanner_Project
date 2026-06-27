from __future__ import annotations

import os
from typing import Any, Callable

from backend.brokers.base_broker import BaseBroker, BrokerError, RealTradingDisabledError


def real_trading_enabled() -> bool:
    return os.getenv("REAL_TRADING_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


class KotakNeoBroker(BaseBroker):
    """Kotak Neo order adapter. All write operations are fail-closed by default."""

    name = "kotak_neo"
    paper_mode = False

    def __init__(self, client: Any | None = None) -> None:
        self.client = client

    def _client(self) -> Any:
        if self.client is not None:
            return self.client
        try:
            from neo_api_client import NeoAPI
        except ImportError as exc:
            raise BrokerError("neo-api-client is not installed") from exc
        consumer_key = os.getenv("KOTAK_NEO_CONSUMER_KEY", "").strip()
        environment = os.getenv("KOTAK_NEO_ENVIRONMENT", "prod").strip() or "prod"
        if not consumer_key:
            raise BrokerError("Kotak Neo credentials are not configured")
        self.client = NeoAPI(consumer_key=consumer_key, environment=environment)
        return self.client

    def _read(self, *names: str, **kwargs: Any) -> Any:
        client = self._client()
        method: Callable[..., Any] | None = next((getattr(client, name, None) for name in names if callable(getattr(client, name, None))), None)
        if method is None:
            raise BrokerError(f"Kotak Neo client does not expose {names[0]}")
        return method(**kwargs)

    def _write(self, names: tuple[str, ...], **kwargs: Any) -> Any:
        if not real_trading_enabled():
            raise RealTradingDisabledError("Real Kotak Neo order placement is disabled")
        return self._read(*names, **kwargs)

    def login(self) -> dict[str, Any]:
        result = self._read(
            "login",
            mobilenumber=os.getenv("KOTAK_NEO_MOBILE", ""),
            password=os.getenv("KOTAK_NEO_PASSWORD", ""),
        )
        return result or {"status": "connected"}

    def refresh_token(self) -> dict[str, Any]:
        return self._read("session_2fa", "refresh_token", OTP=os.getenv("KOTAK_NEO_MPIN", "")) or {}

    def get_profile(self) -> dict[str, Any]:
        return self._read("client_details", "get_profile") or {}

    def get_funds(self) -> dict[str, Any]:
        return self._read("limits", "get_funds", segment="ALL", exchange="ALL", product="ALL") or {}

    def get_positions(self) -> list[dict[str, Any]]:
        return self._read("positions", "get_positions") or []

    def get_holdings(self) -> list[dict[str, Any]]:
        return self._read("holdings", "get_holdings") or []

    def get_orders(self) -> list[dict[str, Any]]:
        return self._read("order_report", "get_orders") or []

    def place_order(self, order: dict[str, Any]) -> dict[str, Any]:
        return self._write(("place_order",), **order) or {}

    def modify_order(self, order_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        return self._write(("modify_order",), order_id=order_id, **changes) or {}

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return self._write(("cancel_order",), order_id=order_id) or {}

    def place_gtt(self, order: dict[str, Any]) -> dict[str, Any]:
        return self._write(("place_gtt", "place_gtt_order"), **order) or {}

    def modify_gtt(self, order_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        return self._write(("modify_gtt", "modify_gtt_order"), order_id=order_id, **changes) or {}

    def cancel_gtt(self, order_id: str) -> dict[str, Any]:
        return self._write(("cancel_gtt", "cancel_gtt_order"), order_id=order_id) or {}

    def get_order_status(self, order_id: str) -> dict[str, Any]:
        return self._read("order_history", "get_order_status", order_id=order_id) or {}

    def get_trade_book(self) -> list[dict[str, Any]]:
        return self._read("trade_report", "get_trade_book") or []

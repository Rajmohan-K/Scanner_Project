from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BrokerError(RuntimeError):
    pass


class RealTradingDisabledError(BrokerError):
    pass


class BaseBroker(ABC):
    """Order-broker contract. Market data intentionally does not belong here."""

    name = "base"
    paper_mode = True

    @abstractmethod
    def login(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def refresh_token(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_profile(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_funds(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_holdings(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_orders(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def place_order(self, order: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def modify_order(self, order_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def place_gtt(self, order: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def modify_gtt(self, order_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def cancel_gtt(self, order_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_order_status(self, order_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_trade_book(self) -> list[dict[str, Any]]:
        raise NotImplementedError

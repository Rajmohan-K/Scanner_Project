from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


class AnalysisEngine:
    """Ranks only centralized High-Profitable Trade Suggestions."""

    min_confidence = 70.0
    min_risk_reward = 1.8
    max_data_age_seconds = 30.0
    max_already_moved_pct = 1.5

    @staticmethod
    def _breakout_window_open(now: datetime | None = None) -> bool:
        current = (now or datetime.now(ZoneInfo("Asia/Kolkata"))).astimezone(ZoneInfo("Asia/Kolkata"))
        minutes = current.hour * 60 + current.minute
        return minutes >= 9 * 60 + 45

    def _normalize(self, suggestion: dict[str, Any], snapshot: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
        symbol = str(suggestion.get("symbol") or snapshot.get("symbol") or "").upper()
        side = str(suggestion.get("direction") or snapshot.get("direction") or "BUY").upper()
        entry = _number(suggestion.get("entry_price") or suggestion.get("suggested_price") or snapshot.get("entry") or snapshot.get("current_price"))
        current = _number(snapshot.get("current_price") or snapshot.get("price") or suggestion.get("current_price") or entry)
        stop = _number(suggestion.get("stop_loss") or snapshot.get("stop_loss"))
        target = _number(suggestion.get("target_1") or snapshot.get("target1"))
        risk = abs(entry - stop)
        reward = abs(target - entry)
        risk_reward = _number(snapshot.get("risk_reward_ratio"), reward / risk if risk > 0 else 0)
        confidence = max(
            _number(suggestion.get("latest_confidence")),
            _number(suggestion.get("initial_confidence")),
            _number(snapshot.get("confidence")),
            _number(snapshot.get("quality_score")),
        )
        volume_ratio = _number(snapshot.get("volume_spike") or snapshot.get("relative_volume"), 0)
        vwap = _number(snapshot.get("vwap"))
        vwap_confirmed = bool(vwap and ((side == "BUY" and current >= vwap) or (side == "SELL" and current <= vwap)))
        reason = str(suggestion.get("initial_reason") or suggestion.get("reason") or snapshot.get("reason") or "")
        breakout_confirmed = "breakout" in reason.lower() or bool(snapshot.get("breakout_confirmed"))
        trend_strength = _number(snapshot.get("trend_strength") or snapshot.get("quality_score") or confidence)
        profit_potential = abs(target - entry) / entry * 100 if entry and target else 0
        moved_pct = abs(current - entry) / entry * 100 if entry else 999
        updated = _timestamp(snapshot.get("updated_at") or snapshot.get("last_checked") or suggestion.get("updated_at") or suggestion.get("suggested_time"))
        reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        age_seconds = max(0.0, (reference - updated).total_seconds()) if updated else 999999.0
        score = (
            confidence * 0.34
            + min(profit_potential * 10, 100) * 0.18
            + min(volume_ratio * 35, 100) * 0.14
            + min(risk_reward * 25, 100) * 0.14
            + min(trend_strength, 100) * 0.12
            + (8 if vwap_confirmed else 0)
            + (6 if breakout_confirmed else 0)
        )
        return {
            "symbol": symbol, "side": side, "entry_price": round(entry, 2), "current_price": round(current, 2),
            "stop_loss": round(stop, 2), "target": round(target, 2), "confidence": round(confidence, 2),
            "profit_potential_pct": round(profit_potential, 2), "volume_ratio": round(volume_ratio, 2),
            "risk_reward": round(risk_reward, 2), "trend_strength": round(trend_strength, 2),
            "vwap_confirmed": vwap_confirmed, "breakout_confirmed": breakout_confirmed,
            "already_moved_pct": round(moved_pct, 2), "data_age_seconds": round(age_seconds, 2),
            "selection_score": round(score, 2), "strategy_reason": reason or "Highest-ranked centralized watchlist suggestion",
        }

    def rank_candidates(self, candidates: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
        ranked: list[dict[str, Any]] = []
        for candidate in candidates:
            normalized = self._normalize(candidate.get("suggestion") or candidate, candidate.get("snapshot") or {}, now)
            if not normalized["symbol"] or normalized["side"] not in {"BUY", "SELL"}:
                continue
            if min(normalized["entry_price"], normalized["stop_loss"], normalized["target"]) <= 0:
                continue
            if normalized["confidence"] < self.min_confidence or normalized["risk_reward"] < self.min_risk_reward:
                continue
            if normalized["data_age_seconds"] > self.max_data_age_seconds:
                continue
            if normalized["already_moved_pct"] > self.max_already_moved_pct:
                continue
            if normalized["breakout_confirmed"] and not self._breakout_window_open(now):
                continue
            ranked.append(normalized)
        return sorted(ranked, key=lambda row: row["selection_score"], reverse=True)

    def best_trade(self) -> dict[str, Any] | None:
        from ui.stock_registry import stock_registry
        from ui.watchlist_monitor import watchlist_monitor

        snapshots: dict[str, dict[str, Any]] = {}
        for item in watchlist_monitor.list_items():
            keys = {
                str(item.get("symbol") or "").upper(),
                str(item.get("nse_symbol") or "").upper(),
                str(item.get("nse_ticker") or "").upper(),
            }
            for key in keys:
                if key:
                    snapshots[key.replace(".NS", "")] = {**(item.get("snapshot") or {}), "last_checked": item.get("last_checked")}
        candidates = []
        for symbol, suggestion in stock_registry.active_suggestions.items():
            normalized = str(symbol or "").upper().replace(".NS", "").replace(".BO", "")
            candidates.append({"suggestion": {**suggestion, "symbol": symbol}, "snapshot": snapshots.get(normalized, {})})
        ranked = self.rank_candidates(candidates)
        return ranked[0] if ranked else None


analysis_engine = AnalysisEngine()

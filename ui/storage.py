from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _scan_path(scan_id: str) -> Path:
    return DATA_DIR / f"{scan_id}.json"


def save_scan(payload: dict[str, Any], scan_id: str | None = None) -> str:
    scan_id = scan_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    record = {
        "scan_id": scan_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        **payload,
    }
    _scan_path(scan_id).write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    return scan_id


def load_scan(scan_id: str) -> dict[str, Any] | None:
    path = _scan_path(scan_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_scans(limit: int = 30) -> list[dict[str, Any]]:
    scans = []
    for path in sorted(DATA_DIR.glob("*.json"), reverse=True):
        if path.name == "settings.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if not payload.get("scan_id") and "results" not in payload and "ranked" not in payload:
            continue
        scans.append(
            {
                "scan_id": payload.get("scan_id", path.stem),
                "created_at": payload.get("created_at", ""),
                "message": payload.get("message", ""),
                "scan_mode": payload.get("scan_mode", "standard"),
                "scan_family": payload.get("scan_family", ""),
                "scanner_bucket": payload.get("scanner_bucket", ""),
                "pipeline_stage": payload.get("pipeline_stage", ""),
                "scanner_display_name": payload.get("scanner_display_name", ""),
                "symbols_scanned": payload.get("symbols_scanned", 0),
                "candidates_considered": payload.get("candidates_considered", 0),
                "qualified": payload.get("summary", {}).get("qualified", 0),
                "avg_premarket_grade": payload.get("summary", {}).get("avg_premarket_grade", 0),
                "avg_ml_probability": payload.get("summary", {}).get("avg_ml_probability", 0),
                "intraday_ready": payload.get("summary", {}).get("intraday_ready", 0),
                "swing_ready": payload.get("summary", {}).get("swing_ready", 0),
            }
        )
        if len(scans) >= limit:
            break
    return scans


def settings_path() -> Path:
    return DATA_DIR / "settings.json"


def save_settings(settings: dict[str, Any]) -> None:
    path = settings_path()
    path.write_text(json.dumps(settings, indent=2, default=str), encoding="utf-8")


def load_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def stock_history(stock: str, limit: int = 25) -> list[dict[str, Any]]:
    history = []
    for item in list_scans(limit=200):
        payload = load_scan(item["scan_id"])
        if not payload:
            continue
        for record in payload.get("results", []):
            if record.get("stock") != stock:
                continue
            history.append(
                {
                    "scan_id": item["scan_id"],
                    "created_at": payload.get("created_at", ""),
                    "stock": stock,
                    "premarket_grade": record.get("premarket_grade", 0),
                    "ml_probability": record.get("ml_probability", 0),
                    "score": record.get("score", 0),
                    "confidence_pct": record.get("confidence_pct", 0),
                    "event_score": record.get("event_score", 0),
                    "best_horizon": record.get("best_horizon", ""),
                    "premarket_action": record.get("premarket_action", ""),
                }
            )
            break
        if len(history) >= limit:
            break
    return list(reversed(history))


def strategies_dir() -> Path:
    directory = DATA_DIR / "strategies"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _strategy_path(strategy_id: str) -> Path:
    return strategies_dir() / f"{strategy_id}.json"


def save_strategy(strategy: dict[str, Any]) -> str:
    strategy_id = strategy.get("strategy_id") or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    record = {
        "strategy_id": strategy_id,
        "created_at": strategy.get("created_at") or datetime.now().isoformat(timespec="seconds"),
        **strategy,
    }
    _strategy_path(strategy_id).write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    return strategy_id


def load_strategy(strategy_id: str) -> dict[str, Any] | None:
    path = _strategy_path(strategy_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("deleted_at"):
            return None
        return payload
    except Exception:
        return None


def list_strategies(limit: int = 50) -> list[dict[str, Any]]:
    strategies = []
    for path in sorted(strategies_dir().glob("*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload.get("deleted_at"):
            continue
        strategies.append({
            "strategy_id": payload.get("strategy_id", path.stem),
            "name": payload.get("name", "Unnamed Strategy"),
            "created_at": payload.get("created_at", ""),
            "description": payload.get("description", ""),
            "horizon": payload.get("horizon", ""),
        })
        if len(strategies) >= limit:
            break
    return strategies


def delete_strategy(strategy_id: str) -> bool:
    path = _strategy_path(strategy_id)
    if path.exists():
        for attempt in range(5):
            try:
                os.chmod(path, 0o666)
                path.unlink()
                return True
            except PermissionError:
                if attempt == 4:
                    try:
                        payload = json.loads(path.read_text(encoding="utf-8"))
                    except Exception:
                        payload = {"strategy_id": strategy_id}
                    payload["deleted_at"] = datetime.now().isoformat(timespec="seconds")
                    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
                    return True
                time.sleep(0.1 * (attempt + 1))
        return False
    return False

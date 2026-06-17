from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests


class TelegramDeliveryError(RuntimeError):
    pass


ALIASES = {
    "Intraday": "Intraday_Stocks",
    "Swing": "Swing_Stocks",
    "Watchlist": "Others",
    "Stock Scanner": "Others",
}

ENV_KEYS = {
    "Intraday_Stocks": ("TELEGRAM_INTRADAY_BOT_TOKEN", "TELEGRAM_INTRADAY_CHAT_IDS"),
    "Swing_Stocks": ("TELEGRAM_SWING_BOT_TOKEN", "TELEGRAM_SWING_CHAT_IDS"),
    "Premarket": ("TELEGRAM_PREMARKET_BOT_TOKEN", "TELEGRAM_PREMARKET_CHAT_IDS"),
    "Others": ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_IDS"),
}


def _load_project_env() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        return


_load_project_env()


def _category_key(category: str | None) -> str:
    normalized = ALIASES.get(str(category or "").strip(), str(category or "").strip())
    return normalized if normalized in ENV_KEYS else "Others"


def _csv_env(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


def telegram_config_status(category: str | None = None) -> dict[str, Any]:
    resolved = _category_key(category)
    token_key, chat_key = ENV_KEYS[resolved]
    token = os.getenv(token_key) or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_ids = _csv_env(chat_key) or _csv_env("TELEGRAM_CHAT_IDS")
    return {
        "category": resolved,
        "token_key": token_key if os.getenv(token_key) else "TELEGRAM_BOT_TOKEN",
        "chat_key": chat_key if _csv_env(chat_key) else "TELEGRAM_CHAT_IDS",
        "has_token": bool(token),
        "chat_count": len(chat_ids),
        "configured": bool(token and chat_ids),
    }


def _resolve_config(category: str | None) -> tuple[str, list[str], dict[str, Any]]:
    status = telegram_config_status(category)
    token = os.getenv(status["token_key"], "")
    chat_ids = _csv_env(status["chat_key"])
    if not token:
        raise TelegramDeliveryError(f"Missing {status['token_key']} in environment")
    if not chat_ids:
        raise TelegramDeliveryError(f"Missing {status['chat_key']} in environment")
    return token, chat_ids, status


def send_telegram_messages(category, message, file_path=None):
    """Send text message or file with caption via Telegram.

    Bot tokens and chat IDs are loaded from environment variables only.
    """

    bot_token, chat_ids, status = _resolve_config(category)
    message_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    document_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    results = []

    for chat_id in chat_ids:
        try:
            if file_path and Path(file_path).is_file():
                with open(file_path, "rb") as file:
                    response = requests.post(
                        document_url,
                        data={"chat_id": chat_id, "caption": message},
                        files={"document": file},
                        timeout=15,
                    )
            else:
                response = requests.post(
                    message_url,
                    data={"chat_id": chat_id, "text": message},
                    timeout=15,
                )
        except requests.RequestException as exc:
            raise TelegramDeliveryError(f"Telegram network error for chat {chat_id}: {exc}") from exc

        if response.status_code != 200:
            raise TelegramDeliveryError(
                f"Telegram API {response.status_code} for chat {chat_id}: {response.text[:300]}"
            )

        try:
            payload = response.json()
        except ValueError:
            payload = {"ok": True}
        results.append({"chat_id": chat_id, "response": payload})

    return {
        "status": "ok",
        "category": status["category"],
        "sent": len(results),
        "results": results,
    }

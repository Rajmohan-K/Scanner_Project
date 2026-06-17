from __future__ import annotations

import hashlib
import pickle
import time
from pathlib import Path
from typing import Any

from config import SCANNER_CACHE_DIR


def _namespace_dir(namespace: str) -> Path:
    cache_dir = Path(SCANNER_CACHE_DIR) / namespace
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _cache_path(namespace: str, key: str) -> Path:
    safe_key = hashlib.md5(key.encode("utf-8")).hexdigest()
    return _namespace_dir(namespace) / f"{safe_key}.pkl"


def load_cache(namespace: str, key: str, ttl_seconds: int) -> Any | None:
    path = _cache_path(namespace, key)
    if not path.exists():
        return None

    try:
        with path.open("rb") as handle:
            payload = pickle.load(handle)
        fetched_at = payload.get("fetched_at", 0)
        if ttl_seconds >= 0 and (time.time() - fetched_at) > ttl_seconds:
            return None
        return payload.get("data")
    except Exception:
        return None


def save_cache(namespace: str, key: str, data: Any) -> None:
    path = _cache_path(namespace, key)
    payload = {
        "fetched_at": time.time(),
        "data": data,
    }
    with path.open("wb") as handle:
        pickle.dump(payload, handle)

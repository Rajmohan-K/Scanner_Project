import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
LOG_FOLDER = os.getenv(
    "LOG_FOLDER",
    str(BASE_DIR / "logs"),
)
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "").strip()
SCANNER_CACHE_DIR = os.getenv(
    "SCANNER_CACHE_DIR",
    str(BASE_DIR / ".scanner_cache"),
)
MARKET_DATA_CACHE_TTL = int(os.getenv("MARKET_DATA_CACHE_TTL", "14400"))
QUOTE_CACHE_TTL = int(os.getenv("QUOTE_CACHE_TTL", "300"))
OPTIONS_CACHE_TTL = int(os.getenv("OPTIONS_CACHE_TTL", "900"))
FUNDAMENTAL_CACHE_TTL = int(os.getenv("FUNDAMENTAL_CACHE_TTL", "21600"))
UNIVERSE_CACHE_TTL = int(os.getenv("UNIVERSE_CACHE_TTL", "43200"))
EVENT_DATA_CACHE_TTL = int(os.getenv("EVENT_DATA_CACHE_TTL", "1800"))
FEED_REQUEST_TIMEOUT = int(os.getenv("FEED_REQUEST_TIMEOUT", "5"))
FII_DII_FEED_URL = os.getenv("FII_DII_FEED_URL", "").strip()


# =========================
# V30 universal variables
# =========================
# Tune these values from this one file instead of editing scanner/app code.
V30_QUOTE_CACHE_SECONDS = int(os.getenv("V30_QUOTE_CACHE_SECONDS", "1"))
V30_CANDLE_CACHE_SECONDS = int(os.getenv("V30_CANDLE_CACHE_SECONDS", "30"))
V30_INTRADAY_ANALYSIS_CACHE_SECONDS = int(os.getenv("V30_INTRADAY_ANALYSIS_CACHE_SECONDS", "90"))
V30_OPPORTUNITY_REFRESH_SECONDS = int(os.getenv("V30_OPPORTUNITY_REFRESH_SECONDS", "5"))
V30_STREAM_INTERVAL_SECONDS = float(os.getenv("V30_STREAM_INTERVAL_SECONDS", "1"))
V30_STREAM_MAX_EVENTS = int(os.getenv("V30_STREAM_MAX_EVENTS", "0"))  # 0 means keep open

V30_INTRADAY_INTERVAL = os.getenv("V30_INTRADAY_INTERVAL", "5m")
V30_INTRADAY_PERIOD = os.getenv("V30_INTRADAY_PERIOD", "5d")
V30_INTRADAY_MIN_BUY_SCORE = float(os.getenv("V30_INTRADAY_MIN_BUY_SCORE", "68"))
V30_INTRADAY_MIN_WATCH_SCORE = float(os.getenv("V30_INTRADAY_MIN_WATCH_SCORE", "50"))
V30_INTRADAY_ATR_STOP_MULTIPLIER = float(os.getenv("V30_INTRADAY_ATR_STOP_MULTIPLIER", "1.2"))
V30_INTRADAY_TARGET_1R = float(os.getenv("V30_INTRADAY_TARGET_1R", "1"))
V30_INTRADAY_TARGET_2R = float(os.getenv("V30_INTRADAY_TARGET_2R", "2"))
V30_INTRADAY_TARGET_3R = float(os.getenv("V30_INTRADAY_TARGET_3R", "3"))

V30_OPPORTUNITY_LIMIT = int(os.getenv("V30_OPPORTUNITY_LIMIT", "50"))
V30_STALE_AFTER_SECONDS = int(os.getenv("V30_STALE_AFTER_SECONDS", "90"))

V30_SCANNER_CONTRACTS = {
    "premarket": ("symbol", "previous_close", "premarket_price", "gap_percent", "relative_volume", "news_score", "premarket_score"),
    "open_confirmation": ("symbol", "open_price", "price_at_0908", "vwap_status", "confirmation_score", "decision"),
    "intraday": ("symbol", "ltp", "vwap", "volume", "intraday_score", "entry", "stop_loss", "target1", "risk_reward", "grade"),
    "swing": ("symbol", "setup_type", "holding_period", "daily_trend", "fundamental_score", "swing_score", "entry", "stop_loss", "target1"),
    "groww": ("symbol", "source", "resolved_symbol", "selected_scan_type", "retail_rank", "score"),
    "meta": ("symbol", "scan_types_matched", "meta_score", "ai_confidence", "ml_confidence", "risk_score", "final_decision"),
    "final_decision": ("symbol", "should_show", "should_trade", "should_watch", "should_reject", "final_decision", "trade_plan"),
}

V30_CONFIG = {
    "quote_cache_seconds": V30_QUOTE_CACHE_SECONDS,
    "candle_cache_seconds": V30_CANDLE_CACHE_SECONDS,
    "intraday_analysis_cache_seconds": V30_INTRADAY_ANALYSIS_CACHE_SECONDS,
    "opportunity_refresh_seconds": V30_OPPORTUNITY_REFRESH_SECONDS,
    "stream_interval_seconds": V30_STREAM_INTERVAL_SECONDS,
    "stream_max_events": V30_STREAM_MAX_EVENTS,
    "intraday": {
        "interval": V30_INTRADAY_INTERVAL,
        "period": V30_INTRADAY_PERIOD,
        "min_buy_score": V30_INTRADAY_MIN_BUY_SCORE,
        "min_watch_score": V30_INTRADAY_MIN_WATCH_SCORE,
        "atr_stop_multiplier": V30_INTRADAY_ATR_STOP_MULTIPLIER,
        "target_1r": V30_INTRADAY_TARGET_1R,
        "target_2r": V30_INTRADAY_TARGET_2R,
        "target_3r": V30_INTRADAY_TARGET_3R,
    },
    "opportunity_limit": V30_OPPORTUNITY_LIMIT,
    "stale_after_seconds": V30_STALE_AFTER_SECONDS,
    "scanner_contracts": V30_SCANNER_CONTRACTS,
}


# =========================
# Master analysis variables
# =========================
# These drive the professional stock-detail intelligence engine. Override any
# value with environment variables instead of editing analysis code.
MASTER_SCORE_WEIGHTS = {
    "trend": float(os.getenv("MASTER_WEIGHT_TREND", "20")),
    "momentum": float(os.getenv("MASTER_WEIGHT_MOMENTUM", "15")),
    "volume": float(os.getenv("MASTER_WEIGHT_VOLUME", "15")),
    "breakout": float(os.getenv("MASTER_WEIGHT_BREAKOUT", "20")),
    "relative_strength": float(os.getenv("MASTER_WEIGHT_RELATIVE_STRENGTH", "10")),
    "market_alignment": float(os.getenv("MASTER_WEIGHT_MARKET_ALIGNMENT", "10")),
    "risk_reward": float(os.getenv("MASTER_WEIGHT_RISK_REWARD", "10")),
}

MASTER_ANALYSIS_SETTINGS = {
    "rsi_buy_min": float(os.getenv("MASTER_RSI_BUY_MIN", "50")),
    "rsi_buy_max": float(os.getenv("MASTER_RSI_BUY_MAX", "70")),
    "rsi_overheated": float(os.getenv("MASTER_RSI_OVERHEATED", "72")),
    "volume_spike_threshold": float(os.getenv("MASTER_VOLUME_SPIKE_THRESHOLD", "1.5")),
    "breakout_near_pct": float(os.getenv("MASTER_BREAKOUT_NEAR_PCT", "2")),
    "min_risk_reward": float(os.getenv("MASTER_MIN_RISK_REWARD", "1.5")),
    "atr_intraday_multiplier": float(os.getenv("MASTER_ATR_INTRADAY_MULTIPLIER", "0.65")),
    "atr_swing_multiplier": float(os.getenv("MASTER_ATR_SWING_MULTIPLIER", "1.15")),
    "refresh_seconds": int(os.getenv("MASTER_ANALYSIS_REFRESH_SECONDS", "10")),
    "timeframes": tuple(
        item.strip()
        for item in os.getenv("MASTER_ANALYSIS_TIMEFRAMES", "15m,30m,1h,4h,1D,1W").split(",")
        if item.strip()
    ),
    "weights": MASTER_SCORE_WEIGHTS,
}

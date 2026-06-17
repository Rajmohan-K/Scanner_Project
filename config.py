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

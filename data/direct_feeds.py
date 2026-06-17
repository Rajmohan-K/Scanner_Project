from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote_plus
import json
import re
import xml.etree.ElementTree as ET

import requests

from config import EVENT_DATA_CACHE_TTL, FEED_REQUEST_TIMEOUT, FII_DII_FEED_URL
from data.cache_utils import load_cache, save_cache
from utils.logger import logger


NSE_HOME_URL = "https://www.nseindia.com"
NSE_CORPORATE_URL = "https://www.nseindia.com/api/corporate-announcements?index=equities"
NSE_QUOTE_EQUITY_URL = "https://www.nseindia.com/api/quote-equity?symbol={symbol}&section=trade_info"
NSE_BULK_DEAL_URLS = [
    "https://www.nseindia.com/api/block-deal?symbol={symbol}",
]
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
OPTIONAL_HTTP_STATUSES = {403, 404, 429, 500, 502, 503, 504}
UNAVAILABLE_CACHE_MARKER = "__feed_unavailable__"

MONTH_MAP = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/html,application/xml,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": NSE_HOME_URL,
        }
    )
    return session


def _get_json(url: str, cache_key: str, warm_nse: bool = False) -> Any:
    cached = load_cache("events", cache_key, EVENT_DATA_CACHE_TTL)
    if isinstance(cached, dict) and cached.get(UNAVAILABLE_CACHE_MARKER):
        return None
    if cached is not None:
        return cached

    try:
        session = _session()
        if warm_nse:
            session.get(NSE_HOME_URL, timeout=FEED_REQUEST_TIMEOUT)
        response = session.get(url, timeout=FEED_REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        save_cache("events", cache_key, payload)
        return payload
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 0
        if status_code in OPTIONAL_HTTP_STATUSES:
            logger.debug(f"Optional direct JSON feed unavailable for {url}: HTTP {status_code}")
            save_cache(
                "events",
                cache_key,
                {
                    UNAVAILABLE_CACHE_MARKER: True,
                    "status_code": status_code,
                    "url": url,
                },
            )
            return None
        logger.error(f"Direct JSON feed failed for {url}: {exc}")
        return None
    except requests.RequestException as exc:
        logger.debug(f"Optional direct JSON feed request failed for {url}: {exc}")
        save_cache(
            "events",
            cache_key,
            {
                UNAVAILABLE_CACHE_MARKER: True,
                "status_code": 0,
                "url": url,
            },
        )
        return None
    except Exception as exc:
        logger.error(f"Direct JSON feed failed for {url}: {exc}")
        return None


def _get_text(url: str, cache_key: str) -> str:
    cached = load_cache("events", cache_key, EVENT_DATA_CACHE_TTL)
    if isinstance(cached, str) and cached:
        return cached

    try:
        response = _session().get(url, timeout=FEED_REQUEST_TIMEOUT)
        response.raise_for_status()
        text = response.text
        save_cache("events", cache_key, text)
        return text
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 0
        if status_code in OPTIONAL_HTTP_STATUSES:
            logger.debug(f"Optional direct text feed unavailable for {url}: HTTP {status_code}")
            return ""
        logger.error(f"Direct text feed failed for {url}: {exc}")
        return ""
    except requests.RequestException as exc:
        logger.debug(f"Optional direct text feed request failed for {url}: {exc}")
        return ""
    except Exception as exc:
        logger.error(f"Direct text feed failed for {url}: {exc}")
        return ""


def _extract_symbol_root(symbol: str) -> str:
    return (symbol or "").split(".")[0].upper()


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").replace("&nbsp;", " ").strip()


def _parse_pub_date(value: str) -> str:
    if not value:
        return ""

    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _days_until(date_str: str) -> int | None:
    if not date_str:
        return None

    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
        return (target - datetime.utcnow().date()).days
    except Exception:
        return None


def _extract_numeric_amounts(text: str) -> list[float]:
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*(?:crore|cr|mn|million|bn|billion)?", text.lower())
    values: list[float] = []
    for raw in matches:
        try:
            values.append(float(raw))
        except Exception:
            continue
    return values


def _extract_date(text: str) -> str:
    text_lower = (text or "").lower()
    month_pattern = "|".join(MONTH_MAP.keys())
    patterns = [
        rf"(\d{{1,2}})[\s/-]({month_pattern})[\s,-]+(\d{{4}})",
        rf"({month_pattern})[\s/-](\d{{1,2}})[\s,-]+(\d{{4}})",
        r"(\d{4})-(\d{2})-(\d{2})",
    ]

    for index, pattern in enumerate(patterns):
        match = re.search(pattern, text_lower)
        if not match:
            continue
        try:
            if index == 0:
                day = int(match.group(1))
                month = MONTH_MAP[match.group(2)[:3]]
                year = int(match.group(3))
            elif index == 1:
                month = MONTH_MAP[match.group(1)[:3]]
                day = int(match.group(2))
                year = int(match.group(3))
            else:
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3))
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except Exception:
            continue

    return ""


def _parse_google_rss(query: str, limit: int = 10) -> list[dict[str, Any]]:
    url = GOOGLE_NEWS_RSS.format(query=quote_plus(query))
    xml_text = _get_text(url, f"rss|{query}|{limit}")
    if not xml_text:
        return []

    try:
        root = ET.fromstring(xml_text)
        articles: list[dict[str, Any]] = []
        for item in root.findall(".//item")[:limit]:
            title = (item.findtext("title") or "").strip()
            description = _strip_html(item.findtext("description") or "")
            pub_date = _parse_pub_date(item.findtext("pubDate") or "")
            link = (item.findtext("link") or "").strip()
            if not title:
                continue
            articles.append(
                {
                    "title": title,
                    "description": description,
                    "published_at": pub_date,
                    "source": "google_rss",
                    "url": link,
                }
            )
        return articles
    except Exception as exc:
        logger.error(f"RSS parse failed for query {query}: {exc}")
        return []


def _filter_symbol_articles(symbol: str, articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    root = _extract_symbol_root(symbol)
    return [
        article for article in articles
        if root in json.dumps(article).upper()
    ]


def fetch_corporate_announcements(symbol: str, limit: int = 15) -> list[dict[str, Any]]:
    payload = _get_json(NSE_CORPORATE_URL, "nse|corporate_announcements", warm_nse=True)
    if not isinstance(payload, list):
        return []

    root_symbol = _extract_symbol_root(symbol)
    events: list[dict[str, Any]] = []
    for item in payload:
        raw_text = " ".join(
            str(item.get(key, "") or "")
            for key in ["symbol", "subject", "desc", "attchmntText", "broadcastDateTime"]
        )
        if root_symbol and root_symbol not in raw_text.upper():
            continue

        subject = str(item.get("subject", "") or item.get("desc", "") or "").strip()
        event_date = _extract_date(raw_text)
        event_type = "general"
        lowered = raw_text.lower()
        if "result" in lowered or "earnings" in lowered or "board meeting" in lowered:
            event_type = "earnings"
        elif "dividend" in lowered:
            event_type = "dividend"
        elif "split" in lowered or "bonus" in lowered:
            event_type = "capital_action"

        events.append(
            {
                "symbol": root_symbol,
                "event_type": event_type,
                "title": subject or "Corporate announcement",
                "date": event_date,
                "source": "nse_corporate",
                "text": raw_text.strip(),
            }
        )

    return events[:limit]


def fetch_bulk_block_deals(symbol: str, limit: int = 10) -> list[dict[str, Any]]:
    symbol_root = _extract_symbol_root(symbol)
    events: list[dict[str, Any]] = []

    for template in NSE_BULK_DEAL_URLS:
        url = template.format(symbol=quote_plus(symbol_root))
        payload = _get_json(url, f"nse|deal|{template}|{symbol_root}", warm_nse=True)
        rows = []
        if isinstance(payload, dict):
            for key in ["data", "deals", "value"]:
                if isinstance(payload.get(key), list):
                    rows = payload[key]
                    break
        elif isinstance(payload, list):
            rows = payload

        for row in rows:
            text = json.dumps(row, default=str)
            if symbol_root and symbol_root not in text.upper():
                continue
            side_text = text.lower()
            side = "buy" if "buy" in side_text else "sell" if "sell" in side_text else "unknown"
            amounts = _extract_numeric_amounts(text)
            value = max(amounts) if amounts else 0.0
            events.append(
                {
                    "symbol": symbol_root,
                    "side": side,
                    "value": value,
                    "source": "nse_deal",
                    "text": text,
                }
            )
        if events:
            break

    if events:
        return events[:limit]

    rss_articles = _filter_symbol_articles(
        symbol,
        _parse_google_rss(f"{symbol_root} block deal OR bulk deal", limit=limit),
    )
    for article in rss_articles:
        text = f"{article.get('title', '')} {article.get('description', '')}"
        side_text = text.lower()
        side = "buy" if "buy" in side_text else "sell" if "sell" in side_text else "unknown"
        amounts = _extract_numeric_amounts(text)
        value = max(amounts) if amounts else 0.0
        events.append(
            {
                "symbol": symbol_root,
                "side": side,
                "value": value,
                "source": article.get("source", "rss"),
                "text": text.strip(),
            }
        )
    return events[:limit]


def fetch_delivery_data(symbol: str) -> dict[str, Any]:
    symbol_root = _extract_symbol_root(symbol)
    payload = _get_json(
        NSE_QUOTE_EQUITY_URL.format(symbol=quote_plus(symbol_root)),
        f"nse|delivery|{symbol_root}",
        warm_nse=True,
    )
    if not isinstance(payload, dict):
        return {"source": "unavailable", "data_quality": "missing"}

    security = payload.get("securityWiseDP") or {}
    trade_info = payload.get("marketDeptOrderBook", {}).get("tradeInfo", {}) or {}

    def as_float(value: Any) -> float:
        try:
            return float(str(value).replace(",", ""))
        except Exception:
            return 0.0

    delivery_percent = as_float(
        security.get("deliveryToTradedQuantity")
        or security.get("deliveryToTradedQuantityPercent")
    )
    current_delivery_qty = as_float(security.get("deliveryQuantity"))
    total_volume = as_float(trade_info.get("totalTradedVolume"))

    if delivery_percent <= 0 and current_delivery_qty and total_volume:
        delivery_percent = (current_delivery_qty / total_volume) * 100

    if delivery_percent <= 0 and current_delivery_qty <= 0:
        return {"source": "nse_quote_equity", "data_quality": "missing"}

    return {
        "current_delivery_qty": current_delivery_qty,
        "delivery_percent": round(delivery_percent, 2),
        "total_traded_volume": total_volume,
        "source": "nse_quote_equity",
        "data_quality": "real",
    }


def fetch_insider_activity(symbol: str, limit: int = 10) -> dict[str, Any]:
    root = _extract_symbol_root(symbol)
    articles = _filter_symbol_articles(
        symbol,
        _parse_google_rss(f"{root} promoter holding insider buying selling pledge", limit=limit),
    )
    buy_value = 0.0
    sell_value = 0.0
    promoter_change = 0.0
    transactions = 0

    for article in articles:
        text = f"{article.get('title', '')} {article.get('description', '')}"
        lower = text.lower()
        amounts = _extract_numeric_amounts(text)
        value = max(amounts) if amounts else 0.0
        if any(word in lower for word in ["buy", "bought", "acquire", "increase"]):
            buy_value += value or 1
            promoter_change += 0.1
            transactions += 1
        if any(word in lower for word in ["sell", "sold", "dispose", "pledge", "reduce"]):
            sell_value += value or 1
            promoter_change -= 0.1
            transactions += 1

    if transactions == 0:
        return {"source": "rss_extracted", "data_quality": "missing"}

    return {
        "buy_value": round(buy_value, 2),
        "sell_value": round(sell_value, 2),
        "net_transactions": transactions,
        "promoter_change_percent": round(promoter_change, 2),
        "source": "rss_extracted",
        "data_quality": "partial",
    }


def fetch_fii_dii_flow() -> dict[str, Any]:
    if FII_DII_FEED_URL:
        payload = _get_json(FII_DII_FEED_URL, "fii_dii|configured", warm_nse=False)
        if isinstance(payload, dict):
            fii = float(payload.get("fii", 0) or 0)
            dii = float(payload.get("dii", 0) or 0)
            return {
                "fii": fii,
                "dii": dii,
                "source": "configured_feed",
                "confidence": 1.0,
            }

    articles = _parse_google_rss("FII DII cash market data India", limit=8)
    fii = 0.0
    dii = 0.0
    confidence_hits = 0

    for article in articles:
        text = f"{article.get('title', '')} {article.get('description', '')}"
        lower = text.lower()
        numbers = _extract_numeric_amounts(text)
        if len(numbers) < 2:
            continue
        if "fii" in lower or "foreign institutional" in lower:
            fii = numbers[0] if "buy" in lower or "inflow" in lower else -numbers[0]
            confidence_hits += 1
        if "dii" in lower or "domestic institutional" in lower:
            dii = numbers[1] if "buy" in lower or "inflow" in lower else -numbers[1]
            confidence_hits += 1
        if confidence_hits >= 2:
            break

    return {
        "fii": fii,
        "dii": dii,
        "source": "rss_extracted" if confidence_hits else "unavailable",
        "confidence": min(confidence_hits / 2, 1.0),
    }


def fetch_geopolitical_news(limit: int = 12) -> list[dict[str, Any]]:
    queries = [
        "war oil sanctions shipping market",
        "middle east conflict crude oil market",
        "china taiwan sanctions market impact",
    ]
    articles: list[dict[str, Any]] = []
    for query in queries:
        articles.extend(_parse_google_rss(query, limit=max(3, limit // len(queries))))

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for article in articles:
        title = article.get("title", "")
        if title in seen:
            continue
        seen.add(title)
        deduped.append(article)
    return deduped[:limit]


def fetch_market_news_feed(limit: int = 12) -> list[dict[str, Any]]:
    queries = [
        "India stock market premarket",
        "NSE BSE market outlook",
        "global markets asia us stocks",
    ]
    articles: list[dict[str, Any]] = []
    for query in queries:
        articles.extend(_parse_google_rss(query, limit=max(3, limit // len(queries))))

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for article in articles:
        key = article.get("title", "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(article)
    return deduped[:limit]


def fetch_stock_news_feed(symbol: str, limit: int = 10) -> list[dict[str, Any]]:
    symbol_root = _extract_symbol_root(symbol)
    queries = [
        f"{symbol_root} stock news",
        f"{symbol_root} earnings results",
    ]
    articles: list[dict[str, Any]] = []
    for query in queries:
        articles.extend(_parse_google_rss(query, limit=max(3, limit // len(queries))))
    return _filter_symbol_articles(symbol, articles)[:limit]


def build_geopolitical_snapshot(articles: list[dict[str, Any]]) -> dict[str, Any]:
    severity = 0
    oil_risk = 0
    regional_risk = 0
    hot_keywords = {
        "war": 3,
        "missile": 3,
        "attack": 3,
        "sanction": 2,
        "tariff": 2,
        "oil": 2,
        "crude": 2,
        "shipping": 2,
        "strait": 2,
        "escalation": 3,
    }

    for article in articles:
        text = f"{article.get('title', '')} {article.get('description', '')}".lower()
        article_score = sum(weight for keyword, weight in hot_keywords.items() if keyword in text)
        severity += article_score
        if "oil" in text or "crude" in text:
            oil_risk += article_score
        if any(keyword in text for keyword in ["india", "asia", "middle east", "china", "taiwan"]):
            regional_risk += max(article_score, 1)

    severity = min(round(severity / 3, 2), 10)
    oil_risk = min(round(oil_risk / 3, 2), 10)
    regional_risk = min(round(regional_risk / 3, 2), 10)
    return {
        "conflict_level": severity,
        "oil_risk": oil_risk,
        "regional_risk": regional_risk,
        "escalation": severity >= 6,
        "headline_count": len(articles),
    }


def build_event_snapshot(symbol: str) -> dict[str, Any]:
    """Build event snapshot from cached direct feeds with graceful fallback."""
    symbol_root = _extract_symbol_root(symbol)
    cache_key = f"snapshot|{symbol_root}"
    cached = load_cache("events", cache_key, EVENT_DATA_CACHE_TTL)
    if isinstance(cached, dict) and cached:
        return cached.copy()

    earnings_events = fetch_corporate_announcements(symbol_root)
    next_earnings = next(
        (event for event in earnings_events if event.get("event_type") == "earnings" and event.get("date")),
        {},
    )
    stock_news = fetch_stock_news_feed(symbol_root, limit=8)
    market_news = fetch_market_news_feed(limit=8)
    geo_news = fetch_geopolitical_news(limit=8)
    snapshot = {
        "symbol": symbol_root,
        "earnings_events": earnings_events,
        "next_earnings_date": next_earnings.get("date", ""),
        "days_to_earnings": _days_until(next_earnings.get("date", "")),
        "block_deals": fetch_bulk_block_deals(symbol_root),
        "delivery_data": fetch_delivery_data(symbol_root),
        "insider_activity": fetch_insider_activity(symbol_root),
        "fii_dii_flow": fetch_fii_dii_flow(),
        "geopolitical_news": geo_news,
        "geopolitical_snapshot": build_geopolitical_snapshot(geo_news),
        "market_news": market_news,
        "stock_news": stock_news,
        "source": "direct_feeds",
    }
    save_cache("events", cache_key, snapshot)
    return {
        **snapshot,
    }

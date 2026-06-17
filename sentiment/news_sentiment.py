from textblob import TextBlob

from utils.logger import logger


POSITIVE_KEYWORDS = {
    "beat": 0.20,
    "surge": 0.18,
    "upgrade": 0.15,
    "wins": 0.15,
    "order": 0.12,
    "contract": 0.12,
    "buy": 0.10,
    "stake": 0.08,
    "inflow": 0.10,
    "growth": 0.10,
}

NEGATIVE_KEYWORDS = {
    "miss": -0.20,
    "downgrade": -0.18,
    "fraud": -0.25,
    "probe": -0.18,
    "war": -0.18,
    "attack": -0.20,
    "sell": -0.10,
    "outflow": -0.10,
    "slump": -0.16,
    "cuts": -0.12,
    "sanctions": -0.18,
}


def _article_text(item):
    if isinstance(item, dict):
        title = str(item.get("title", "") or "")
        description = str(item.get("description", "") or "")
        return f"{title}. {description}".strip()
    return str(item or "").strip()


def analyze_news_sentiment(news_list):
    """
    Analyze sentiment from stock or market news articles.
    Supports plain headline strings and structured article dictionaries.
    """

    try:

        if not news_list:

            return {
                "score": 0,
                "sentiment": "Neutral",
                "reason": "No News"
            }

        total_polarity = 0
        keyword_bias = 0
        observed = 0

        for news in news_list:

            text = _article_text(news)

            if not text:
                continue

            polarity = TextBlob(
                text
            ).sentiment.polarity

            total_polarity += polarity
            observed += 1

            lowered = text.lower()
            keyword_bias += sum(weight for keyword, weight in POSITIVE_KEYWORDS.items() if keyword in lowered)
            keyword_bias += sum(weight for keyword, weight in NEGATIVE_KEYWORDS.items() if keyword in lowered)

        if observed == 0:
            return {
                "score": 0,
                "sentiment": "Neutral",
                "reason": "No readable articles"
            }

        avg_polarity = (
            total_polarity /
            observed
        )

        score = (
            avg_polarity +
            (keyword_bias / observed)
        ) * 100

        if score >= 25:

            sentiment = "Very Bullish"

        elif score >= 10:

            sentiment = "Bullish"

        elif score <= -25:

            sentiment = "Very Bearish"

        elif score <= -10:

            sentiment = "Bearish"

        else:

            sentiment = "Neutral"

        return {
            "score": round(score, 2),
            "sentiment": sentiment,
            "reason": f"News sample size {observed}"
        }

    except Exception as e:

        logger.error(
            f"News sentiment failed: {e}"
        )

        return {
            "score": 0,
            "sentiment": "Unknown"
        }

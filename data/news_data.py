from config import NEWS_API_KEY
from data.direct_feeds import fetch_market_news_feed, fetch_stock_news_feed
from utils.logger import logger

try:
    from newsapi import NewsApiClient
except Exception:  # pragma: no cover
    NewsApiClient = None


def _get_client():
    if not NEWS_API_KEY:
        return None

    if NewsApiClient is None:
        logger.warning("newsapi package not available")
        return None

    try:
        return NewsApiClient(api_key=NEWS_API_KEY)
    except Exception as exc:
        logger.error(f"News client init failed: {exc}")
        return None


def get_stock_news(
    query,
    limit=10
):
    """
    Fetch stock/company related news articles.
    """

    try:
        client = _get_client()

        if client is None:
            return fetch_stock_news_feed(query, limit=limit)

        articles = client.get_everything(
            q=query,
            language="en",
            sort_by="publishedAt",
            page_size=limit
        )

        articles_out = []

        for article in articles.get(
            "articles",
            []
        ):

            title = article.get(
                "title"
            )

            if title:

                articles_out.append(
                    {
                        "title": title,
                        "description": article.get("description", "") or "",
                        "published_at": article.get("publishedAt", "") or "",
                        "source": "newsapi",
                        "url": article.get("url", "") or "",
                    }
                )

        return articles_out[:limit] if articles_out else fetch_stock_news_feed(query, limit=limit)

    except Exception as e:

        logger.error(
            f"Stock news fetch failed: {e}"
        )

        return fetch_stock_news_feed(query, limit=limit)


def get_market_news(
    limit=10
):
    """
    Fetch broader market/economy news.
    """

    try:
        client = _get_client()

        if client is None:
            return fetch_market_news_feed(limit=limit)

        articles = client.get_top_headlines(
            category="business",
            language="en",
            page_size=limit
        )

        articles_out = []

        for article in articles.get(
            "articles",
            []
        ):

            title = article.get(
                "title"
            )

            if title:

                articles_out.append(
                    {
                        "title": title,
                        "description": article.get("description", "") or "",
                        "published_at": article.get("publishedAt", "") or "",
                        "source": "newsapi",
                        "url": article.get("url", "") or "",
                    }
                )

        return articles_out[:limit] if articles_out else fetch_market_news_feed(limit=limit)

    except Exception as e:

        logger.error(
            f"Market news fetch failed: {e}"
        )

        return fetch_market_news_feed(limit=limit)

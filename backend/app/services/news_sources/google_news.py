"""Google News source integration."""

import asyncio
import feedparser
from urllib.parse import quote


GOOGLE_NEWS_URL = "https://news.google.com/rss/search"


async def fetch_google_news(
    query: str = "artificial intelligence",
    max_records: int = 30
):
    params = (
        f"?q={quote(query)}"
        f"&hl=en-US"
        f"&gl=US"
        f"&ceid=US:en"
    )

    feed = await asyncio.to_thread(feedparser.parse, GOOGLE_NEWS_URL + params)

    articles = []

    for entry in feed.entries[:max_records]:
        articles.append({
            "title": entry.get("title"),
            "url": entry.get("link"),
            "original_url": entry.get("link"),
            "source": entry.get("source", {}).get("title"),
            "published_at": entry.get("published"),
            "summary": entry.get("summary"),
            "image_url": None,
            "category": None,
            "source_type": "google_news",
        })

    return articles
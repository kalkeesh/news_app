"""NewsData.io source integration."""
# app/services/news_sources/newsdata.py

import os
import httpx


NEWSDATA_URL = "https://newsdata.io/api/1/latest"


async def fetch_newsdata_news(
    query: str | None = None,
    country: str | None = None,
    language: str = "en",
    max_records: int = 10,
):
    params = {
        "apikey": os.getenv("NEWSDATA_API_KEY"),
        "language": language,
    }

    if query:
        params["q"] = query

    if country:
        params["country"] = country

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            NEWSDATA_URL,
            params=params
        )

        response.raise_for_status()

    data = response.json()

    articles = []

    for article in data.get("results", [])[:max_records]:
        articles.append({
            "title": article.get("title"),
            "url": article.get("link"),
            "source": article.get("source_name"),
            "published_at": article.get("pubDate"),
            "summary": article.get("description"),
            "image_url": article.get("image_url"),
            "category": article.get("category"),
            "source_type": "newsdata",
        })

    return articles
"""The Guardian news source integration."""
# app/services/news_sources/guardian.py

import os
import httpx


GUARDIAN_URL = "https://content.guardianapis.com/search"


async def fetch_guardian_news(
    query: str = "artificial intelligence",
    page_size: int = 20,
):
    params = {
        "api-key": os.getenv("GUARDIAN_API_KEY"),
        "q": query,
        "order-by": "newest",
        "page-size": page_size,
        "show-fields": "thumbnail,trailText",
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            GUARDIAN_URL,
            params=params
        )

        response.raise_for_status()

    data = response.json()

    articles = []

    for article in data["response"].get("results", []):
        fields = article.get("fields", {})

        articles.append({
            "title": article.get("webTitle"),
            "url": article.get("webUrl"),
            "source": "The Guardian",
            "published_at": article.get("webPublicationDate"),
            "summary": fields.get("trailText"),
            "image_url": fields.get("thumbnail"),
            "category": article.get("sectionName"),
            "source_type": "guardian",
        })

    return articles
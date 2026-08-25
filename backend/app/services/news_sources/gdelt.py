"""GDELT news source integration."""

import asyncio
import json
import logging

import httpx


GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
logger = logging.getLogger(__name__)
MAX_RETRIES = 2


async def fetch_gdelt_news(query: str = "technology", max_records: int = 50):
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": max_records,
        "timespan": "1h",
        "sort": "datedesc",
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            for attempt in range(MAX_RETRIES + 1):
                response = await client.get(GDELT_URL, params=params)
                if response.status_code != 429:
                    break
                if attempt < MAX_RETRIES:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = min(float(retry_after), 10.0) if retry_after else 2**attempt
                    except ValueError:
                        delay = 2**attempt
                    await asyncio.sleep(delay)

            response.raise_for_status()
            if "json" not in response.headers.get("content-type", "").lower():
                logger.warning(
                    "GDELT returned non-JSON content (status %s); skipping source",
                    response.status_code,
                )
                return []
            data = response.json()
    except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError) as error:
        logger.warning("GDELT request failed; skipping source: %s", error)
        return []

    articles = []

    for article in data.get("articles", []):
        articles.append({
            "title": article.get("title"),
            "url": article.get("url"),
            "source": article.get("domain"),
            "published_at": article.get("seendate"),
            "summary": None,
            "image_url": None,
            "category": None,
            "source_type": "gdelt",
        })

    return articles
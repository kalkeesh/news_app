"""News collection orchestration."""

import asyncio
import logging
from typing import Any, Awaitable, Callable

from .news_sources.gdelt import fetch_gdelt_news
from .news_sources.google_news import fetch_google_news
from .news_sources.newsdata import fetch_newsdata_news
from .news_sources.guardian import fetch_guardian_news


logger = logging.getLogger(__name__)


async def _fetch_source(
    name: str,
    fetcher: Callable[[], Awaitable[list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    try:
        return await fetcher()
    except Exception:
        logger.exception("Failed to collect news from %s", name)
        return []


async def collect_all_news() -> list[dict[str, Any]]:
    sources = [
        ("gdelt", lambda: fetch_gdelt_news(
            query="technology OR artificial intelligence",
            max_records=30,
        )),
        ("google_news", lambda: fetch_google_news(
            query="artificial intelligence",
            max_records=30,
        )),
        ("newsdata", lambda: fetch_newsdata_news(
            query="artificial intelligence",
            language="en",
            max_records=10,
        )),
        ("guardian", lambda: fetch_guardian_news(
            query="artificial intelligence",
            page_size=20,
        )),
    ]

    results = await asyncio.gather(
        *(_fetch_source(name, fetcher) for name, fetcher in sources)
    )
    return [article for source_articles in results for article in source_articles]
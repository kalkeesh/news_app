"""News collection orchestration."""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from .news_sources.google_news import fetch_google_news
from .news_sources.newsdata import fetch_newsdata_news
from .news_sources.guardian import fetch_guardian_news
from .new_sources import (
    HTTP_TIMEOUT,
    USER_AGENT,
    collect_github,
    collect_google_news_targeted,
    collect_hacker_news,
    collect_huggingface,
    collect_official_ai,
)


logger = logging.getLogger(__name__)


async def _fetch_new_source(
    collector: Callable[[httpx.AsyncClient], Awaitable[list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(
        timeout=HTTP_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
    ) as client:
        return await collector(client)


async def _fetch_source(
    name: str,
    fetcher: Callable[[], Awaitable[list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    try:
        return await fetcher()
    except Exception:
        logger.exception("Failed to collect news from %s", name)
        return []


async def _collect_sources(
    sources: list[tuple[str, Callable[[], Awaitable[list[dict[str, Any]]]]]],
) -> list[dict[str, Any]]:
    results = await asyncio.gather(
        *(_fetch_source(name, fetcher) for name, fetcher in sources)
    )
    return [article for source_articles in results for article in source_articles]


def _service_a_sources() -> list[tuple[str, Callable[[], Awaitable[list[dict[str, Any]]]]]]:
    return [
        ("official_ai", lambda: _fetch_new_source(collect_official_ai)),
        ("hackernews", lambda: _fetch_new_source(collect_hacker_news)),
        ("google_news", lambda: fetch_google_news(query="artificial intelligence", max_records=30)),
        ("newsdata", lambda: fetch_newsdata_news(query="artificial intelligence", language="en", max_records=10)),
        ("guardian", lambda: fetch_guardian_news(query="artificial intelligence", page_size=20)),
    ]


def _service_b_sources() -> list[tuple[str, Callable[[], Awaitable[list[dict[str, Any]]]]]]:
    return [
        ("targeted_google_news", lambda: _fetch_new_source(collect_google_news_targeted)),
        ("huggingface", lambda: _fetch_new_source(collect_huggingface)),
        ("github", lambda: _fetch_new_source(collect_github)),
    ]


async def collect_service_a_news() -> list[dict[str, Any]]:
    return await _collect_sources(_service_a_sources())


async def collect_service_b_news() -> list[dict[str, Any]]:
    return await _collect_sources(_service_b_sources())


async def collect_all_news() -> list[dict[str, Any]]:
    service_results = await asyncio.gather(
        collect_service_a_news(),
        collect_service_b_news(),
    )
    return [article for results in service_results for article in results]

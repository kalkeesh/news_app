"""
Additional AI / Technology signal collectors.

Sources:
1. Official AI company feeds/pages
2. Hacker News
3. Google News targeted RSS
4. Hugging Face
5. GitHub

Each collector returns dictionaries compatible with the existing
raw_article -> normalize_article() pipeline.

No MongoDB operations happen here.
No Gemini/LLM operations happen here.
No deduplication happens here.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

import httpx
import feedparser


logger = logging.getLogger(__name__)

USER_AGENT = "AI-News-Aggregator/1.0"

HTTP_TIMEOUT = httpx.Timeout(
    connect=5.0,
    read=15.0,
    write=10.0,
    pool=10.0,
)


# ============================================================
# COMMON HELPERS
# ============================================================

def utc_from_timestamp(timestamp: Any) -> str | None:
    """Convert Unix timestamp to ISO UTC."""
    if not timestamp:
        return None

    try:
        return datetime.fromtimestamp(
            float(timestamp),
            tz=timezone.utc,
        ).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def clean_text(value: Any, max_length: int = 2000) -> str:
    if value is None:
        return ""

    text = str(value)
    text = re.sub(r"\s+", " ", text).strip()

    return text[:max_length]


def make_article(
    *,
    title: str,
    url: str,
    source: str,
    source_type: str,
    published_at: str | None = None,
    summary: str | None = None,
    image_url: str | None = None,
    category: str | None = None,
    content_type: str = "article",
) -> dict[str, Any]:

    return {
        "title": clean_text(title, 500),
        "url": url,
        "source": source,
        "source_type": source_type,
        "published_at": published_at,
        "summary": clean_text(summary, 2000),
        "image_url": image_url,
        "category": category,
        "content_type": content_type,
    }


async def fetch_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:

    response = await client.get(
        url,
        headers=headers,
        params=params,
    )

    response.raise_for_status()

    return response.json()


async def fetch_text(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str] | None = None,
) -> str:

    response = await client.get(
        url,
        headers=headers,
    )

    response.raise_for_status()

    return response.text


# ============================================================
# 1. OFFICIAL AI COMPANY SOURCES
# ============================================================

"""
Prefer RSS when the company provides an official RSS feed.

Some companies do not provide a stable public RSS endpoint.
For those, keep the URL in this configuration and let Codex
adapt the collector to the current official page/feed.

DO NOT use unofficial RSS mirrors for "official_ai" unless
explicitly configured later.
"""

OFFICIAL_AI_FEEDS = [
    {
        "name": "OpenAI",
        "url": "https://openai.com/news/rss.xml",
        "source_type": "official_ai",
    },

    # Add/adjust official feed URLs if available.
    #
    # {
    #     "name": "Anthropic",
    #     "url": "...",
    #     "source_type": "official_ai",
    # },
    #
    # {
    #     "name": "Google DeepMind",
    #     "url": "...",
    #     "source_type": "official_ai",
    # },
]


async def collect_official_ai(
    client: httpx.AsyncClient,
) -> list[dict[str, Any]]:

    results: list[dict[str, Any]] = []

    for feed in OFFICIAL_AI_FEEDS:
        try:
            xml = await fetch_text(
                client,
                feed["url"],
            )

            parsed = feedparser.parse(xml)

            for entry in parsed.entries:

                title = clean_text(
                    entry.get("title"),
                    500,
                )

                url = (
                    entry.get("link")
                    or entry.get("id")
                )

                if not title or not url:
                    continue

                published_at = None

                if entry.get("published_parsed"):
                    try:
                        published_at = datetime(
                            *entry.published_parsed[:6],
                            tzinfo=timezone.utc,
                        ).isoformat()
                    except Exception:
                        pass

                summary = (
                    entry.get("summary")
                    or entry.get("description")
                    or ""
                )

                results.append(
                    make_article(
                        title=title,
                        url=url,
                        source=feed["name"],
                        source_type="official_ai",
                        published_at=published_at,
                        summary=summary,
                        category="AI",
                        content_type="announcement",
                    )
                )

        except Exception as exc:
            logger.warning(
                "Official AI source failed: %s: %s",
                feed["name"],
                exc,
            )

    return results


# ============================================================
# 2. HACKER NEWS
# ============================================================

HN_BASE = "https://hacker-news.firebaseio.com/v0"

HN_FEEDS = [
    "newstories",
    "showstories",
]

HN_MAX_STORIES_PER_FEED = 100


async def get_hn_item(
    client: httpx.AsyncClient,
    item_id: int,
) -> dict[str, Any] | None:

    try:
        return await fetch_json(
            client,
            f"{HN_BASE}/item/{item_id}.json",
        )
    except Exception as exc:
        logger.debug(
            "Hacker News item %s failed: %s",
            item_id,
            exc,
        )
        return None


async def collect_hacker_news(
    client: httpx.AsyncClient,
) -> list[dict[str, Any]]:

    results: list[dict[str, Any]] = []

    seen_ids: set[int] = set()

    for feed_name in HN_FEEDS:

        try:
            story_ids = await fetch_json(
                client,
                f"{HN_BASE}/{feed_name}.json",
            )

        except Exception as exc:
            logger.warning(
                "Hacker News feed %s failed: %s",
                feed_name,
                exc,
            )
            continue

        if not isinstance(story_ids, list):
            continue

        story_ids = story_ids[:HN_MAX_STORIES_PER_FEED]

        # Avoid requesting the same story twice if it appears
        # in both newstories and showstories.
        story_ids = [
            story_id
            for story_id in story_ids
            if story_id not in seen_ids
        ]

        seen_ids.update(story_ids)

        # Small concurrency limit.
        semaphore = asyncio.Semaphore(10)

        async def get_limited(story_id: int):
            async with semaphore:
                return await get_hn_item(
                    client,
                    story_id,
                )

        items = await asyncio.gather(
            *[
                get_limited(story_id)
                for story_id in story_ids
            ],
            return_exceptions=True,
        )

        for item in items:

            if not isinstance(item, dict):
                continue

            title = clean_text(
                item.get("title"),
                500,
            )

            if not title:
                continue

            url = (
                item.get("url")
                or f"https://news.ycombinator.com/item?id={item.get('id')}"
            )

            published_at = utc_from_timestamp(
                item.get("time")
            )

            item_type = item.get("type")

            content_type = (
                "discussion"
                if item_type == "story" and not item.get("url")
                else "article"
            )

            results.append(
                make_article(
                    title=title,
                    url=url,
                    source="Hacker News",
                    source_type="hackernews",
                    published_at=published_at,
                    summary=clean_text(
                        item.get("text"),
                        2000,
                    ),
                    category=None,
                    content_type=content_type,
                )
            )

    return results


# ============================================================
# 3. TARGETED GOOGLE NEWS RSS
# ============================================================

GOOGLE_NEWS_QUERIES = [
    "artificial intelligence models",
    "generative AI agents",
    "LLM research",
]

GOOGLE_NEWS_MAX_PER_QUERY = 20


def google_news_rss_url(query: str) -> str:

    encoded = quote_plus(query)

    return (
        "https://news.google.com/rss/search"
        f"?q={encoded}"
        "&hl=en-US"
        "&gl=US"
        "&ceid=US:en"
    )


async def collect_google_news_targeted(
    client: httpx.AsyncClient,
) -> list[dict[str, Any]]:

    results: list[dict[str, Any]] = []

    semaphore = asyncio.Semaphore(5)

    async def fetch_query(query: str):

        async with semaphore:

            try:
                xml = await fetch_text(
                    client,
                    google_news_rss_url(query),
                )

                parsed = feedparser.parse(xml)

                query_results = []

                for entry in parsed.entries[
                    :GOOGLE_NEWS_MAX_PER_QUERY
                ]:

                    title = clean_text(
                        entry.get("title"),
                        500,
                    )

                    url = entry.get("link")

                    if not title or not url:
                        continue

                    source_name = "Google News"

                    if entry.get("source"):
                        source_name = clean_text(
                            entry.source.get("title")
                            or "Google News",
                            200,
                        )

                    published_at = None

                    if entry.get("published_parsed"):
                        try:
                            published_at = datetime(
                                *entry.published_parsed[:6],
                                tzinfo=timezone.utc,
                            ).isoformat()
                        except Exception:
                            pass

                    query_results.append(
                        make_article(
                            title=title,
                            url=url,
                            source=source_name,
                            source_type="targeted_google_news",
                            published_at=published_at,
                            summary=entry.get("summary", ""),
                            category=None,
                            content_type="article",
                        )
                    )

                return query_results

            except Exception as exc:
                logger.warning(
                    "Google News query failed: %s: %s",
                    query,
                    exc,
                )

                return []

    batches = await asyncio.gather(
        *[
            fetch_query(query)
            for query in GOOGLE_NEWS_QUERIES
        ]
    )

    for batch in batches:
        results.extend(batch)

    return results


# ============================================================
# 4. HUGGING FACE
# ============================================================

HF_API_BASE = "https://huggingface.co/api"

HF_MAX_MODELS = 25


async def collect_huggingface(
    client: httpx.AsyncClient,
) -> list[dict[str, Any]]:

    results: list[dict[str, Any]] = []

    # Public Hub metadata.
    # No inference is performed here.
    url = f"{HF_API_BASE}/models"

    params = {
        "sort": "lastModified",
        "direction": "-1",
        "limit": HF_MAX_MODELS,
    }

    try:

        models = await fetch_json(
            client,
            url,
            params=params,
        )

        if not isinstance(models, list):
            return results

        for model in models:

            if not isinstance(model, dict):
                continue

            model_id = model.get("id")

            if not model_id:
                continue

            title = f"New/updated Hugging Face model: {model_id}"

            model_url = (
                f"https://huggingface.co/{model_id}"
            )

            last_modified = model.get(
                "lastModified"
            )

            results.append(
                make_article(
                    title=title,
                    url=model_url,
                    source="Hugging Face",
                    source_type="huggingface",
                    published_at=last_modified,
                    summary=(
                        f"Hugging Face model "
                        f"{model_id} was recently "
                        f"updated or surfaced."
                    ),
                    category="AI",
                    content_type="model_release",
                )
            )

    except Exception as exc:

        logger.warning(
            "Hugging Face collector failed: %s",
            exc,
        )

    return results


# ============================================================
# 5. GITHUB
# ============================================================

GITHUB_API = "https://api.github.com"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

GITHUB_SEARCH_QUERIES = ["AI OR LLM OR \"generative AI\" in:name,description"]

GITHUB_MAX_RESULTS_PER_QUERY = 20


def github_headers() -> dict[str, str]:

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": USER_AGENT,
    }

    if GITHUB_TOKEN:
        headers["Authorization"] = (
            f"Bearer {GITHUB_TOKEN}"
        )

    return headers


async def collect_github(
    client: httpx.AsyncClient,
) -> list[dict[str, Any]]:

    results: list[dict[str, Any]] = []

    # Important:
    # GitHub has much higher API limits when authenticated.
    # If GITHUB_TOKEN is absent, this still works but should
    # be called conservatively.

    headers = github_headers()

    semaphore = asyncio.Semaphore(3)

    async def search_query(query: str):

        async with semaphore:

            try:

                params = {
                    "q": (
                        f"{query} "
                        "pushed:>=2026-08-20"
                    ),
                    "sort": "updated",
                    "order": "desc",
                    "per_page": GITHUB_MAX_RESULTS_PER_QUERY,
                }

                data = await fetch_json(
                    client,
                    f"{GITHUB_API}/search/repositories",
                    headers=headers,
                    params=params,
                )

                if not isinstance(data, dict):
                    return []

                items = data.get(
                    "items",
                    [],
                )

                query_results = []

                for repo in items:

                    if not isinstance(repo, dict):
                        continue

                    full_name = repo.get(
                        "full_name"
                    )

                    html_url = repo.get(
                        "html_url"
                    )

                    if not full_name or not html_url:
                        continue

                    description = clean_text(
                        repo.get("description"),
                        1000,
                    )

                    updated_at = repo.get(
                        "updated_at"
                    )

                    title = (
                        f"GitHub project: "
                        f"{full_name}"
                    )

                    query_results.append(
                        make_article(
                            title=title,
                            url=html_url,
                            source="GitHub",
                            source_type="github",
                            published_at=updated_at,
                            summary=description,
                            category="Technology",
                            content_type="repository",
                        )
                    )

                return query_results

            except Exception as exc:

                logger.warning(
                    "GitHub search failed for '%s': %s",
                    query,
                    exc,
                )

                return []

    batches = await asyncio.gather(
        *[
            search_query(query)
            for query in GITHUB_SEARCH_QUERIES
        ]
    )

    for batch in batches:
        results.extend(batch)

    return results



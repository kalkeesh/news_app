"""Normalize, filter, deduplicate, and persist collected news."""

import html
import logging
import json
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

import httpx

from app.models.article import Article
from app.repositories.article_repository import ArticleRepository
from app.services.ai.ai_service import AIBatchError, classify_ambiguous_batch
from app.services.news_collector import collect_all_news


TAG_RE = re.compile(r"<[^>]*>")
SPACE_RE = re.compile(r"\s+")
SPAM_TERMS = ("login", "sign in", "subscribe", "privacy policy", "terms of use")
logger = logging.getLogger(__name__)

AI_CONFIDENT_TERMS = {
    "artificial intelligence", "generative ai",
    "large language model", "llm", "ai model", "ai agent", "ai research", "ai safety",
    "computer vision", "natural language processing",
    "openai", "anthropic", "chatgpt", "claude", "gemini", "hugging face",
}
AI_SIGNAL_TERMS = {
    "ai", "inference", "foundation model", "transformer", "fine-tuning", "fine tuning",
    "gpu", "nvidia", "accelerator", "autonomous", "generative", "model training",
    "ai regulation", "ai policy", "ai startup", "ai chip", "ai hardware",
}
AI_MAX_BATCH_ARTICLES_DEFAULT = 50
AI_MAX_PROMPT_CHARS_DEFAULT = 30000


def clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = SPACE_RE.sub(" ", html.unescape(TAG_RE.sub(" ", value))).strip()
    return cleaned or None


def parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def usable_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return url


async def resolve_google_url(url: str) -> str:
    """Resolve only Google News redirect URLs to their publisher URL."""
    host = urlparse(url).netloc.lower().split(":", 1)[0]
    if host not in {"news.google.com", "www.news.google.com"}:
        return url
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "AI-News-Aggregator/1.0"})
            final_url = usable_url(str(response.url))
            return final_url or url
    except httpx.HTTPError:
        logger.warning("Could not resolve Google News URL; retaining original URL")
        return url


def quality_score(title: str, summary: str | None, url: str) -> float:
    score = 0.55
    if len(title) >= 25:
        score += 0.15
    if summary and len(summary) >= 40:
        score += 0.15
    if urlparse(url).path not in {"", "/"}:
        score += 0.1
    if any(term in title.lower() for term in SPAM_TERMS):
        score -= 0.5
    return max(0.0, min(1.0, score))


def classify_locally(article: Article) -> tuple[str, dict[str, Any]]:
    text = " ".join(filter(None, [article.title, article.source, article.summary, article.category])).casefold()
    confident_hits = sum(term in text for term in AI_CONFIDENT_TERMS)
    signal_hits = sum(term in text for term in AI_SIGNAL_TERMS)
    if confident_hits:
        return "keep", {
            "category": "AI",
            "subcategory": "AI",
            "topics": [],
            "ai_relevance_score": min(1.0, 0.6 + confident_hits * 0.1),
            "importance_score": min(10.0, 4.0 + confident_hits),
            "why_it_matters": None,
            "summary": article.summary,
            "ai_processed": False,
        }
    if signal_hits:
        return "ambiguous", {}
    return "reject", {}


def _ai_signal_score(article: Article) -> tuple[int, float, str]:
    text = " ".join(filter(None, [article.title, article.source, article.summary])).casefold()
    hits = sum(term in text for term in AI_SIGNAL_TERMS)
    return hits, article.quality_score, article.title_source_key


def normalize_article(raw: Any) -> Article | None:
    if not isinstance(raw, dict):
        return None
    title = clean_text(raw.get("title"))
    url = usable_url(raw.get("url"))
    if not title or len(title) < 8 or not url:
        return None
    source = clean_text(raw.get("source")) or "Unknown"
    source_type = clean_text(raw.get("source_type")) or "unknown"
    summary = clean_text(raw.get("summary"))
    normalized_title = SPACE_RE.sub(" ", title.casefold())
    key = f"{normalized_title}|{source.casefold()}"
    score = quality_score(title, summary, url)
    if score < 0.3:
        return None
    now = datetime.now(timezone.utc)
    return Article(
        title=title,
        url=url,
        original_url=usable_url(raw.get("original_url")),
        source=source,
        source_type=source_type,
        published_at=parse_datetime(raw.get("published_at")),
        summary=summary,
        image_url=usable_url(raw.get("image_url")),
        category=clean_text(raw.get("category")),
        language=clean_text(raw.get("language")),
        quality_score=score,
        created_at=now,
        updated_at=now,
        title_source_key=key,
    )


async def ingest_articles(
    repository: ArticleRepository,
    collector: Callable[[], Awaitable[list[dict[str, Any]]]] = collect_all_news,
) -> dict[str, Any]:
    raw_articles = await collector()
    fetched_by_source: dict[str, int] = {}
    for raw_article in raw_articles:
        if isinstance(raw_article, dict):
            source_type = raw_article.get("source_type") or "unknown"
            fetched_by_source[source_type] = fetched_by_source.get(source_type, 0) + 1
    resolved_articles = []
    for raw_article in raw_articles:
        if isinstance(raw_article, dict) and usable_url(raw_article.get("url")):
            resolved_url = await resolve_google_url(raw_article["url"])
            raw_article = {**raw_article, "url": resolved_url}
            if urlparse(raw_article["url"]).netloc.lower().endswith("google.com"):
                raw_article["original_url"] = raw_article.get("original_url") or raw_article["url"]
            resolved_articles.append(raw_article)
    raw_articles = resolved_articles
    normalized: list[Article] = []
    rejected = 0
    seen_urls: set[str] = set()
    seen_title_source_keys: set[str] = set()
    duplicates_removed = 0
    for raw_article in raw_articles:
        article = normalize_article(raw_article)
        if article is None:
            rejected += 1
            continue
        if article.url in seen_urls or article.title_source_key in seen_title_source_keys:
            duplicates_removed += 1
            continue
        seen_urls.add(article.url)
        seen_title_source_keys.add(article.title_source_key)
        normalized.append(article)

    total_normalized = len(normalized)
    existing_urls, existing_keys = await repository.existing_keys(normalized)
    existing_normalized_count = sum(
        article.url in existing_urls or article.title_source_key in existing_keys
        for article in normalized
    )
    normalized = [
        article for article in normalized
        if article.url not in existing_urls
        and article.title_source_key not in existing_keys
    ]

    candidates: list[Article] = []
    rejected_by_relevance = 0
    ambiguous_articles: list[Article] = []
    for article in normalized:
        decision, enrichment = classify_locally(article)
        if decision == "reject":
            rejected_by_relevance += 1
            continue
        if decision == "ambiguous":
            ambiguous_articles.append(article)
            continue
        now = datetime.now(timezone.utc)
        candidates.append(article.model_copy(update={**enrichment, "ai_processed": False, "ai_processed_at": None, "ai_provider": None, "updated_at": now}))

    ai_stats = {"gemini_batches": 0, "groq_batches": 0, "openrouter_batches": 0, "ai_failures": 0}
    ai_articles_processed = 0
    provider_articles_processed = {"gemini": 0, "groq": 0, "openrouter": 0}
    ai_articles_skipped_by_limit = 0
    if ambiguous_articles:
        max_articles = max(1, int(os.getenv("AI_MAX_BATCH_ARTICLES", str(AI_MAX_BATCH_ARTICLES_DEFAULT))))
        configured_prompt_chars = max(1000, int(os.getenv("AI_MAX_PROMPT_CHARS", str(AI_MAX_PROMPT_CHARS_DEFAULT))))
        # Leave room for the provider instruction wrapper around the records.
        max_prompt_chars = max(500, configured_prompt_chars - 2000)
        ranked = sorted(ambiguous_articles, key=lambda article: (-_ai_signal_score(article)[0], -_ai_signal_score(article)[1], _ai_signal_score(article)[2]))
        selected_articles: list[Article] = []
        prompt_chars = 2
        for article in ranked:
            if len(selected_articles) >= max_articles:
                break
            record_size = len(json.dumps({"id": article.title_source_key, "title": article.title, "source": article.source, "summary": article.summary or ""}, ensure_ascii=True, separators=(",", ":")))
            if selected_articles and prompt_chars + record_size + 1 > max_prompt_chars:
                continue
            if not selected_articles and prompt_chars + record_size > max_prompt_chars:
                continue
            selected_articles.append(article)
            prompt_chars += record_size + 1
        ai_articles_skipped_by_limit = len(ambiguous_articles) - len(selected_articles)
        ambiguous_articles = selected_articles
        records = [
            {
                "id": article.title_source_key,
                "title": article.title,
                "source": article.source,
                "summary": article.summary or "",
            }
            for article in ambiguous_articles
        ]
        try:
            classifications, ai_stats = await classify_ambiguous_batch(records)
        except AIBatchError as error:
            ai_stats = error.stats
            logger.warning("Skipping ambiguous batch after all AI providers failed: %s", error)
        else:
            now = datetime.now(timezone.utc)
            ai_articles_processed = len(classifications)
            selected_provider = next(iter(classifications.values()), {}).get("ai_provider")
            if selected_provider:
                provider_articles_processed[selected_provider] = len(classifications)
            for article in ambiguous_articles:
                classification = classifications[article.title_source_key]
                if not classification["keep"]:
                    rejected_by_relevance += 1
                    continue
                candidates.append(article.model_copy(update={
                    **{key: value for key, value in classification.items() if key not in {"id", "keep"}},
                    "ai_processed": True,
                    "ai_processed_at": now,
                    "updated_at": now,
                }))

    existing_urls, existing_keys = await repository.existing_keys(candidates)
    new_articles = [
        article for article in candidates
        if article.url not in existing_urls
        and article.title_source_key not in existing_keys
    ]
    already_existing = existing_normalized_count + len(candidates) - len(new_articles)
    inserted = await repository.insert_new(new_articles)
    return {
        "total_fetched": len(raw_articles),
        "total_normalized": total_normalized,
        "duplicates_removed": duplicates_removed,
        "rejected": rejected,
        "rejected_by_relevance": rejected_by_relevance,
        "gemini_processed": provider_articles_processed["gemini"],
        "inserted": inserted,
        "already_existing": already_existing + len(new_articles) - inserted,
        "fetched_by_source": fetched_by_source,
        "gemini_batches": ai_stats["gemini_batches"],
        "groq_batches": ai_stats["groq_batches"],
        "openrouter_batches": ai_stats["openrouter_batches"],
        "ai_articles_processed": ai_articles_processed,
        "ai_articles_skipped_by_limit": ai_articles_skipped_by_limit,
        "ai_failures": ai_stats["ai_failures"],
    }

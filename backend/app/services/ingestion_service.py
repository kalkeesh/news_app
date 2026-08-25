"""Normalize, filter, deduplicate, and persist collected news."""

import html
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from app.models.article import Article
from app.repositories.article_repository import ArticleRepository
from app.services.news_collector import collect_all_news
from app.services.gemini_service import GeminiClassificationError, classify_article


TAG_RE = re.compile(r"<[^>]*>")
SPACE_RE = re.compile(r"\s+")
SPAM_TERMS = ("login", "sign in", "subscribe", "privacy policy", "terms of use")
logger = logging.getLogger(__name__)

AI_TERMS = {
    "artificial intelligence", "generative ai", "machine learning", "llm", "large language model",
    "openai", "chatgpt", "gemini", "anthropic", "claude", "nvidia ai", "ai agent", "ai model",
    "ai research", "ai regulation", "ai safety", "deep learning", "neural network",
}
TECH_TERMS = {
    "software", "programming", "developer", "cloud", "cybersecurity", "cyber security", "semiconductor",
    "chip", "hardware", "smartphone", "database", "developer tools", "enterprise technology", "it industry",
    "tech company", "startup", "coding", "data center", "operating system", "job", "computing",
}
INDIA_TERMS = {"india", "indian", "new delhi", "lok sabha", "rajya sabha", "modi", "bjp", "congress party"}
POLITICS_TERMS = {"politics", "political", "election", "minister", "government", "parliament", "president", "senate", "congress"}
GENERAL_IRRELEVANT_TERMS = {"celebrity", "recipe", "football", "cricket", "movie", "horoscope", "weather", "travel"}


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
    ai_hits = sum(term in text for term in AI_TERMS)
    tech_hits = sum(term in text for term in TECH_TERMS)
    india_hits = sum(term in text for term in INDIA_TERMS)
    politics_hits = sum(term in text for term in POLITICS_TERMS)
    irrelevant_hits = sum(term in text for term in GENERAL_IRRELEVANT_TERMS)
    if irrelevant_hits and not ai_hits and not tech_hits:
        return "reject", {}
    if politics_hits and not india_hits and not (ai_hits or tech_hits):
        return "reject", {}
    if ai_hits or tech_hits or (politics_hits and india_hits):
        category = "AI" if ai_hits else "Indian Politics" if politics_hits and india_hits else "Technology"
        subcategory = "AI" if ai_hits else "Indian Politics" if politics_hits and india_hits else "Technology"
        score = min(1.0, 0.55 + 0.1 * max(ai_hits, tech_hits, india_hits))
        return "keep", {
            "category": category,
            "subcategory": subcategory,
            "topics": [],
            "ai_relevance_score": min(1.0, ai_hits * 0.25) if ai_hits else 0.0,
            "technology_relevance_score": min(1.0, tech_hits * 0.2) if tech_hits else 0.0,
            "indian_politics_relevance_score": min(1.0, india_hits * 0.25) if politics_hits else 0.0,
            "importance_score": min(10.0, 4.0 + max(ai_hits, tech_hits, india_hits)),
            "why_it_matters": None,
            "summary": article.summary,
            "ai_processed": False,
        }
    if not text or len(text) < 20:
        return "reject", {}
    return "ambiguous", {}


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


async def ingest_articles(repository: ArticleRepository) -> dict[str, int]:
    raw_articles = await collect_all_news()
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

    candidates: list[Article] = []
    rejected_by_relevance = 0
    gemini_processed = 0
    for article in normalized:
        decision, enrichment = classify_locally(article)
        if decision == "reject":
            rejected_by_relevance += 1
            continue
        if decision == "ambiguous":
            try:
                enrichment = await classify_article(article.title, article.source, article.summary)
                gemini_processed += 1
            except GeminiClassificationError as error:
                logger.warning("Skipping ambiguous article after Gemini failure: %s", error)
                continue
            if not enrichment["keep"]:
                rejected_by_relevance += 1
                continue
        now = datetime.now(timezone.utc)
        candidates.append(article.model_copy(update={**enrichment, "ai_processed": decision == "ambiguous", "ai_processed_at": now if decision == "ambiguous" else None, "updated_at": now}))

    existing_urls, existing_keys = await repository.existing_keys(candidates)
    new_articles = [
        article for article in candidates
        if article.url not in existing_urls
        and article.title_source_key not in existing_keys
    ]
    already_existing = len(candidates) - len(new_articles)
    inserted = await repository.insert_new(new_articles)
    return {
        "total_fetched": len(raw_articles),
        "total_normalized": len(normalized),
        "duplicates_removed": duplicates_removed,
        "rejected": rejected,
        "rejected_by_relevance": rejected_by_relevance,
        "gemini_processed": gemini_processed,
        "inserted": inserted,
        "already_existing": already_existing + len(new_articles) - inserted,
    }
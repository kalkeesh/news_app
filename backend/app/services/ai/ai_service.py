"""Provider fallback orchestration for one batch of ambiguous articles."""

from __future__ import annotations

import json
import logging
import math
import os
from typing import Any, Awaitable, Callable

from app.services.gemini_service import GeminiClassificationError, classify_articles_batch
from .groq_service import GroqClassificationError, classify_batch as classify_groq
from .openrouter_service import OpenRouterClassificationError, classify_batch as classify_openrouter

logger = logging.getLogger(__name__)


class AIBatchError(RuntimeError):
    def __init__(self, message: str, stats: dict[str, int]):
        super().__init__(message)
        self.stats = stats


def _validate_results(records: list[dict[str, str | None]], values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expected = {record["id"] for record in records}
    if not all(isinstance(value, dict) for value in values):
        raise ValueError("AI provider returned a non-object result")
    if len(values) != len(expected) or {value.get("id") for value in values} != expected:
        raise ValueError("AI provider returned an incomplete or mismatched batch")
    allowed = {"AI"}
    required = {
        "id", "keep", "category", "subcategory", "topics", "ai_relevance_score", "summary",
        "why_it_matters", "importance_score",
    }
    allowed_fields = required
    validated = []
    for value in values:
        if not isinstance(value, dict) or not required.issubset(value):
            raise ValueError("AI provider returned an incomplete result")
        if set(value) != allowed_fields:
            raise ValueError("AI provider returned unexpected fields")
        if not isinstance(value.get("id"), str) or not value["id"]:
            raise ValueError("AI provider returned an invalid id")
        if not isinstance(value.get("keep"), bool):
            raise ValueError("AI provider returned an invalid keep value")
        category = value.get("category")
        if category not in allowed:
            raise ValueError("AI provider returned an invalid category")
        try:
            importance = max(0.0, min(10.0, float(value.get("importance_score"))))
            ai_relevance_score = max(0.0, min(1.0, float(value.get("ai_relevance_score", 0))))
        except (TypeError, ValueError) as error:
            raise ValueError("AI provider returned invalid scores") from error
        if not math.isfinite(importance) or not math.isfinite(ai_relevance_score):
            raise ValueError("AI provider returned invalid scores")
        validated.append({
            "id": value["id"],
            "keep": value["keep"],
            "category": "AI",
            "subcategory": str(value.get("subcategory") or "")[:120],
            "topics": [str(topic)[:80] for topic in value.get("topics", []) if isinstance(topic, str)][:10],
            "ai_relevance_score": ai_relevance_score,
            "summary": str(value.get("summary") or "")[:1000],
            "why_it_matters": str(value.get("why_it_matters") or "")[:1000],
            "importance_score": importance,
        })
    return validated


async def classify_ambiguous_batch(records: list[dict[str, str | None]]) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    stats = {"gemini_batches": 0, "groq_batches": 0, "openrouter_batches": 0, "ai_failures": 0}
    providers: list[tuple[str, Callable[[list[dict[str, str | None]]], Awaitable[list[dict[str, Any]]]], type[Exception]]] = [
        ("gemini", classify_articles_batch, GeminiClassificationError),
        ("groq", classify_groq, GroqClassificationError),
        ("openrouter", classify_openrouter, OpenRouterClassificationError),
    ]
    errors = []
    for provider, classify, error_type in providers:
        stats[f"{provider}_batches"] += 1
        try:
            values = _validate_results(records, await classify(records))
            return {value["id"]: {**value, "ai_provider": provider} for value in values}, stats
        except Exception as error:
            logger.warning("AI provider %s failed: %s", provider, str(error)[:300].replace("\n", " "))
            errors.append(f"{provider}: {error}")
    stats["ai_failures"] = 1
    raise AIBatchError("All AI providers failed: " + "; ".join(errors), stats)

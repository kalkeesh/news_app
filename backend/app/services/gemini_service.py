"""Small, structured Gemini classification client."""

import json
import os
from typing import Any

import httpx


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_TIMEOUT = 30.0


class GeminiClassificationError(RuntimeError):
    """Raised when Gemini cannot return a valid classification."""


def _response_schema() -> dict[str, Any]:
    return {
        "type": "OBJECT",
        "properties": {
            "keep": {"type": "BOOLEAN"},
            "category": {"type": "STRING", "enum": ["AI", "Technology", "Indian Politics"]},
            "subcategory": {"type": "STRING"},
            "ai_relevance_score": {"type": "NUMBER"},
            "technology_relevance_score": {"type": "NUMBER"},
            "indian_politics_relevance_score": {"type": "NUMBER"},
            "importance_score": {"type": "NUMBER"},
            "topics": {"type": "ARRAY", "items": {"type": "STRING"}},
            "summary": {"type": "STRING"},
            "why_it_matters": {"type": "STRING"},
        },
        "required": [
            "keep", "category", "subcategory", "ai_relevance_score",
            "technology_relevance_score", "indian_politics_relevance_score",
            "importance_score", "topics", "summary", "why_it_matters",
        ],
    }


def _clamp(value: Any, lower: float, upper: float) -> float:
    try:
        return max(lower, min(upper, float(value)))
    except (TypeError, ValueError):
        raise GeminiClassificationError("Gemini returned an invalid numeric score")


def validate_classification(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("keep"), bool):
        raise GeminiClassificationError("Gemini returned an invalid classification")
    category = value.get("category")
    if value["keep"] and category not in {"AI", "Technology", "Indian Politics"}:
        raise GeminiClassificationError("Gemini returned an invalid category")
    return {
        "keep": value["keep"],
        "category": category if category in {"AI", "Technology", "Indian Politics"} else None,
        "subcategory": str(value.get("subcategory") or "")[:120],
        "ai_relevance_score": _clamp(value.get("ai_relevance_score"), 0.0, 1.0),
        "technology_relevance_score": _clamp(value.get("technology_relevance_score"), 0.0, 1.0),
        "indian_politics_relevance_score": _clamp(value.get("indian_politics_relevance_score"), 0.0, 1.0),
        "importance_score": _clamp(value.get("importance_score"), 0.0, 10.0),
        "topics": [str(topic)[:80] for topic in value.get("topics", []) if isinstance(topic, str)][:10],
        "summary": str(value.get("summary") or "")[:1000],
        "why_it_matters": str(value.get("why_it_matters") or "")[:1000],
    }


async def classify_article(title: str, source: str, summary: str | None) -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiClassificationError("GEMINI_API_KEY is not configured")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    prompt = (
        "Classify this news article for an AI-first aggregator. Keep only AI, Technology, "
        "or politics specifically related to India. Score importance by real-world impact "
        "on technology, developers, companies, infrastructure, or Indian national policy. "
        "Return only the requested JSON.\n\n"
        f"title: {title}\nsource: {source}\nsummary: {summary or '(none)'}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": _response_schema(),
        },
    }
    try:
        async with httpx.AsyncClient(timeout=GEMINI_TIMEOUT) as client:
            response = await client.post(
                GEMINI_URL.format(model=model),
                params={"key": api_key},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            text = body["candidates"][0]["content"]["parts"][0]["text"]
            return validate_classification(json.loads(text))
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise GeminiClassificationError(f"Gemini classification failed: {error}") from error
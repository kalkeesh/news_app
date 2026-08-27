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
            "category": {"type": "STRING", "enum": ["AI"]},
            "subcategory": {"type": "STRING"},
            "ai_relevance_score": {"type": "NUMBER"},
            "importance_score": {"type": "NUMBER"},
            "topics": {"type": "ARRAY", "items": {"type": "STRING"}},
            "summary": {"type": "STRING"},
            "why_it_matters": {"type": "STRING"},
        },
        "required": [
            "keep", "category", "subcategory", "ai_relevance_score",
            "importance_score", "topics", "summary", "why_it_matters",
        ],
    }


def _batch_response_schema() -> dict[str, Any]:
    schema = _response_schema()
    schema["properties"]["id"] = {"type": "STRING"}
    schema["required"].append("id")
    return {
        "type": "OBJECT",
        "properties": {"results": {"type": "ARRAY", "items": schema}},
        "required": ["results"],
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
    if category != "AI":
        raise GeminiClassificationError("Gemini returned an invalid category")
    return {
        "keep": value["keep"],
        "category": "AI" if category == "AI" else None,
        "subcategory": str(value.get("subcategory") or "")[:120],
        "ai_relevance_score": _clamp(value.get("ai_relevance_score"), 0.0, 1.0),
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
        "Classify this news article for an AI-only aggregator. Keep only genuinely AI-related "
        "content. Generic technology, software, developer, or politics stories are not enough. "
        "Score importance by real-world impact on AI research, models, agents, companies, "
        "developer tools, infrastructure, chips, robotics, regulation, or breakthroughs. "
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
    except httpx.HTTPStatusError as error:
        raise GeminiClassificationError(f"Gemini HTTP {error.response.status_code}: {error.response.text[:500].replace(chr(10), ' ')}") from error
    except httpx.RequestError as error:
        raise GeminiClassificationError(f"Gemini request error {type(error).__name__}: {error}") from error
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise GeminiClassificationError(f"Gemini classification failed ({type(error).__name__}): {error or 'no details'}") from error


async def classify_articles_batch(articles: list[dict[str, str | None]]) -> list[dict[str, Any]]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiClassificationError("GEMINI_API_KEY is not configured")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    prompt = (
        "Classify each lightweight news article for an AI-only aggregator. Keep only genuinely "
        "AI-related content. Generic technology, software, developer, or politics stories are not enough. "
        "Return JSON only: an object with a results array. No markdown, no ```json fences, no explanations. "
        "Return exactly one result per input, preserving each id exactly. category must be exactly AI. "
        "Use importance from 0 to 10 and relevance scores from 0 to 1.\n\n"
        + json.dumps(articles, ensure_ascii=True)
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": _batch_response_schema(),
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
            if text.strip().startswith("```"):
                text = text.strip().split("\n", 1)[1].rsplit("```", 1)[0].strip()
            envelope = json.loads(text)
            values = envelope.get("results") if isinstance(envelope, dict) else None
            if not isinstance(values, list):
                raise GeminiClassificationError("Gemini returned an invalid results envelope")
            return [{"id": item.get("id"), **validate_classification(item)} for item in values if isinstance(item, dict)]
    except GeminiClassificationError:
        raise
    except httpx.HTTPStatusError as error:
        raise GeminiClassificationError(f"Gemini HTTP {error.response.status_code}: {error.response.text[:500].replace(chr(10), ' ')}") from error
    except httpx.RequestError as error:
        raise GeminiClassificationError(f"Gemini request error {type(error).__name__}: {error}") from error
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise GeminiClassificationError(f"Gemini batch classification failed ({type(error).__name__}): {error or 'no details'}") from error

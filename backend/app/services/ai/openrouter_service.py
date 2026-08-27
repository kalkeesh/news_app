"""Asynchronous OpenRouter batch classification client."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_DEFAULT_MODEL = "minimax/minimax-m3:free"
AI_TIMEOUT = 30.0


class OpenRouterClassificationError(RuntimeError):
    pass


def _prompt(records: list[dict[str, str | None]]) -> str:
    return (
        "Classify every article for an AI-only news application. Keep only genuinely AI-related "
        "content; generic technology, software, developer, or politics stories must be false. "
        "Return JSON only, with no markdown, no ```json fences, and no explanations. Return exactly "
        "one result per input id, preserving every id exactly. category must be exactly AI. "
        "Return a JSON object with a results array containing exactly one result per input id, using "
        "fields id, keep, category, subcategory, topics, ai_relevance_score, summary, "
        "why_it_matters, importance_score.\n\n"
        + json.dumps(records, ensure_ascii=True)
    )


async def classify_batch(records: list[dict[str, str | None]]) -> list[dict[str, Any]]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise OpenRouterClassificationError("OPENROUTER_API_KEY is not configured")
    payload = {
        "model": os.getenv("OPENROUTER_MODEL", OPENROUTER_DEFAULT_MODEL),
        "messages": [
            {"role": "system", "content": "Return only valid JSON."},
            {"role": "user", "content": _prompt(records)},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=AI_TIMEOUT) as client:
            response = await client.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            values = json.loads(content)
            if isinstance(values, dict):
                values = values.get("results")
            if not isinstance(values, list):
                raise OpenRouterClassificationError("OpenRouter returned a non-list batch")
            return values
    except OpenRouterClassificationError:
        raise
    except httpx.HTTPStatusError as error:
        detail = error.response.text[:500].replace("\n", " ")
        raise OpenRouterClassificationError(f"OpenRouter HTTP {error.response.status_code}: {detail}") from error
    except httpx.RequestError as error:
        raise OpenRouterClassificationError(f"OpenRouter request error {type(error).__name__}: {error}") from error
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise OpenRouterClassificationError(f"OpenRouter batch classification failed ({type(error).__name__}): {error or 'no details'}") from error

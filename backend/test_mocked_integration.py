"""Offline integration checks for both service collectors and ingestion wiring."""
import asyncio
from app.services import news_collector
import app.services.ingestion_service as ingestion
from app.services.ai import ai_service

async def source_checks():
    a_expected = {"official_ai", "hackernews", "google_news", "newsdata", "guardian"}
    b_expected = {"targeted_google_news", "huggingface", "github"}
    assert {name for name, _ in news_collector._service_a_sources()} == a_expected
    assert {name for name, _ in news_collector._service_b_sources()} == b_expected
    assert not any("gdelt" in name.lower() for name, _ in news_collector._service_b_sources())
    names = ["collect_official_ai", "collect_hacker_news", "collect_google_news_targeted", "collect_huggingface", "collect_github", "fetch_google_news", "fetch_newsdata_news", "fetch_guardian_news"]
    old = {name: getattr(news_collector, name) for name in names}
    async def fake(name, *args, **kwargs): return [{"source_type": name, "title": "AI signal", "url": "https://example.test/" + name, "source": name}]
    try:
        for name in names:
            async def replacement(*args, _name=name, **kwargs): return await fake(_name, *args, **kwargs)
            setattr(news_collector, name, replacement)
        a = await news_collector.collect_service_a_news()
        b = await news_collector.collect_service_b_news()
        assert {item["source_type"] for item in a} == set(names[:2] + names[5:])
        assert {item["source_type"] for item in b} == set(names[2:5])
    finally:
        for name, value in old.items(): setattr(news_collector, name, value)

async def ingestion_check(expected_sources):
    raw = [{"title": f"Nvidia inference update {name}", "url": f"https://example.test/{name}", "source": name, "source_type": name, "summary": "Inference accelerator news."} for name in expected_sources]
    calls = []
    async def fake_collect(): return raw
    async def fake_batch(records):
        calls.append(records)
        assert all(set(record) == {"id", "title", "source", "summary"} for record in records)
        values = {record["id"]: {"id": record["id"], "keep": True, "category": "AI", "subcategory": "Infrastructure", "topics": ["inference"], "ai_relevance_score": .9, "summary": "classified", "why_it_matters": "impact", "importance_score": 8, "ai_provider": "gemini"} for record in records}
        return values, {"gemini_batches": 1, "groq_batches": 0, "openrouter_batches": 0, "ai_failures": 0}
    class Repo:
        async def existing_keys(self, articles): return set(), set()
        async def insert_new(self, articles): self.inserted = articles; return len(articles)
    old = ingestion.classify_ambiguous_batch
    try:
        ingestion.classify_ambiguous_batch = fake_batch
        stats = await ingestion.ingest_articles(Repo(), fake_collect)
    finally:
        ingestion.classify_ambiguous_batch = old
    assert len(calls) == 1 and stats["gemini_batches"] == 1
    assert stats["groq_batches"] == stats["openrouter_batches"] == 0
    assert stats["inserted"] == len(expected_sources)

async def fallback_check():
    records = [{"id": "a", "title": "AI model", "source": "x", "summary": "s"}]
    result = {"id": "a", "keep": True, "category": "AI", "subcategory": "Models", "topics": [], "ai_relevance_score": .9, "summary": "s", "why_it_matters": "i", "importance_score": 8}
    old = (ai_service.classify_articles_batch, ai_service.classify_groq, ai_service.classify_openrouter)
    try:
        calls = []
        async def gemini(_): calls.append("gemini"); raise RuntimeError("failure")
        async def groq(_): calls.append("groq"); raise RuntimeError("429")
        async def openrouter(_): calls.append("openrouter"); return [result]
        ai_service.classify_articles_batch, ai_service.classify_groq, ai_service.classify_openrouter = gemini, groq, openrouter
        values, stats = await ai_service.classify_ambiguous_batch(records)
        assert calls == ["gemini", "groq", "openrouter"] and stats["openrouter_batches"] == 1
        assert values["a"]["category"] == "AI"
    finally:
        ai_service.classify_articles_batch, ai_service.classify_groq, ai_service.classify_openrouter = old

async def main():
    await source_checks()
    await ingestion_check({"official_ai", "hackernews", "google_news", "newsdata", "guardian"})
    await ingestion_check({"targeted_google_news", "huggingface", "github"})
    await fallback_check()
    print("MOCKED_INTEGRATION: PASS")

asyncio.run(main())

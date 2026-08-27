"""Create independently deployable news API applications."""

from contextlib import asynccontextmanager
import os
from typing import Any, Awaitable, Callable

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from app.database.mongodb import close_database, get_database, initialize_database
from app.repositories.article_repository import ArticleRepository
from app.services.ingestion_service import ingest_articles


load_dotenv()
Collector = Callable[[], Awaitable[list[dict[str, Any]]]]


def create_app(collector: Collector, title: str = "AI News Aggregator") -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if os.getenv("MONGODB_URI"):
            await initialize_database()
        yield
        await close_database()

    app = FastAPI(title=title, version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def root() -> dict[str, str]:
        return {"message": title}

    @app.get("/news")
    async def get_news(
        limit: int = Query(default=20, ge=1, le=100),
        page: int = Query(default=1, ge=1),
        category: str | None = None,
        source: str | None = None,
        subcategory: str | None = None,
        topic: str | None = None,
        min_importance: float | None = Query(default=None, ge=0, le=10),
        min_ai_relevance: float | None = Query(default=None, ge=0, le=1),
        search: str | None = None,
        sort: str = Query(default="important", pattern="^(important|newest|oldest|ai)$"),
    ) -> dict[str, object]:
        repository = ArticleRepository(get_database())
        articles, total = await repository.list_articles(
            limit, category, source, subcategory, topic, min_importance,
            min_ai_relevance, search, sort, page,
        )
        return {"count": len(articles), "articles": articles, "page": page, "limit": limit, "total": total}

    @app.get("/news/{article_id}")
    async def get_article(article_id: str) -> dict[str, object]:
        from fastapi import HTTPException
        article = await ArticleRepository(get_database()).get_article(article_id)
        if article is None:
            raise HTTPException(status_code=404, detail="Article not found")
        return article

    @app.get("/stats")
    async def get_stats() -> dict[str, object]:
        return await ArticleRepository(get_database()).get_stats()

    @app.post("/admin/ingest")
    async def run_ingestion() -> dict[str, object]:
        return await ingest_articles(ArticleRepository(get_database()), collector)

    return app

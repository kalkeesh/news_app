"""Common article model used between ingestion and MongoDB."""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class Article(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    original_url: str | None = None
    source: str = "Unknown"
    source_type: str
    published_at: datetime | None = None
    summary: str | None = None
    image_url: str | None = None
    category: str | None = None
    subcategory: str | None = None
    topics: list[str] = Field(default_factory=list)
    language: str | None = None
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    ai_relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    importance_score: float = Field(default=0.0, ge=0.0, le=10.0)
    why_it_matters: str | None = None
    ai_processed: bool = False
    ai_processed_at: datetime | None = None
    ai_provider: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    title_source_key: str = ""
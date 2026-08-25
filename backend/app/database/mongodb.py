"""MongoDB client and database access."""

import os
from typing import Any

from pymongo import ASCENDING, AsyncMongoClient


_client: AsyncMongoClient[Any] | None = None


def get_database() -> Any:
    """Return the configured MongoDB database, creating the client lazily."""
    global _client
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI is not configured")

    if _client is None:
        _client = AsyncMongoClient(uri, tz_aware=True)

    return _client[os.getenv("MONGODB_DATABASE", "news_ai")]


async def initialize_database() -> None:
    """Create indexes required by the article repository."""
    database = get_database()
    articles = database["articles"]
    await articles.create_index([("url", ASCENDING)], unique=True, name="article_url_unique")
    await articles.create_index(
        [("title_source_key", ASCENDING)],
        name="article_title_source_key",
    )
    await articles.create_index([("importance_score", -1)], name="article_importance_desc")


async def close_database() -> None:
    """Close the shared client when the application shuts down."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
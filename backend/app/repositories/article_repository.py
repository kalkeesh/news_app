"""MongoDB operations for articles."""

from collections.abc import Iterable
from typing import Any

from pymongo.errors import BulkWriteError

from app.models.article import Article


class ArticleRepository:
    def __init__(self, database: Any):
        self.collection = database["articles"]

    async def existing_keys(self, articles: Iterable[Article]) -> tuple[set[str], set[str]]:
        articles = list(articles)
        urls = {article.url for article in articles}
        title_source_keys = {article.title_source_key for article in articles}
        query = {
            "$or": [
                {"url": {"$in": list(urls)}},
                {"title_source_key": {"$in": list(title_source_keys)}},
            ]
        }
        existing_urls: set[str] = set()
        existing_title_source_keys: set[str] = set()
        async for document in self.collection.find(query, {"url": 1, "title_source_key": 1}):
            if document.get("url"):
                existing_urls.add(document["url"])
            if document.get("title_source_key"):
                existing_title_source_keys.add(document["title_source_key"])
        return existing_urls, existing_title_source_keys

    async def insert_new(self, articles: list[Article]) -> int:
        if not articles:
            return 0
        try:
            result = await self.collection.insert_many(
                [article.model_dump() for article in articles],
                ordered=False,
            )
            return len(result.inserted_ids)
        except BulkWriteError as error:
            duplicate_indexes = {
                detail.get("index")
                for detail in error.details.get("writeErrors", [])
                if detail.get("code") == 11000
            }
            non_duplicate_errors = [
                detail for detail in error.details.get("writeErrors", [])
                if detail.get("code") != 11000
            ]
            if non_duplicate_errors:
                raise
            return len(articles) - len(duplicate_indexes)

    async def list_articles(
        self,
        limit: int = 50,
        category: str | None = None,
        source: str | None = None,
        subcategory: str | None = None,
        topic: str | None = None,
        min_importance: float | None = None,
        min_ai_relevance: float | None = None,
        search: str | None = None,
        sort: str = "important",
        page: int = 1,
    ) -> tuple[list[dict[str, Any]], int]:
        query: dict[str, Any] = {}
        if category:
            query["category"] = category
        if source:
            query["source"] = source
        if subcategory:
            query["subcategory"] = subcategory
        if topic:
            query["topics"] = topic
        if min_importance is not None:
            query["importance_score"] = {"$gte": min_importance}
        if min_ai_relevance is not None:
            query["ai_relevance_score"] = {"$gte": min_ai_relevance}
        if search:
            query["$or"] = [
                {"title": {"$regex": search, "$options": "i"}},
                {"summary": {"$regex": search, "$options": "i"}},
                {"source": {"$regex": search, "$options": "i"}},
                {"topics": {"$regex": search, "$options": "i"}},
                {"category": {"$regex": search, "$options": "i"}},
            ]
        sort_fields = {
            "important": [("importance_score", -1), ("published_at", -1)],
            "newest": [("published_at", -1)],
            "oldest": [("published_at", 1)],
            "ai": [("ai_relevance_score", -1), ("published_at", -1)],
        }
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).sort(sort_fields.get(sort, sort_fields["important"])).skip((page - 1) * limit).limit(limit)
        articles = []
        async for article in cursor:
            if article.get("_id"):
                article["id"] = str(article.pop("_id"))
            articles.append(article)
        return articles, total

    async def get_article(self, article_id: str) -> dict[str, Any] | None:
        from bson import ObjectId
        if not ObjectId.is_valid(article_id):
            return None
        article = await self.collection.find_one({"_id": ObjectId(article_id)})
        if article:
            article["_id"] = str(article["_id"])
        return article

    async def get_stats(self) -> dict[str, Any]:
        pipeline = [{"$group": {"_id": "$category", "count": {"$sum": 1}}}]
        grouped = {}
        cursor = await self.collection.aggregate(pipeline)
        async for item in cursor:
            if item.get("_id"):
                grouped[item["_id"]] = item["count"]
        latest = await self.collection.find_one(sort=[("updated_at", -1)], projection={"updated_at": 1})
        return {
            "total": await self.collection.count_documents({}),
            "ai": grouped.get("AI", 0),
            "latest_update": latest.get("updated_at") if latest else None,
        }
"""Service B: targeted Google News, Hugging Face, and GitHub."""

from app.app_factory import create_app
from app.database.mongodb import get_database
from app.services.news_collector import collect_service_b_news
from bson import ObjectId
from fastapi import HTTPException

app = create_app(collect_service_b_news, "AI News Aggregator - Service B")


@app.delete("/admin/articles/{article_id}")
async def delete_article(article_id: str) -> dict[str, str]:
    """Delete exactly one article by its MongoDB ObjectId."""
    if not ObjectId.is_valid(article_id):
        raise HTTPException(status_code=400, detail="Invalid article ID")
    result = await get_database()["articles"].delete_one({"_id": ObjectId(article_id)})
    if result.deleted_count != 1:
        raise HTTPException(status_code=404, detail="Article not found")
    return {"message": "Article deleted", "article_id": article_id}

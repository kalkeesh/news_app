"""Service A: official AI, Hacker News, Google News, NewsData, and Guardian."""

from app.app_factory import create_app
from app.services.news_collector import collect_service_a_news

app = create_app(collect_service_a_news, "AI News Aggregator - Service A")

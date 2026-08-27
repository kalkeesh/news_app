"""Offline verification for Service B's single-article deletion endpoint."""
import asyncio
from types import SimpleNamespace

import app.service_b as service_b


class Collection:
    def __init__(self, deleted_count):
        self.deleted_count = deleted_count
        self.calls = []

    async def delete_one(self, query):
        self.calls.append(query)
        return SimpleNamespace(deleted_count=self.deleted_count)


class Database:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == "articles"
        return self.collection


async def invoke(endpoint, article_id):
    try:
        return 200, await endpoint(article_id)
    except Exception as error:
        return error.status_code, error.detail


async def main():
    route = next(route for route in service_b.app.routes if route.path == "/admin/articles/{article_id}")
    endpoint = route.endpoint
    original = service_b.get_database
    try:
        collection = Collection(1)
        service_b.get_database = lambda: Database(collection)
        status, body = await invoke(endpoint, "507f1f77bcf86cd799439011")
        assert status == 200 and body["message"] == "Article deleted"
        assert collection.calls and "_id" in collection.calls[0]

        status, body = await invoke(endpoint, "not-an-object-id")
        assert status == 400

        collection = Collection(0)
        service_b.get_database = lambda: Database(collection)
        status, body = await invoke(endpoint, "507f1f77bcf86cd799439011")
        assert status == 404
    finally:
        service_b.get_database = original
    print("SERVICE_B_DELETE_TEST: PASS")


asyncio.run(main())

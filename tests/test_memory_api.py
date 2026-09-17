"""
M1 API tests: memory listing and deletion, with
post-delete verification against persistent storage.
"""

import os

import pytest

from fastapi.testclient import TestClient

from backend.core.memory import MemoryService
from backend.core.services import memory_service
from backend.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store():
    memory_service.clear()
    yield


def fresh_service() -> MemoryService:
    """
    A brand-new service over the same storage file —
    proves deletion persisted to disk, not just in RAM.
    """

    return MemoryService(
        storage_path=os.environ["GHOST_MEMORY_PATH"],
    )


class TestMemoryListing:

    def test_list_returns_metadata_and_content(self):
        memory_service.add_memory(
            content="My project is called GHOST.",
            memory_type="project",
            importance=0.9,
            confidence=0.8,
            tags=["test"],
            source="user",
        )

        response = client.get("/api/memory")

        assert response.status_code == 200

        body = response.json()

        assert body["total"] == 1

        memory = body["memories"][0]

        # Safe metadata fields required by M1 scope.
        assert memory["type"] == "project"
        assert memory["importance"] == 0.9
        assert memory["confidence"] == 0.8
        assert memory["tags"] == ["test"]
        assert memory["created_at"]
        assert memory["updated_at"]

        # Full content on the dedicated memory endpoint
        # (user visibility, spec §35).
        assert (
            memory["content"]
            == "My project is called GHOST."
        )

    def test_empty_store(self):
        response = client.get("/api/memory")

        assert response.status_code == 200
        assert response.json() == {
            "memories": [],
            "total": 0,
        }


class TestMemoryDeletion:

    def test_delete_removes_and_verifies(self):
        memory = memory_service.add_memory(
            content="temporary memory for deletion",
        )

        response = client.delete(
            f"/api/memory/{memory['id']}",
        )

        assert response.status_code == 200

        body = response.json()

        assert body["deleted"] is True
        assert body["verified"] is True

        # Gone from the live API...
        listing = client.get("/api/memory").json()

        assert listing["total"] == 0

        # ...and gone from persistent storage.
        assert (
            fresh_service().get(memory["id"])
            is None
        )

    def test_delete_unknown_memory_404(self):
        response = client.delete(
            "/api/memory/not-a-real-id",
        )

        assert response.status_code == 404

    def test_clear_all(self):
        memory_service.add_memory(content="one")
        memory_service.add_memory(content="two")

        response = client.delete("/api/memory")

        assert response.status_code == 200

        body = response.json()

        assert body["deleted"] is True
        assert body["verified"] is True

        assert (
            client.get("/api/memory").json()["total"]
            == 0
        )

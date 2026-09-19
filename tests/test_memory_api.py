"""
M1 API tests: memory listing and deletion, with
post-delete verification against persistent storage.
M2: requests now go through the authenticated client.
"""

import os

import pytest

from backend.core.memory import MemoryService
from backend.core.services import memory_service


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

    def test_list_returns_metadata_and_content(
        self,
        auth_client,
    ):
        memory_service.add_memory(
            content="My project is called GHOST.",
            memory_type="project",
            importance=0.9,
            confidence=0.8,
            tags=["test"],
            source="user",
        )

        response = auth_client.get("/api/memory")

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

    def test_empty_store(
        self,
        auth_client,
    ):
        response = auth_client.get("/api/memory")

        assert response.status_code == 200
        assert response.json() == {
            "memories": [],
            "total": 0,
        }


class TestMemoryDeletion:

    def test_delete_removes_and_verifies(
        self,
        auth_client,
    ):
        memory = memory_service.add_memory(
            content="temporary memory for deletion",
        )

        response = auth_client.delete(
            f"/api/memory/{memory['id']}",
        )

        assert response.status_code == 200

        body = response.json()

        assert body["deleted"] is True
        assert body["verified"] is True

        # Gone from the live API...
        listing = (
            auth_client.get("/api/memory").json()
        )

        assert listing["total"] == 0

        # ...and gone from persistent storage.
        assert (
            fresh_service().get(memory["id"])
            is None
        )

    def test_delete_unknown_memory_404(
        self,
        auth_client,
    ):
        response = auth_client.delete(
            "/api/memory/not-a-real-id",
        )

        assert response.status_code == 404

    def test_clear_all(
        self,
        auth_client,
    ):
        memory_service.add_memory(content="one")
        memory_service.add_memory(content="two")

        response = auth_client.delete("/api/memory")

        assert response.status_code == 200

        body = response.json()

        assert body["deleted"] is True
        assert body["verified"] is True

        assert (
            auth_client.get("/api/memory").json()[
                "total"
            ]
            == 0
        )

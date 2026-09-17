"""
Tests for the persistent memory service:
CRUD, duplicate handling, ranking, deletion.
"""

from backend.core.memory import MemoryService


def make_service(tmp_path):
    return MemoryService(
        storage_path=str(
            tmp_path / "memory.json"
        )
    )


class TestAddAndPersist:

    def test_add_memory_roundtrip(self, tmp_path):
        service = make_service(tmp_path)

        memory = service.add_memory(
            content="My project is called GHOST.",
            memory_type="project",
            importance=0.9,
            source="user",
        )

        assert memory["id"]
        assert memory["type"] == "project"

        # A second instance must see the same data.
        reloaded = make_service(tmp_path)

        assert reloaded.get_all() != []
        assert (
            reloaded.get_all()[0]["content"]
            == "My project is called GHOST."
        )

    def test_empty_content_rejected(self, tmp_path):
        service = make_service(tmp_path)

        assert (
            service.add_memory(content="   ")
            == {}
        )

        assert service.get_all() == []

    def test_importance_clamped(self, tmp_path):
        service = make_service(tmp_path)

        memory = service.add_memory(
            content="clamp test importance",
            importance=5.0,
        )

        assert memory["importance"] == 1.0


class TestDuplicates:

    def test_identical_content_not_duplicated(self, tmp_path):
        service = make_service(tmp_path)

        first = service.add_memory(
            content="I prefer dark mode.",
        )

        second = service.add_memory(
            content="  I   PREFER   dark mode.  ",
            importance=0.9,
        )

        assert (
            second["id"] == first["id"]
        )

        assert len(service.get_all()) == 1

        # Higher importance is merged into the original.
        assert (
            first["importance"] == 0.9
        )

    def test_different_content_both_stored(self, tmp_path):
        service = make_service(tmp_path)

        service.add_memory(content="I like tea.")
        service.add_memory(content="I like coffee.")

        assert len(service.get_all()) == 2


class TestSearch:

    def test_keyword_match_ranks_first(self, tmp_path):
        service = make_service(tmp_path)

        service.add_memory(
            content="My project is called GHOST.",
            memory_type="project",
        )

        service.add_memory(
            content="I like strawberries.",
            memory_type="preference",
        )

        results = service.search(
            "what is my project called?",
        )

        assert results
        assert "GHOST" in results[0]["content"]

    def test_no_match_returns_empty(self, tmp_path):
        service = make_service(tmp_path)

        service.add_memory(content="I like tea.")

        assert (
            service.search("quantum chromodynamics")
            == []
        )

    def test_type_filter(self, tmp_path):
        service = make_service(tmp_path)

        service.add_memory(
            content="Project fact one.",
            memory_type="project",
        )

        service.add_memory(
            content="Preference fact two.",
            memory_type="preference",
        )

        results = service.search(
            "fact",
            memory_type="project",
        )

        assert results
        assert all(
            r["type"] == "project"
            for r in results
        )


class TestUpdateDelete:

    def test_update_memory(self, tmp_path):
        service = make_service(tmp_path)

        memory = service.add_memory(
            content="We use REST.",
        )

        updated = service.update(
            memory["id"],
            content="We use GraphQL now.",
        )

        assert (
            updated["content"]
            == "We use GraphQL now."
        )

        # Timestamps must move forward.
        assert (
            updated["updated_at"]
            >= memory["created_at"]
        )

    def test_update_rejects_unknown_fields(self, tmp_path):
        service = make_service(tmp_path)

        memory = service.add_memory(
            content="update guard test",
        )

        updated = service.update(
            memory["id"],
            id="forged-id",
            content="still fine",
        )

        assert updated["id"] != "forged-id"

    def test_delete_memory(self, tmp_path):
        service = make_service(tmp_path)

        memory = service.add_memory(
            content="delete me",
        )

        assert service.delete(memory["id"])

        assert service.get(memory["id"]) is None
        assert service.get_all() == []

    def test_clear(self, tmp_path):
        service = make_service(tmp_path)

        service.add_memory(content="one")
        service.add_memory(content="two")

        assert service.clear()
        assert service.get_all() == []

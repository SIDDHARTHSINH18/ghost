"""
Task ownership / session isolation regression tests.

Ownership = hash of the authenticated session token, stored on
the Task. Foreign tasks are indistinguishable from unknown ones
(404) in every endpoint, including approvals and resume.
"""

import os

import pytest

from backend.core.security import hash_session_token
from backend.tasks.service import TaskService


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


class TestTaskServiceOwnership:

    def test_owner_sees_own_task(self):
        svc = TaskService()
        owner = hash_session_token("token-a")

        task = svc.create("t", "", owner=owner)

        assert svc.get(task.id, owner=owner) is task

    def test_other_session_get_is_keyerror(self):
        svc = TaskService()
        owner_a = hash_session_token("token-a")
        owner_b = hash_session_token("token-b")

        task = svc.create("t", "", owner=owner_a)

        with pytest.raises(KeyError):
            svc.get(task.id, owner=owner_b)

    def test_ownerless_task_visible_to_all(self):
        """Legacy/in-process tasks stay reachable."""

        svc = TaskService()
        owner_b = hash_session_token("token-b")

        task = svc.create("t")

        assert svc.get(task.id, owner=owner_b) is task

    def test_list_filtered_by_owner(self):
        svc = TaskService()
        owner_a = hash_session_token("token-a")
        owner_b = hash_session_token("token-b")

        svc.create("a", "", owner=owner_a)
        svc.create("b", "", owner=owner_b)
        svc.create("legacy")

        assert [t.title for t in svc.list(owner=owner_a)] == [
            "a",
            "legacy",
        ]
        assert [t.title for t in svc.list(owner=owner_b)] == [
            "b",
            "legacy",
        ]
        assert len(svc.list()) == 3


class TestTaskOwnershipAPI:
    """Full API surface with two independent sessions."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from backend.main import app

        return TestClient(app)

    @pytest.fixture
    def sessions(self, client):
        pw = os.environ["GHOST_AUTH_PASSWORD"]

        token_a = client.post(
            "/api/auth/login", json={"password": pw}
        ).json()["token"]
        token_b = client.post(
            "/api/auth/login", json={"password": pw}
        ).json()["token"]

        return _headers(token_a), _headers(token_b)

    def test_cross_session_read_is_404(
        self, client, sessions
    ):
        ha, hb = sessions

        created = client.post(
            "/api/tasks",
            headers=ha,
            json={"request": "check whether venv exists"},
        )
        task_id = created.json()["task_id"]

        assert created.status_code == 201
        assert (
            client.get(
                f"/api/tasks/{task_id}", headers=ha
            ).status_code
            == 200
        )
        assert (
            client.get(
                f"/api/tasks/{task_id}", headers=hb
            ).status_code
            == 404
        )

    def test_cross_session_listing_hides_foreign_task(
        self, client, sessions
    ):
        ha, hb = sessions

        created = client.post(
            "/api/tasks",
            headers=ha,
            json={"request": "check whether tests exist"},
        )
        task_id = created.json()["task_id"]

        b_ids = {
            t["id"]
            for t in client.get(
                "/api/tasks", headers=hb
            ).json()["tasks"]
        }
        a_ids = {
            t["id"]
            for t in client.get(
                "/api/tasks", headers=ha
            ).json()["tasks"]
        }

        assert task_id in a_ids
        assert task_id not in b_ids

    def test_cross_session_resume_is_404(self, client, sessions):
        ha, hb = sessions

        created = client.post(
            "/api/tasks",
            headers=ha,
            json={"request": "check whether docs exist"},
        )
        task_id = created.json()["task_id"]

        assert (
            client.post(
                f"/api/tasks/{task_id}/resume", headers=hb
            ).status_code
            == 404
        )

    def test_owner_still_reads_and_lists(self, client, sessions):
        ha, _ = sessions

        created = client.post(
            "/api/tasks",
            headers=ha,
            json={"request": "check whether README exists"},
        )
        task_id = created.json()["task_id"]

        detail = client.get(
            f"/api/tasks/{task_id}", headers=ha
        )
        assert detail.status_code == 200
        assert detail.json()["id"] == task_id

        ids = {
            t["id"]
            for t in client.get(
                "/api/tasks", headers=ha
            ).json()["tasks"]
        }
        assert task_id in ids

"""
Focused tests for M4 step 10 — the authenticated audit view.

Covers:
1. /api/audit requires a session
2. rows come back in append order, newest-truncated by limit
3. task_id and stage filters narrow the view
4. an unknown stage is refused instead of returning nothing
5. the view is read-only: no write/update/delete route exists
6. stored secrets stay redacted on the way out
7. a real pipeline request is audited end to end
"""

import json
import os

import pytest
from fastapi.testclient import TestClient

import backend.api.audit as audit_api
from backend.audit.log import AuditLog, AuditStage
from backend.main import app


README_ABS = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "README.md")
)


# ============================================================
# Fixtures / helpers
# ============================================================

class FakeGateway:
    def __init__(self, response):
        self._response = response
        self.generate_calls = []

    async def generate(self, **kwargs):
        self.generate_calls.append(kwargs)
        return self._response


def ready_payload():
    return json.dumps(
        {
            "enough_information": True,
            "task_title": "Read the readme",
            "task_description": "Read README.md.",
            "steps": [
                {
                    "description": "Read the file",
                    "tool": "fs_read_file",
                    "params": {"path": README_ABS},
                }
            ],
            "assumptions": [],
            "clarifying_questions": [],
        }
    )


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_client(client):
    import os

    response = client.post(
        "/api/auth/login",
        json={"password": os.environ["GHOST_AUTH_PASSWORD"]},
    )
    assert response.status_code == 200
    client.headers.update(
        {"Authorization": f"Bearer {response.json()['token']}"}
    )
    return client


@pytest.fixture
def store(monkeypatch, tmp_path):
    """A private audit file, so rows here are exactly this test's."""

    isolated = AuditLog(storage_path=str(tmp_path / "audit.jsonl"))

    monkeypatch.setattr(audit_api, "audit_log", isolated)

    return isolated


# ============================================================
# 1. Authentication
# ============================================================

def test_audit_endpoint_requires_auth(client):
    assert client.get("/api/audit").status_code == 401

    assert client.get(
        "/api/audit", params={"task_id": "anything"}
    ).status_code == 401


def test_invalid_token_rejected(client):
    client.headers.update({"Authorization": "Bearer not-a-real-token"})
    assert client.get("/api/audit").status_code == 401


# ============================================================
# 2. Append order and limits
# ============================================================

def test_empty_store_returns_no_rows(auth_client, store):
    body = auth_client.get("/api/audit").json()

    assert body["rows"] == []
    assert body["total"] == 0


def test_rows_return_in_append_order(auth_client, store):
    for index in range(3):
        store.append(
            task_id=f"task-{index}",
            stage=AuditStage.REQUEST,
            event=f"event-{index}",
        )

    body = auth_client.get("/api/audit").json()

    assert [row["event"] for row in body["rows"]] == [
        "event-0",
        "event-1",
        "event-2",
    ]
    assert [row["sequence"] for row in body["rows"]] == [1, 2, 3]
    assert body["total"] == 3


def test_limit_keeps_the_most_recent_rows(auth_client, store):
    for index in range(5):
        store.append(
            task_id="task-1",
            stage=AuditStage.TOOL,
            event=f"tool-{index}",
        )

    body = auth_client.get("/api/audit", params={"limit": 2}).json()

    assert [row["event"] for row in body["rows"]] == ["tool-3", "tool-4"]
    assert body["limit"] == 2


def test_limit_out_of_range_is_refused(auth_client, store):
    assert auth_client.get(
        "/api/audit", params={"limit": 0}
    ).status_code == 422

    assert auth_client.get(
        "/api/audit", params={"limit": audit_api.MAX_LIMIT + 1}
    ).status_code == 422


# ============================================================
# 3. Filters
# ============================================================

def test_filter_by_task_and_stage(auth_client, store):
    store.append(task_id="a", stage=AuditStage.REQUEST, event="r")
    store.append(task_id="a", stage=AuditStage.TOOL, event="t")
    store.append(task_id="b", stage=AuditStage.TOOL, event="t")

    only_a = auth_client.get(
        "/api/audit", params={"task_id": "a"}
    ).json()
    assert [row["event"] for row in only_a["rows"]] == ["r", "t"]
    assert only_a["task_id"] == "a"

    only_tools = auth_client.get(
        "/api/audit", params={"stage": "tool"}
    ).json()
    assert [row["task_id"] for row in only_tools["rows"]] == ["a", "b"]

    combined = auth_client.get(
        "/api/audit", params={"task_id": "b", "stage": "tool"}
    ).json()
    assert combined["total"] == 1
    assert combined["rows"][0]["stage"] == "tool"


def test_unknown_stage_is_refused_not_ignored(auth_client, store):
    store.append(task_id="a", stage=AuditStage.REQUEST, event="r")

    response = auth_client.get(
        "/api/audit", params={"stage": "not-a-stage"}
    )

    assert response.status_code == 400
    assert "not-a-stage" in response.json()["detail"]


def test_stage_names_are_the_pipeline_stages(auth_client, store):
    """The API exposes the same stage vocabulary the writer uses."""

    body = auth_client.get(
        "/api/audit", params={"stage": "clarification"}
    )

    allowed = {member.value for member in AuditStage}

    assert "request" in allowed and "memory" in allowed
    assert "clarification" not in allowed
    assert body.status_code == 400


# ============================================================
# 5. Read-only surface
# ============================================================

def test_audit_route_is_read_only(auth_client, store):
    """Only a listing exists: no write, update or delete verb."""

    methods = set()

    for route in audit_api.router.routes:
        if route.path == "/api/audit":
            methods |= set(route.methods)

    assert methods == {"GET"}

    # And the mounted app agrees: writing is not just absent
    # from the router, it is refused.
    assert auth_client.post("/api/audit", json={}).status_code == 405
    assert auth_client.delete("/api/audit").status_code == 405


def test_audit_log_has_no_mutation_api():
    assert not hasattr(AuditLog, "update")
    assert not hasattr(AuditLog, "delete")
    assert not hasattr(AuditLog, "truncate")
    assert not hasattr(AuditLog, "clear")


# ============================================================
# 6. Secrets stay redacted on the way out
# ============================================================

def test_stored_secrets_are_redacted_in_the_response(auth_client, store):
    store.append(
        task_id="a",
        stage=AuditStage.MODEL,
        event="raw-output",
        data={
            "authorization": "Bearer sk-SECRETSECRET123",
            "note": "password=hunter2hunter2",
            "url": "https://generativelanguage.googleapis.com"
            "/v1beta/models?key=SYNTHETIC_GOOGLE_TEST_KEY",
        },
    )

    rows = auth_client.get("/api/audit").json()["rows"]

    text = json.dumps(rows)

    assert "sk-SECRETSECRET123" not in text
    assert "hunter2hunter2" not in text
    assert assert "SYNTHETIC_GOOGLE_TEST_KEY" not in text
    assert "[redacted]" in text


# ============================================================
# 7. A real pipeline request is audited
# ============================================================

def test_pipeline_request_writes_readable_rows(
    auth_client, store, monkeypatch
):
    """One POST /api/tasks leaves the whole chain on disk."""

    import backend.api.tasks as tasks_api
    from backend.core import agent_services
    from backend.tasks import service as service_module
    from backend.tasks.runner import TaskRunner

    fresh_store = service_module.TaskService()

    monkeypatch.setattr(tasks_api, "audit_log", store)
    monkeypatch.setattr(tasks_api, "task_service", fresh_store)
    monkeypatch.setattr(
        tasks_api,
        "task_runner",
        TaskRunner(
            task_service=fresh_store,
            automation_engine=agent_services.automation_engine,
            approvals=agent_services.approval_service,
            reflection_engine=agent_services.reflection_engine,
        ),
    )
    monkeypatch.setattr(
        tasks_api.planner,
        "_orchestrator",
        FakeGateway(ready_payload()),
    )

    created = auth_client.post(
        "/api/tasks",
        json={"request": f"Read {README_ABS}"},
    )
    assert created.status_code == 201
    task_id = created.json()["task_id"]

    body = auth_client.get(
        "/api/audit", params={"task_id": task_id}
    ).json()

    stages = [row["stage"] for row in body["rows"]]

    # The whole chain is recorded, in order, for this task only.
    assert stages == [
        AuditStage.PLANNED.value,
        AuditStage.SKILL.value,
        AuditStage.SPEC.value,
        AuditStage.TOOL.value,
        AuditStage.RESULT.value,
        AuditStage.REFLECTION.value,
    ]

    # The REQUEST row exists too, but carries no task id yet.
    unassigned = auth_client.get(
        "/api/audit", params={"stage": "request"}
    ).json()["rows"]
    assert unassigned[-1]["task_id"] is None

"""
Focused tests for the M3-H live task entry point.

Verifies the wired flow:

  user request -> POST /api/tasks -> Planner -> TaskService
               -> TaskRunner -> Agent -> PermissionPolicy
               -> ToolRegistry -> tool result

- ready plans create a stored Task and execute planned
  tool steps through the permission-gated pipeline
- clarification rounds create nothing
- the Planner is never bypassed (gateway sees every request)
- execution always goes through Agent/PermissionPolicy
- session auth is enforced on the new endpoints
- existing M1/M2 endpoints keep working

The model gateway is always a fake — no network.
"""

import json
import os

import pytest

from backend.core.task import TaskStatus
from fastapi.testclient import TestClient

import backend.api.tasks as tasks_api
from backend.main import app


README_ABS = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "README.md")
)


# ============================================================
# Fakes / helpers
# ============================================================

class FakeGateway:
    """Duck-typed orchestrator gateway; records calls."""

    def __init__(self, response):
        self._response = response
        self.generate_calls = []

    async def generate(self, **kwargs):
        self.generate_calls.append(kwargs)
        return self._response


class ExplodingAgent:
    """Guard: any execution attempt fails the test."""

    def execute(self, *args, **kwargs):
        raise AssertionError(
            "No tool may execute from the task API path"
        )


def ready_payload():
    return json.dumps(
        {
            "enough_information": True,
            "task_title": "Summarize the project notes",
            "task_description": "Read and summarize the notes.",
            "steps": [
                {
                    "description": "Read the notes file",
                    "tool": "fs_read_file",
                    "params": {"path": README_ABS},
                }
            ],
            "assumptions": [],
            "clarifying_questions": [],
        }
    )


def clarification_payload():
    return json.dumps(
        {
            "enough_information": False,
            "task_title": None,
            "task_description": None,
            "steps": [],
            "assumptions": [],
            "clarifying_questions": [
                "Which notes do you mean?",
                "Where are they saved?",
            ],
        }
    )


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_client(client):
    """
    Authenticated client (mirrors conftest's pattern but
    local, so gateway monkeypatching here stays scoped).
    """

    import os

    response = client.post(
        "/api/auth/login",
        json={
            "password": os.environ["GHOST_AUTH_PASSWORD"],
        },
    )
    assert response.status_code == 200

    client.headers.update(
        {
            "Authorization": (
                f"Bearer {response.json()['token']}"
            ),
        }
    )
    return client


@pytest.fixture
def exploding_agent(monkeypatch):
    """
    Route the production agent/automation away: if the API
    path ever reaches execution, the test fails loudly.

    The task runner is rebuilt against the guard so the
    guard is actually what the API path would invoke.
    """

    from backend.core import agent_services

    guard = ExplodingAgent()
    monkeypatch.setattr(agent_services, "agent", guard)
    monkeypatch.setattr(agent_services, "automation_engine", guard)

    from backend.tasks.runner import TaskRunner

    monkeypatch.setattr(
        tasks_api,
        "task_runner",
        TaskRunner(
            task_service=tasks_api.task_service,
            automation_engine=guard,
            approvals=agent_services.approval_service,
            reflection_engine=agent_services.reflection_engine,
        ),
    )
    return guard


@pytest.fixture(autouse=True)
def empty_task_store(monkeypatch):
    """Every test starts from a clean, isolated store.

    The task runner is rebuilt against the fresh store so
    execution (when a plan has tool steps) writes to the
    isolated TaskService, mirroring production construction.
    """

    from backend.core import agent_services
    from backend.tasks import service as service_module
    from backend.tasks.runner import TaskRunner

    fresh_store = service_module.TaskService()

    monkeypatch.setattr(
        tasks_api,
        "task_service",
        fresh_store,
    )

    monkeypatch.setattr(
        tasks_api,
        "task_runner",
        TaskRunner(
            task_service=fresh_store,
            automation_engine=(
                agent_services.automation_engine
            ),
            approvals=agent_services.approval_service,
            reflection_engine=(
                agent_services.reflection_engine
            ),
        ),
    )


# ============================================================
# Clear request -> Planner -> TaskService
# ============================================================

def test_clear_request_creates_task_via_planner(
    auth_client, monkeypatch
):
    gateway = FakeGateway(ready_payload())
    monkeypatch.setattr(tasks_api.planner, "_orchestrator", gateway)

    before = len(tasks_api.task_service.list())

    response = auth_client.post(
        "/api/tasks",
        json={"request": "Summarize my notes in /tmp/notes.txt"},
    )

    assert response.status_code == 201
    body = response.json()

    assert body["status"] == "created"
    assert body["task"]["status"] == TaskStatus.COMPLETED.value
    assert body["task"]["title"] == "Summarize the project notes"
    assert body["planning"]["ready"] is True
    assert body["planning"]["source"] == "MODEL"

    # Planner was used: exactly one gateway call carrying
    # the user request verbatim.
    assert len(gateway.generate_calls) == 1
    assert (
        "Summarize my notes in /tmp/notes.txt"
        in gateway.generate_calls[0]["message"]
    )

    # TaskService stored it.
    assert len(tasks_api.task_service.list()) == before + 1
    stored = tasks_api.task_service.get(body["task_id"])
    assert stored.title == "Summarize the project notes"

    # The planned SAFE step executed through the
    # permission-gated pipeline and completed with real
    # output (the repository README).
    assert stored.status == TaskStatus.COMPLETED
    assert "GHOST" in str(stored.result)
    assert body["execution"]["task_status"] == (
        TaskStatus.COMPLETED.value
    )


# ============================================================
# Clarification-required -> no premature task
# ============================================================

def test_clarification_creates_no_task(
    auth_client, monkeypatch, exploding_agent
):
    gateway = FakeGateway(clarification_payload())
    monkeypatch.setattr(tasks_api.planner, "_orchestrator", gateway)

    before = len(tasks_api.task_service.list())

    response = auth_client.post(
        "/api/tasks",
        json={"request": "summarize the notes"},
    )

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "clarification_required"
    assert body["questions"] == [
        "Which notes do you mean?",
        "Where are they saved?",
    ]
    assert body["planning"]["ready"] is False
    assert "task_id" not in body

    # Nothing stored, nothing executed.
    assert len(tasks_api.task_service.list()) == before
    assert len(gateway.generate_calls) == 1


# ============================================================
# Task creation / retrieval endpoints
# ============================================================

def test_list_and_get_task_endpoints(auth_client, monkeypatch):
    monkeypatch.setattr(
        tasks_api.planner,
        "_orchestrator",
        FakeGateway(ready_payload()),
    )

    created = auth_client.post(
        "/api/tasks",
        json={"request": "Summarize my notes"},
    ).json()
    task_id = created["task_id"]

    listed = auth_client.get("/api/tasks").json()
    assert listed["total"] == 1
    assert listed["tasks"][0]["id"] == task_id

    single = auth_client.get(f"/api/tasks/{task_id}").json()
    assert single["id"] == task_id
    assert single["status"] == TaskStatus.COMPLETED.value
    assert single["result"] is not None
    assert single["error"] is None


def test_get_unknown_task_returns_404(auth_client):
    response = auth_client.get("/api/tasks/no-such-id")
    assert response.status_code == 404


def test_created_task_listing_is_ordered(auth_client, monkeypatch):
    monkeypatch.setattr(
        tasks_api.planner,
        "_orchestrator",
        FakeGateway(ready_payload()),
    )

    ids = [
        auth_client.post(
            "/api/tasks",
            json={"request": f"Prepare task number {i}"},
        ).json()["task_id"]
        for i in range(3)
    ]

    listed = auth_client.get("/api/tasks").json()
    assert [t["id"] for t in listed["tasks"]] == ids


# ============================================================
# Unknown / malformed request handling
# ============================================================

def test_empty_request_rejected_without_planning(auth_client, monkeypatch):
    gateway = FakeGateway(ready_payload())
    monkeypatch.setattr(tasks_api.planner, "_orchestrator", gateway)

    response = auth_client.post(
        "/api/tasks",
        json={"request": "   "},
    )

    assert response.status_code == 400
    # The planner was never consulted.
    assert gateway.generate_calls == []


def test_planner_fallback_on_malformed_model_output(
    auth_client, monkeypatch
):
    gateway = FakeGateway("not json at all, just chatter")
    monkeypatch.setattr(tasks_api.planner, "_orchestrator", gateway)

    response = auth_client.post(
        "/api/tasks",
        json={"request": "Summarize the quarterly report file"},
    )

    # Deterministic fallback still yields an auditable plan.
    assert response.status_code == 201
    body = response.json()
    assert body["planning"]["source"] == "FALLBACK_MALFORMED"
    assert body["planning"]["parse_ok"] is False
    assert body["planning"]["raw_response"] == (
        "not json at all, just chatter"
    )


def test_missing_request_field_rejected(auth_client):
    response = auth_client.post("/api/tasks", json={})
    assert response.status_code == 422


# ============================================================
# Authentication remains enforced
# ============================================================

def test_tasks_endpoints_require_auth(client):
    assert client.post(
        "/api/tasks",
        json={"request": "anything"},
    ).status_code == 401

    assert client.get("/api/tasks").status_code == 401
    assert client.get("/api/tasks/some-id").status_code == 401


def test_invalid_token_rejected(client):
    client.headers.update(
        {"Authorization": "Bearer not-a-real-token"}
    )
    assert client.get("/api/tasks").status_code == 401


# ============================================================
# Existing M1/M2 endpoints remain functional
# ============================================================

def test_existing_memory_endpoint_still_works(auth_client):
    response = auth_client.get("/api/memory")
    assert response.status_code == 200
    assert "memories" in response.json()


def test_health_still_public(client):
    assert client.get("/health").status_code == 200


def test_existing_chat_route_registered(auth_client):
    # Route presence (not a full chat generation): the
    # endpoint must still exist with its M2 rate limiting.
    assert auth_client.post(
        "/api/chat",
        json={"message": ""},
    ).status_code in (400, 422)


# ============================================================
# Planner is not bypassed / no tools execute
# ============================================================

def test_planner_not_bypassed(auth_client, monkeypatch):
    calls = []

    class RecordingPlanner:
        async def plan(self, request, **kwargs):
            calls.append(request)
            from backend.core.planner import PlanningResult

            return PlanningResult(
                request=request,
                ready=False,
                questions=["Fallback question?"],
            )

    monkeypatch.setattr(
        tasks_api, "planner", RecordingPlanner()
    )

    response = auth_client.post(
        "/api/tasks",
        json={"request": "do the thing"},
    )

    assert response.status_code == 200
    assert calls == ["do the thing"]  # request went through it


def test_tools_execute_through_permission_policy(
    auth_client, monkeypatch
):
    """A ready plan referencing a tool executes it through
    the Agent -> PermissionPolicy -> ToolRegistry stack: the
    policy is consulted before any tool runs."""

    from backend.permissions.policy import PermissionPolicy

    policy_calls = []

    original_evaluate = PermissionPolicy.evaluate

    def recording_evaluate(self, tool_name, task_id=None):
        policy_calls.append(tool_name)
        return original_evaluate(self, tool_name, task_id=task_id)

    monkeypatch.setattr(
        PermissionPolicy, "evaluate", recording_evaluate
    )

    gateway = FakeGateway(ready_payload())
    monkeypatch.setattr(tasks_api.planner, "_orchestrator", gateway)

    response = auth_client.post(
        "/api/tasks",
        json={"request": f"Read {README_ABS} and summarize"},
    )

    assert response.status_code == 201
    task = tasks_api.task_service.get(response.json()["task_id"])

    # The permission policy gated the planned tool before it
    # ran, and the SAFE read completed with real content.
    assert policy_calls == ["fs_read_file"]
    assert task.status == TaskStatus.COMPLETED
    assert "GHOST" in str(task.result)
    assert task.error is None

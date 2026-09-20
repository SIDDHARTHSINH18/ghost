"""
Focused tests for M3-H Step 5 — approval + resume.

Covers:
1. SAFE actions still execute normally
2. SENSITIVE actions pause and do not execute
3. Approval is required before execution
4. Explicit approval resumes the correct pending action
5. Approval causes execution THROUGH PermissionPolicy
6. Explicit denial does not execute
7. DANGEROUS actions remain denied (grants can't override)
8. Wrong/unknown task or step cannot be approved/resumed
9. Completed/non-pending tasks cannot be resumed
10. API authentication is enforced on approval endpoints
11. Existing M1/M2 behavior remains intact
12. No duplicate permission logic was introduced
"""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import backend.api.tasks as tasks_api
from backend.approval.service import (
    ApprovalDeniedError,
    ApprovalRequiredError,
    ApprovalService,
    ApprovalStatus,
)
from backend.agents.executor import Agent
from backend.automation.engine import AutomationEngine, TaskStep
from backend.core import agent_services
from backend.core.task import TaskStatus
from backend.permissions.policy import (
    PermissionDecision,
    PermissionPolicy,
)
from backend.tasks import TaskService
from backend.tasks.runner import TaskRunner
from backend.tools.registry import RiskLevel, ToolRegistry


# ============================================================
# Isolated stack builder (no production singletons touched)
# ============================================================

class SpyExecutor:
    """Records every execution; fails the test if any
    execution happens when none is expected."""

    def __init__(self):
        self.calls = []

    def __call__(self, tool_name, params):
        self.calls.append((tool_name, dict(params)))
        return f"{tool_name} output"


class CountingPolicy(PermissionPolicy):
    """Real policy that records every evaluate() call —
    proves decisions flow through the single policy."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.evaluate_calls = []

    def evaluate(self, tool_name, task_id=None):
        self.evaluate_calls.append((tool_name, task_id))
        return super().evaluate(tool_name, task_id)


def make_stack(policy=None):
    registry = ToolRegistry()
    registry.register("read_note", "Read a note", "memory", RiskLevel.SAFE)
    registry.register("send_email", "Send an email", "comms", RiskLevel.SENSITIVE)
    registry.register("delete_all", "Delete everything", "system", RiskLevel.DANGEROUS)

    approvals = ApprovalService()
    if policy is None:
        policy = PermissionPolicy(registry, approval_grants=approvals)

    executor = SpyExecutor()
    agent = Agent(
        name="approval-test-agent",
        registry=registry,
        permission_policy=policy,
        tool_executor=executor,
    )
    engine = AutomationEngine(agent)
    store = TaskService()
    runner = TaskRunner(
        task_service=store,
        automation_engine=engine,
        approvals=approvals,
    )
    return SimpleNamespace(
        registry=registry,
        approvals=approvals,
        policy=policy,
        executor=executor,
        engine=engine,
        store=store,
        runner=runner,
    )


def start_sensitive(stack, tool="send_email"):
    task = stack.store.create(title="t", description="d")
    steps = [TaskStep(tool_name=tool, params={"to": "x"}, order=0)]
    outcome = stack.runner.start(task.id, steps)
    return task, steps, outcome


# ============================================================
# 1. SAFE actions still execute normally
# ============================================================

def test_safe_action_still_executes():
    stack = make_stack()
    task = stack.store.create(title="t", description="d")
    steps = [TaskStep(tool_name="read_note", params={"p": 1}, order=0)]

    outcome = stack.runner.start(task.id, steps)

    assert outcome["state"].value == "COMPLETED"
    assert outcome["approval_id"] is None
    assert stack.executor.calls == [("read_note", {"p": 1})]
    assert task.status == TaskStatus.COMPLETED
    assert task.result == {"read_note": "read_note output"}
    # No approval machinery was involved.
    assert stack.approvals.list_pending() == []
    assert stack.approvals.list_for_task(task.id) == []


# ============================================================
# 2. SENSITIVE pauses, does not execute
# ============================================================

def test_sensitive_action_pauses_and_does_not_execute():
    stack = make_stack()
    task, steps, outcome = start_sensitive(stack)

    assert outcome["state"].value == "PAUSED"
    assert stack.executor.calls == []  # nothing executed
    assert task.status == TaskStatus.RUNNING
    assert task.result is None

    pending = stack.approvals.list_pending()
    assert len(pending) == 1
    record = pending[0]
    assert record.task_id == task.id
    assert record.tool_name == "send_email"
    assert record.step_id == steps[0].id
    assert record.status == ApprovalStatus.PENDING
    assert record.decided_at is None


# ============================================================
# 3. Approval required before execution
# ============================================================

def test_resume_without_decision_is_refused():
    stack = make_stack()
    task, steps, outcome = start_sensitive(stack)

    with pytest.raises(ApprovalRequiredError):
        stack.runner.resume(task.id)

    assert stack.executor.calls == []  # still nothing ran
    assert task.status == TaskStatus.RUNNING
    assert task.result is None


# ============================================================
# 4. Explicit approval resumes the correct pending action
# ============================================================

def test_granted_approval_resumes_correct_action():
    stack = make_stack()
    task, steps, outcome = start_sensitive(stack)
    approval_id = outcome["approval_id"]

    record = stack.approvals.decide(approval_id, approved=True)
    assert record.status == ApprovalStatus.GRANTED
    assert record.decided_at is not None

    resumed = stack.runner.resume(task.id)

    assert resumed["state"].value == "COMPLETED"
    # Exactly the paused action, with its own params.
    assert stack.executor.calls == [("send_email", {"to": "x"})]
    assert task.status == TaskStatus.COMPLETED
    assert task.result == {"send_email": "send_email output"}
    assert task.error is None
    # The grant was consumed: one-shot only.
    assert (
        stack.approvals.get(approval_id).status
        == ApprovalStatus.CONSUMED
    )


# ============================================================
# 5. Approval causes execution THROUGH PermissionPolicy
# ============================================================

def test_resume_executes_through_permission_policy():
    registry = make_stack_policy_registry()
    approvals = ApprovalService()
    policy = CountingPolicy(registry, approval_grants=approvals)

    stack = make_stack(policy=policy)
    # The stack builder made its own approvals/policy; rewire
    # the stack pieces to the counting policy's grant store.
    stack = SimpleNamespace(
        registry=registry,
        approvals=approvals,
        policy=policy,
        executor=stack.executor,
        engine=stack.engine,
        store=stack.store,
        runner=TaskRunner(
            task_service=stack.store,
            automation_engine=stack.engine,
            approvals=approvals,
        ),
    )

    task, steps, outcome = start_sensitive(stack)
    stack.approvals.decide(outcome["approval_id"], approved=True)

    stack.runner.resume(task.id)

    # The single policy was consulted during resume, with
    # the task context, and it authorized the execution.
    assert ("send_email", task.id) in stack.policy.evaluate_calls
    assert task.status == TaskStatus.COMPLETED


def make_stack_policy_registry():
    registry = ToolRegistry()
    registry.register("read_note", "Read a note", "memory", RiskLevel.SAFE)
    registry.register("send_email", "Send an email", "comms", RiskLevel.SENSITIVE)
    registry.register("delete_all", "Delete everything", "system", RiskLevel.DANGEROUS)
    return registry


def test_grant_is_one_shot_and_scoped():
    stack = make_stack()
    task, steps, outcome = start_sensitive(stack)
    stack.approvals.decide(outcome["approval_id"], approved=True)

    # First resume consumes the grant and completes.
    stack.runner.resume(task.id)
    assert task.status == TaskStatus.COMPLETED

    # A second sensitive run of the same tool for a NEW
    # task is NOT auto-approved by the old grant.
    task2, steps2, outcome2 = start_sensitive(stack, tool="send_email")
    assert outcome2["state"].value == "PAUSED"
    assert stack.executor.calls.count(("send_email", {"to": "x"})) == 1

    # And at the policy level the consumed grant is gone.
    assert (
        stack.policy.evaluate("send_email", task_id=task.id).decision
        == PermissionDecision.REQUIRE_APPROVAL
    )


# ============================================================
# 6. Explicit denial does not execute
# ============================================================

def test_denied_approval_does_not_execute():
    stack = make_stack()
    task, steps, outcome = start_sensitive(stack)

    record = stack.approvals.decide(
        outcome["approval_id"], approved=False
    )
    assert record.status == ApprovalStatus.DENIED

    with pytest.raises(ApprovalDeniedError):
        stack.runner.resume(task.id)

    assert stack.executor.calls == []
    assert task.status == TaskStatus.FAILED
    assert task.result is None


# ============================================================
# 7. DANGEROUS remains denied
# ============================================================

def test_dangerous_action_remains_denied():
    stack = make_stack()
    task = stack.store.create(title="t", description="d")
    steps = [TaskStep(tool_name="delete_all", order=0)]

    outcome = stack.runner.start(task.id, steps)

    assert outcome["state"].value == "FAILED"
    assert stack.executor.calls == []
    assert task.status == TaskStatus.FAILED
    assert "DANGEROUS" in task.error

    # Even a granted approval cannot override DENY.
    record = stack.approvals.create(
        task_id=task.id, tool_name="delete_all", step_id=steps[0].id
    )
    stack.approvals.decide(record.approval_id, approved=True)

    result = stack.policy.evaluate("delete_all", task_id=task.id)
    assert result.decision == PermissionDecision.DENY

    # And the failed task is not resumable.
    with pytest.raises(ValueError):
        stack.runner.resume(task.id)


# ============================================================
# 8. Wrong/unknown task or step cannot be approved/resumed
# ============================================================

def test_unknown_approval_and_task_fail_safely():
    stack = make_stack()

    with pytest.raises(KeyError):
        stack.approvals.decide("no-such-approval", approved=True)

    with pytest.raises(KeyError):
        stack.runner.resume("no-such-task")


def test_approval_cannot_leak_across_tasks():
    stack = make_stack()
    task_a, _, outcome_a = start_sensitive(stack)
    stack.approvals.decide(outcome_a["approval_id"], approved=True)

    # Task B (same tool) has no grant of its own.
    task_b = stack.store.create(title="b", description="d")
    steps_b = [TaskStep(tool_name="send_email", params={"to": "y"}, order=0)]
    stack.runner.start(task_b.id, steps_b)

    with pytest.raises(ApprovalRequiredError):
        stack.runner.resume(task_b.id)

    # Task A's grant was untouched by task B's attempt.
    assert len(stack.approvals.grants_for(task_a.id, "send_email")) == 1


def test_already_decided_approval_cannot_be_redecided():
    stack = make_stack()
    _, _, outcome = start_sensitive(stack)

    stack.approvals.decide(outcome["approval_id"], approved=True)

    with pytest.raises(ValueError):
        stack.approvals.decide(outcome["approval_id"], approved=False)


# ============================================================
# 9. Completed/non-pending tasks cannot be resumed
# ============================================================

def test_completed_task_cannot_be_resumed():
    stack = make_stack()
    task, steps, outcome = start_sensitive(stack)
    stack.approvals.decide(outcome["approval_id"], approved=True)
    stack.runner.resume(task.id)

    assert task.status == TaskStatus.COMPLETED
    with pytest.raises(ValueError):
        stack.runner.resume(task.id)


def test_failed_task_cannot_be_resumed():
    stack = make_stack()
    task = stack.store.create(title="t", description="d")
    stack.runner.start(task.id, [TaskStep(tool_name="delete_all", order=0)])

    assert task.status == TaskStatus.FAILED
    with pytest.raises(ValueError):
        stack.runner.resume(task.id)


def test_task_without_workflow_cannot_be_resumed():
    stack = make_stack()
    task = stack.store.create(title="t", description="d")

    with pytest.raises(ValueError):
        stack.runner.resume(task.id)


# ============================================================
# 10-11. API: authentication, endpoints, M1/M2 intact
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
            "task_title": "Email task",
            "task_description": "Send the email.",
            "steps": [],
            "assumptions": [],
            "clarifying_questions": [],
        }
    )


@pytest.fixture
def client():
    from backend.main import app

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
def isolated_flow(monkeypatch):
    """
    Fresh, fully isolated execution flow wired into the
    API module: production singletons are never mutated
    (only the tasks_api module references are redirected).
    """

    registry = ToolRegistry()
    registry.register("read_note", "Read a note", "memory", RiskLevel.SAFE)
    registry.register("send_email", "Send an email", "comms", RiskLevel.SENSITIVE)

    approvals = ApprovalService()
    policy = PermissionPolicy(registry, approval_grants=approvals)
    executor = SpyExecutor()
    agent = Agent(
        name="isolated-agent",
        registry=registry,
        permission_policy=policy,
        tool_executor=executor,
    )
    store = TaskService()
    runner = TaskRunner(
        task_service=store,
        automation_engine=AutomationEngine(agent),
        approvals=approvals,
    )

    monkeypatch.setattr(tasks_api, "task_service", store)
    monkeypatch.setattr(tasks_api, "task_runner", runner)
    monkeypatch.setattr(tasks_api, "approval_service", approvals)
    # The production policy must consume the SAME grant
    # store the API's runner checks (single source).
    monkeypatch.setattr(
        agent_services.permission_policy,
        "_approval_grants",
        approvals,
    )

    return SimpleNamespace(
        store=store,
        approvals=approvals,
        runner=runner,
        executor=executor,
        policy=policy,
    )


def _create_task(auth_client, monkeypatch):
    monkeypatch.setattr(
        tasks_api.planner,
        "_orchestrator",
        FakeGateway(ready_payload()),
    )
    response = auth_client.post(
        "/api/tasks",
        json={"request": "Send the email now"},
    )
    assert response.status_code == 201
    return response.json()["task_id"]


def test_api_endpoints_require_auth(client):
    assert client.get("/api/approvals").status_code == 401
    assert (
        client.post(
            "/api/approvals/some-id/decision",
            json={"approved": True},
        ).status_code
        == 401
    )
    assert (
        client.post("/api/tasks/some-id/resume").status_code == 401
    )


def test_api_decision_unknown_approval_404(auth_client):
    response = auth_client.post(
        "/api/approvals/no-such-id/decision",
        json={"approved": True},
    )
    assert response.status_code == 404


def test_api_approval_and_resume_end_to_end(
    auth_client, monkeypatch, isolated_flow
):
    task_id = _create_task(auth_client, monkeypatch)

    # Start the workflow (service-level): pauses on the
    # SENSITIVE step and registers an approval.
    started = isolated_flow.runner.start(
        task_id,
        [TaskStep(tool_name="send_email", params={"to": "x"}, order=0)],
    )
    assert started["state"].value == "PAUSED"
    approval_id = started["approval_id"]

    # Pending approvals visible (audit view).
    listed = auth_client.get("/api/approvals").json()
    assert listed["total"] == 1
    assert listed["approvals"][0]["approval_id"] == approval_id

    # Explicit grant via the API.
    decided = auth_client.post(
        f"/api/approvals/{approval_id}/decision",
        json={"approved": True},
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "GRANTED"

    # Resume via the API: executes through the isolated
    # policy (grant consumed) and completes.
    resumed = auth_client.post(f"/api/tasks/{task_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "COMPLETED"
    assert resumed.json()["task_status"] == "COMPLETED"

    single = auth_client.get(f"/api/tasks/{task_id}").json()
    assert single["status"] == "COMPLETED"
    assert isolated_flow.executor.calls == [("send_email", {"to": "x"})]

    # Grant consumed, workflow done: further resumes refuse.
    again = auth_client.post(f"/api/tasks/{task_id}/resume")
    assert again.status_code == 409


def test_api_denied_decision_blocks_resume(
    auth_client, monkeypatch, isolated_flow
):
    task_id = _create_task(auth_client, monkeypatch)
    started = isolated_flow.runner.start(
        task_id,
        [TaskStep(tool_name="send_email", order=0)],
    )
    approval_id = started["approval_id"]

    decided = auth_client.post(
        f"/api/approvals/{approval_id}/decision",
        json={"approved": False},
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "DENIED"
    assert isolated_flow.store.get(task_id).status == TaskStatus.FAILED

    denied = auth_client.post(f"/api/tasks/{task_id}/resume")
    assert denied.status_code == 409
    assert "denied" in denied.json()["detail"].lower()
    assert isolated_flow.executor.calls == []


def test_api_double_decision_conflict(
    auth_client, monkeypatch, isolated_flow
):
    task_id = _create_task(auth_client, monkeypatch)
    started = isolated_flow.runner.start(
        task_id,
        [TaskStep(tool_name="send_email", order=0)],
    )
    approval_id = started["approval_id"]

    first = auth_client.post(
        f"/api/approvals/{approval_id}/decision",
        json={"approved": True},
    )
    assert first.status_code == 200

    second = auth_client.post(
        f"/api/approvals/{approval_id}/decision",
        json={"approved": True},
    )
    assert second.status_code == 409


def test_api_resume_unknown_task_404(auth_client):
    response = auth_client.post("/api/tasks/no-such-id/resume")
    assert response.status_code == 404


def test_existing_memory_endpoint_still_works(auth_client):
    response = auth_client.get("/api/memory")
    assert response.status_code == 200
    assert "memories" in response.json()


# ============================================================
# 12. No duplicate permission logic
# ============================================================

def test_approval_service_is_a_record_keeper_only():
    approvals = ApprovalService()

    # It decides nothing itself: no evaluation/risk API.
    assert not hasattr(approvals, "evaluate")
    assert not hasattr(approvals, "risk_policy")
    assert not hasattr(approvals, "set_policy")

    # Unknown actions have no grants and consume nothing.
    assert approvals.consume("task-x", "tool-x") is False
    assert approvals.grants_for("task-x", "tool-x") == []


def test_policy_without_grants_is_unchanged():
    """The M3-C default path is untouched when no
    approval store is wired."""

    registry = ToolRegistry()
    registry.register("send_email", "Send", "comms", RiskLevel.SENSITIVE)
    policy = PermissionPolicy(registry)

    result = policy.evaluate("send_email", task_id="task-1")

    assert result.decision == PermissionDecision.REQUIRE_APPROVAL

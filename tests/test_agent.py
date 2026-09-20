import pytest

from backend.agents.executor import Agent, ExecutionResult
from backend.core.orchestrator import Orchestrator
from backend.core.task import Task, TaskStatus
from backend.permissions.policy import (
    PermissionDecision,
    PermissionPolicy,
)
from backend.tools.registry import RiskLevel, ToolRegistry


# ============================================================
# Deterministic mock tool execution (testing only — no real
# filesystem, shell, browser, email or other integrations).
# ============================================================

class MockToolExecutor:
    """Maps tool name -> return value or exception."""

    def __init__(self):
        self.behaviors = {}
        self.calls = []

    def set(self, tool_name, value):
        self.behaviors[tool_name] = value

    def __call__(self, tool_name, params):
        self.calls.append((tool_name, params))
        value = self.behaviors[tool_name]
        if isinstance(value, Exception):
            raise value
        return value


# ============================================================
# Shared fixture-style helpers
# ============================================================

def make_registry():
    registry = ToolRegistry()
    registry.register("read_note", "Read a note", "memory", RiskLevel.SAFE)
    registry.register("send_email", "Send an email", "comms", RiskLevel.SENSITIVE)
    registry.register("delete_all", "Delete everything", "system", RiskLevel.DANGEROUS)
    return registry


def make_agent(executor=None):
    registry = make_registry()
    return Agent(
        name="task-agent",
        registry=registry,
        permission_policy=PermissionPolicy(registry),
        tool_executor=executor if executor is not None else MockToolExecutor(),
    )


# ============================================================
# Tests
# ============================================================

def test_safe_tool_executes_automatically():
    executor = MockToolExecutor()
    executor.set("read_note", "note contents")
    agent = make_agent(executor)

    task = Task(title="Read note", description="Fetch a stored note")
    result = agent.execute(task, "read_note", {"key": "value"})

    assert result.status == TaskStatus.COMPLETED
    assert result.decision == PermissionDecision.ALLOW
    assert result.output == "note contents"
    assert result.error is None
    # Params reached the tool, permission was checked first.
    assert executor.calls == [("read_note", {"key": "value"})]


def test_safe_execution_updates_task_fields():
    executor = MockToolExecutor()
    executor.set("read_note", "note contents")
    agent = make_agent(executor)

    task = Task(title="Read note", description="d")
    result = agent.execute(task, "read_note")

    assert task.status == TaskStatus.COMPLETED
    assert task.result == "note contents"
    assert task.error is None
    assert task.updated_at >= task.created_at
    assert result.task_id == task.id


def test_sensitive_tool_requires_approval_and_does_not_execute():
    executor = MockToolExecutor()
    executor.set("send_email", "sent")
    agent = make_agent(executor)

    task = Task(title="Send email", description="d")
    result = agent.execute(task, "send_email")

    assert result.decision == PermissionDecision.REQUIRE_APPROVAL
    assert "approval" in result.reason.lower() or "SENSITIVE" in result.reason
    # Nothing ran and the task waits for the user.
    assert executor.calls == []
    assert task.status == TaskStatus.PENDING
    assert task.result is None
    assert task.error is None


def test_dangerous_tool_blocked():
    executor = MockToolExecutor()
    agent = make_agent(executor)

    task = Task(title="Delete all", description="d")
    result = agent.execute(task, "delete_all")

    assert result.decision == PermissionDecision.DENY
    assert result.status == TaskStatus.FAILED
    assert executor.calls == []
    assert task.status == TaskStatus.FAILED
    assert task.error is not None
    assert "DANGEROUS" in task.error
    assert task.result is None


def test_unknown_tool_blocked():
    executor = MockToolExecutor()
    agent = make_agent(executor)

    task = Task(title="Mystery", description="d")
    result = agent.execute(task, "nonexistent_tool")

    assert result.decision == PermissionDecision.DENY
    assert result.status == TaskStatus.FAILED
    assert executor.calls == []
    assert task.status == TaskStatus.FAILED
    assert "Unknown tool" in task.error


def test_tool_execution_failure_marks_task_failed():
    executor = MockToolExecutor()
    executor.set("read_note", RuntimeError("storage offline"))
    agent = make_agent(executor)

    task = Task(title="Read note", description="d")
    result = agent.execute(task, "read_note")

    assert result.status == TaskStatus.FAILED
    assert result.decision == PermissionDecision.ALLOW
    assert "storage offline" in result.error
    assert task.status == TaskStatus.FAILED
    assert "storage offline" in task.error
    assert task.result is None


def test_task_lifecycle_timestamps_updated():
    executor = MockToolExecutor()
    executor.set("read_note", "ok")
    agent = make_agent(executor)

    task = Task(title="Read note", description="d")
    before = task.updated_at
    agent.execute(task, "read_note")

    assert task.status == TaskStatus.COMPLETED
    assert task.updated_at >= before


def test_agent_attaches_to_existing_orchestrator():
    """
    The executor plugs into the existing core Orchestrator
    (its reserved `agents` registry) instead of creating a
    second orchestration layer.
    """
    orchestrator = Orchestrator()
    agent = make_agent()

    orchestrator.agents[agent.name] = agent

    assert orchestrator.agents["task-agent"] is agent

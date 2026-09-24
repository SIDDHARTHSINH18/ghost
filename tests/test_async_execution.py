"""
M4 step 3 — async execution seam.

The async path must be semantically identical to the proven
synchronous path: permission before execution, SAFE runs,
SENSITIVE pauses, DENIED/unknown stay denied, completed steps
are not replayed.

Tests are plain synchronous functions driving the coroutines
with asyncio.run(); nothing here runs inside a FastAPI request,
so no nested event loop is created.
"""

import asyncio

import pytest

from backend.agents.executor import Agent
from backend.automation.engine import AutomationEngine, TaskStep, WorkflowState
from backend.core.task import Task, TaskStatus
from backend.permissions.policy import PermissionDecision, PermissionPolicy
from backend.tools.registry import RiskLevel, ToolRegistry


def make_stack(tool_risk=None, approval_grants=None):
    registry = ToolRegistry()
    registry.register(
        name="safe_tool",
        description="safe",
        category="test",
        risk_level=RiskLevel.SAFE,
    )
    registry.register(
        name="sensitive_tool",
        description="sensitive",
        category="test",
        risk_level=RiskLevel.SENSITIVE,
    )
    registry.register(
        name="dangerous_tool",
        description="danger",
        category="test",
        risk_level=RiskLevel.DANGEROUS,
    )

    calls = []
    tool_risk = tool_risk or {}

    def executor(name, params):
        calls.append((name, params))
        implementation = tool_risk.get(name)
        if implementation is None:
            return f"ran:{name}"
        return implementation(params)

    # Same wiring as production agent_services: the policy can
    # consume one-shot approval grants, or a granted resume would
    # never be allowed to run.
    policy = PermissionPolicy(registry, approval_grants=approval_grants)
    agent = Agent(
        name="test-agent",
        registry=registry,
        permission_policy=policy,
        tool_executor=executor,
    )
    return registry, policy, agent, calls


# --------------------------------------------------------
# AGENT.execute_async
# --------------------------------------------------------

def test_execute_async_runs_allowed_tool():
    _, _, agent, calls = make_stack()
    task = Task(title="t", description="d")

    result = asyncio.run(
        agent.execute_async(task, "safe_tool", {"a": 1})
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.output == "ran:safe_tool"
    assert task.status == TaskStatus.COMPLETED
    assert calls == [("safe_tool", {"a": 1})]


def test_execute_async_awaits_async_tool_result():
    async def slow_model(params):
        await asyncio.sleep(0)
        return {"text": "generated"}

    _, _, agent, _ = make_stack(tool_risk={"safe_tool": slow_model})
    task = Task(title="t", description="d")

    result = asyncio.run(agent.execute_async(task, "safe_tool", {}))

    assert result.output == {"text": "generated"}
    assert task.result == {"text": "generated"}


def test_sync_execute_refuses_async_tool_instead_of_storing_coroutine():
    async def slow_model(params):
        return "never"

    _, _, agent, _ = make_stack(tool_risk={"safe_tool": slow_model})
    task = Task(title="t", description="d")

    result = agent.execute(task, "safe_tool", {})

    assert result.status == TaskStatus.FAILED
    assert "execute_async" in result.error
    assert task.result is None


def test_execute_async_requires_approval_without_running():
    _, _, agent, calls = make_stack()
    task = Task(title="t", description="d")

    result = asyncio.run(agent.execute_async(task, "sensitive_tool", {}))

    assert result.decision == PermissionDecision.REQUIRE_APPROVAL
    assert calls == []
    assert task.status == TaskStatus.PENDING


def test_execute_async_denies_dangerous_tool():
    _, _, agent, calls = make_stack()
    task = Task(title="t", description="d")

    result = asyncio.run(agent.execute_async(task, "dangerous_tool", {}))

    assert result.decision == PermissionDecision.DENY
    assert calls == []
    assert task.status == TaskStatus.FAILED


def test_execute_async_denies_unknown_tool():
    _, _, agent, calls = make_stack()
    task = Task(title="t", description="d")

    result = asyncio.run(agent.execute_async(task, "nope", {}))

    assert result.decision == PermissionDecision.DENY
    assert calls == []


def test_execute_async_captures_tool_error_without_traceback():
    def explode(params):
        raise RuntimeError("secret upstream body")

    _, _, agent, _ = make_stack(tool_risk={"safe_tool": explode})
    task = Task(title="t", description="d")

    result = asyncio.run(agent.execute_async(task, "safe_tool", {}))

    assert result.status == TaskStatus.FAILED
    assert result.error.startswith("RuntimeError:")
    assert "Traceback" not in result.error


def test_permission_is_evaluated_before_any_tool_call():
    evaluated = []

    registry, _, agent, calls = make_stack()

    class RecordingPolicy(PermissionPolicy):
        def evaluate(self, tool_name, task_id=None):
            evaluated.append(tool_name)
            return super().evaluate(tool_name, task_id=task_id)

    agent._permissions = RecordingPolicy(registry)
    task = Task(title="t", description="d")

    asyncio.run(agent.execute_async(task, "dangerous_tool", {}))

    assert evaluated == ["dangerous_tool"]
    assert calls == []


# --------------------------------------------------------
# AUTOMATION ENGINE run_async
# --------------------------------------------------------

def test_run_async_executes_in_order():
    _, _, agent, calls = make_stack()
    engine = AutomationEngine(agent)
    task = Task(title="t", description="d")

    steps = [
        TaskStep(tool_name="safe_tool", order=1, title="second"),
        TaskStep(tool_name="safe_tool", order=0, title="first"),
    ]

    result = asyncio.run(engine.run_async(task, steps))

    assert result.state == WorkflowState.COMPLETED
    assert len(calls) == 2
    assert [step.status for step in result.steps] == [
        TaskStatus.COMPLETED,
        TaskStatus.COMPLETED,
    ]


def test_run_async_pauses_on_sensitive_step():
    _, _, agent, calls = make_stack()
    engine = AutomationEngine(agent)
    task = Task(title="t", description="d")

    steps = [
        TaskStep(tool_name="safe_tool", order=0),
        TaskStep(tool_name="sensitive_tool", order=1),
        TaskStep(tool_name="safe_tool", order=2),
    ]

    result = asyncio.run(engine.run_async(task, steps))

    assert result.state == WorkflowState.PAUSED
    # The step after the paused one never ran.
    assert len(calls) == 1
    assert steps[1].status == TaskStatus.PENDING
    assert steps[2].status == TaskStatus.PENDING


def test_run_async_stops_at_denied_step():
    _, _, agent, calls = make_stack()
    engine = AutomationEngine(agent)
    task = Task(title="t", description="d")

    steps = [
        TaskStep(tool_name="dangerous_tool", order=0),
        TaskStep(tool_name="safe_tool", order=1),
    ]

    result = asyncio.run(engine.run_async(task, steps))

    assert result.state == WorkflowState.FAILED
    assert len(calls) == 0
    assert task.status == TaskStatus.FAILED


def test_run_async_matches_sync_run_outcomes():
    """Both paths must agree on the same workflow."""

    def build():
        _, _, agent, _ = make_stack()
        return agent

    steps_sync = [
        TaskStep(tool_name="safe_tool", order=0),
        TaskStep(tool_name="safe_tool", order=1),
    ]
    steps_async = [
        TaskStep(tool_name="safe_tool", order=0),
        TaskStep(tool_name="safe_tool", order=1),
    ]

    task_sync = Task(title="t", description="d")
    task_async = Task(title="t", description="d")

    sync_result = AutomationEngine(build()).run(task_sync, steps_sync)

    async_result = asyncio.run(
        AutomationEngine(build()).run_async(task_async, steps_async)
    )

    assert sync_result.state == async_result.state
    assert task_sync.status == task_async.status
    assert task_sync.result == task_async.result


# --------------------------------------------------------
# TASK RUNNER async start / resume
# --------------------------------------------------------

def make_runner():
    from backend.approval.service import ApprovalService
    from backend.tasks.runner import TaskRunner
    from backend.tasks.service import TaskService

    approvals = ApprovalService()
    registry, policy, agent, calls = make_stack(approval_grants=approvals)
    tasks = TaskService()
    runner = TaskRunner(
        task_service=tasks,
        automation_engine=AutomationEngine(agent),
        approvals=approvals,
    )
    return tasks, approvals, runner, calls


def test_start_async_pauses_and_creates_approval_record():
    tasks, approvals, runner, calls = make_runner()
    task = tasks.create(title="t", description="d")

    outcome = asyncio.run(
        runner.start_async(
            task.id,
            [TaskStep(tool_name="sensitive_tool", order=0)],
        )
    )

    assert outcome["state"] == WorkflowState.PAUSED
    assert outcome["approval_id"]
    assert calls == []


def test_start_async_rejects_non_pending_task():
    tasks, _, runner, _ = make_runner()
    task = tasks.create(title="t", description="d")
    task.status = TaskStatus.COMPLETED

    with pytest.raises(ValueError):
        asyncio.run(runner.start_async(task.id, [TaskStep("safe_tool")]))


def test_start_async_rejects_empty_steps():
    tasks, _, runner, _ = make_runner()
    task = tasks.create(title="t", description="d")

    with pytest.raises(ValueError):
        asyncio.run(runner.start_async(task.id, []))


def test_resume_async_requires_granted_approval():
    from backend.approval.service import ApprovalRequiredError

    tasks, approvals, runner, calls = make_runner()
    task = tasks.create(title="t", description="d")

    asyncio.run(
        runner.start_async(
            task.id,
            [TaskStep(tool_name="sensitive_tool", order=0)],
        )
    )

    with pytest.raises(ApprovalRequiredError):
        asyncio.run(runner.resume_async(task.id))

    assert calls == []


def test_resume_async_completes_after_grant_and_skips_done_steps():
    tasks, approvals, runner, calls = make_runner()
    task = tasks.create(title="t", description="d")

    asyncio.run(
        runner.start_async(
            task.id,
            [
                TaskStep(tool_name="safe_tool", order=0),
                TaskStep(tool_name="sensitive_tool", order=1),
            ],
        )
    )

    pending = approvals.list_pending()[0]
    approvals.decide(pending.approval_id, approved=True)
    calls.clear()

    outcome = asyncio.run(runner.resume_async(task.id))

    assert outcome["state"] == WorkflowState.COMPLETED
    # Only the paused step re-ran; the completed step did not.
    assert calls == [("sensitive_tool", {})]


def test_sync_resume_still_works_after_shared_gate_refactor():
    tasks, approvals, runner, calls = make_runner()
    task = tasks.create(title="t", description="d")

    runner.start(
        task.id,
        [TaskStep(tool_name="sensitive_tool", order=0)],
    )

    pending = approvals.list_pending()[0]
    approvals.decide(pending.approval_id, approved=True)

    outcome = runner.resume(task.id)

    assert outcome["state"] == WorkflowState.COMPLETED
    assert calls == [("sensitive_tool", {})]

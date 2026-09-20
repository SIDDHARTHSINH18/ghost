"""Focused M3-H7 tests for live post-workflow reflection."""

from types import SimpleNamespace

import pytest

from backend.agents.executor import Agent
from backend.approval.service import (
    ApprovalDeniedError,
    ApprovalService,
    ApprovalStatus,
)
from backend.automation.engine import AutomationEngine, TaskStep, WorkflowState
from backend.core.task import Task, TaskStatus
from backend.permissions.policy import PermissionPolicy
from backend.reflection.engine import ReflectionEngine
from backend.reflection.result import ReflectionOutcome
from backend.tasks.runner import TaskRunner
from backend.tasks.service import TaskService
from backend.tools.builtin.fs import fs_file_exists, fs_list_directory
from backend.tools.registry import RiskLevel, ToolRegistry


class SpyExecutor:
    def __init__(self, failures=None):
        self.calls = []
        self.failures = set(failures or [])

    def __call__(self, tool_name, params):
        self.calls.append((tool_name, dict(params)))
        if tool_name in self.failures:
            raise RuntimeError(f"{tool_name} failed")
        return f"{tool_name} output"


class TrackingReflectionEngine(ReflectionEngine):
    def __init__(self):
        self.calls = []

    def reflect_on_task(self, task, **kwargs):
        self.calls.append((task, kwargs))
        return super().reflect_on_task(task, **kwargs)


def make_stack(*, failures=None):
    registry = ToolRegistry()
    registry.register("first", "First", "test", RiskLevel.SAFE)
    registry.register("second", "Second", "test", RiskLevel.SAFE)
    registry.register("broken", "Broken", "test", RiskLevel.SAFE)
    registry.register("sensitive", "Sensitive", "test", RiskLevel.SENSITIVE)
    registry.register("dangerous", "Dangerous", "test", RiskLevel.DANGEROUS)
    approvals = ApprovalService()
    policy = PermissionPolicy(registry, approval_grants=approvals)
    executor = SpyExecutor(failures=failures)
    reflection = TrackingReflectionEngine()
    store = TaskService()
    runner = TaskRunner(
        task_service=store,
        automation_engine=AutomationEngine(
            Agent("test", registry, policy, executor)
        ),
        approvals=approvals,
        reflection_engine=reflection,
    )
    return SimpleNamespace(
        approvals=approvals,
        executor=executor,
        reflection=reflection,
        runner=runner,
        store=store,
    )


def start(stack, steps):
    task = stack.store.create("Task", "d")
    return task, stack.runner.start(task.id, steps)


def test_successful_workflow_reflects_succeeded_from_real_artifacts():
    stack = make_stack()
    task, outcome = start(stack, [TaskStep("first")])

    assert outcome["reflection"]["outcome"] == "SUCCEEDED"
    assert task.reflection.outcome is ReflectionOutcome.SUCCEEDED
    reflected_task, kwargs = stack.reflection.calls[-1]
    assert reflected_task is task
    assert kwargs["automation_result"].state is WorkflowState.COMPLETED
    assert kwargs["automation_result"].steps[0].result == "first output"


def test_failed_and_denied_workflows_reflect_real_outcomes():
    failed_stack = make_stack(failures={"broken"})
    failed_task, failed = start(failed_stack, [TaskStep("broken")])
    assert failed_task.status is TaskStatus.FAILED
    assert failed["reflection"]["outcome"] == "FAILED"
    assert failed_task.reflection.failures[0].detail == "RuntimeError: broken failed"

    denied_stack = make_stack()
    denied_task, denied = start(denied_stack, [TaskStep("dangerous")])
    assert denied_task.status is TaskStatus.FAILED
    assert denied["reflection"]["outcome"] == "DENIED"
    assert denied_stack.executor.calls == []


def test_paused_and_partial_workflows_reflect_real_outcomes():
    paused_stack = make_stack()
    paused_task, paused = start(paused_stack, [TaskStep("sensitive")])
    assert paused_task.status is TaskStatus.RUNNING
    assert paused["reflection"]["outcome"] == "AWAITING_APPROVAL"
    assert paused_stack.executor.calls == []

    partial_stack = make_stack(failures={"broken"})
    partial_task, partial = start(
        partial_stack,
        [TaskStep("first", order=0), TaskStep("broken", order=1)],
    )
    assert partial_task.status is TaskStatus.FAILED
    assert partial["reflection"]["outcome"] == "PARTIAL"


def test_insufficient_evidence_remains_unknown():
    task = Task(title="No evidence", description="d")

    result = ReflectionEngine().reflect_on_task(task)

    assert result.outcome is ReflectionOutcome.UNKNOWN


def test_reflection_executes_no_tools_and_writes_no_memory():
    stack = make_stack()
    task, outcome = start(stack, [TaskStep("first")])

    assert stack.executor.calls == [("first", {})]
    assert not hasattr(stack.reflection, "execute")
    assert not hasattr(stack.reflection, "memory")
    assert task.result == {"first": "first output"}
    assert outcome["reflection"]["memory_write_recommended"] is False


def test_approval_resume_still_works_and_refreshes_reflection():
    stack = make_stack()
    task, paused = start(stack, [TaskStep("sensitive")])
    approval_id = paused["approval_id"]
    assert paused["reflection"]["outcome"] == "AWAITING_APPROVAL"

    stack.approvals.decide(approval_id, approved=True)
    resumed = stack.runner.resume(task.id)

    assert resumed["reflection"]["outcome"] == "SUCCEEDED"
    assert task.reflection.outcome is ReflectionOutcome.SUCCEEDED
    assert stack.approvals.get(approval_id).status is ApprovalStatus.CONSUMED
    assert stack.executor.calls == [("sensitive", {})]


def test_safe_then_sensitive_step_pauses_and_resumes_without_replaying_safe_step():
    stack = make_stack()
    steps = [TaskStep("first", order=0), TaskStep("sensitive", order=1)]
    task, paused = start(stack, steps)

    assert paused["state"] is WorkflowState.PAUSED
    assert task.status is TaskStatus.RUNNING
    assert steps[0].status is TaskStatus.COMPLETED
    assert steps[1].status is TaskStatus.PENDING
    assert stack.executor.calls == [("first", {})]

    approval_id = paused["approval_id"]
    stack.approvals.decide(approval_id, approved=True)
    resumed = stack.runner.resume(task.id)

    assert resumed["state"] is WorkflowState.COMPLETED
    assert task.status is TaskStatus.COMPLETED
    assert stack.approvals.get(approval_id).status is ApprovalStatus.CONSUMED
    assert resumed["reflection"]["outcome"] == "SUCCEEDED"
    assert task.reflection.outcome is ReflectionOutcome.SUCCEEDED
    assert stack.executor.calls == [("first", {}), ("sensitive", {})]


def test_human_denial_terminalizes_workflow_and_reflects_denied():
    stack = make_stack()
    task, paused = start(stack, [TaskStep("sensitive")])
    approval_id = paused["approval_id"]

    assert stack.approvals.get(approval_id).status is ApprovalStatus.PENDING
    stack.approvals.decide(approval_id, approved=False)
    terminal = stack.runner.finalize_denied_approval(approval_id)

    assert terminal["state"] is WorkflowState.FAILED
    assert task.status is TaskStatus.FAILED
    assert task.reflection.outcome is ReflectionOutcome.DENIED
    assert stack.executor.calls == []
    with pytest.raises(ApprovalDeniedError):
        stack.runner.resume(task.id)


def test_h6_filesystem_tools_remain_available(tmp_path):
    file_path = tmp_path / "present.txt"
    file_path.write_text("present", encoding="utf-8")

    assert fs_file_exists({"path": str(file_path)}) is True
    assert fs_list_directory({"path": str(tmp_path)}) == ["present.txt"]

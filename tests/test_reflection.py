import json
from dataclasses import asdict

from backend.agents.executor import ExecutionResult
from backend.automation.engine import (
    AutomationResult,
    TaskStep,
    WorkflowState,
)
from backend.core.task import Task, TaskStatus
from backend.permissions.policy import PermissionDecision
from backend.reflection import (
    ReflectionEngine,
    ReflectionFailure,
    ReflectionOutcome,
    ReflectionResult,
)
from backend.skills.skill import SkillResult
from backend.tools.registry import RiskLevel, ToolRegistry


# ============================================================
# Helpers — constructed artifacts only, no real services.
# ============================================================

def make_step(tool_name, order, status, error=None):
    step = TaskStep(tool_name=tool_name, order=order)
    step.status = status
    step.error = error
    return step


def make_automation(state, steps, reason=""):
    return AutomationResult(
        task_id="task-1",
        state=state,
        steps=steps,
        reason=reason,
    )


def make_execution(
    status=TaskStatus.FAILED,
    decision=None,
    reason="",
    error=None,
    output=None,
):
    return ExecutionResult(
        task_id="task-1",
        status=status,
        decision=decision,
        reason=reason,
        output=output,
        error=error,
    )


def snapshot_task(task: Task) -> dict:
    return {
        "id": task.id,
        "status": task.status,
        "result": task.result,
        "error": task.error,
        "updated_at": task.updated_at,
    }


# ============================================================
# Outcome classification
# ============================================================

def test_successful_task_reflection():
    task = Task(title="Pipeline", description="d")
    task.status = TaskStatus.COMPLETED
    steps = [
        make_step("read_note", 0, TaskStatus.COMPLETED),
        make_step("summarize", 1, TaskStatus.COMPLETED),
    ]
    result = ReflectionEngine().reflect_on_task(
        task,
        automation_result=make_automation(WorkflowState.COMPLETED, steps),
    )

    assert result.task_id == task.id
    assert result.outcome == ReflectionOutcome.SUCCEEDED
    assert result.succeeded is True
    assert result.failures == []
    assert result.causes == []
    assert result.lessons == []
    assert result.confidence == 1.0
    assert "all 2 step(s)" in result.summary
    assert result.memory_write_recommended is False


def test_failed_task_reflection():
    task = Task(title="Pipeline", description="d")
    task.status = TaskStatus.FAILED
    task.error = "RuntimeError: boom"
    result = ReflectionEngine().reflect_on_task(
        task,
        execution_result=make_execution(
            decision=PermissionDecision.ALLOW,
            reason="Tool 'x' is SAFE: ALLOW.",
            error="RuntimeError: boom",
        ),
    )

    assert result.outcome == ReflectionOutcome.FAILED
    assert result.succeeded is False
    assert len(result.failures) == 1
    failure = result.failures[0]
    assert failure.kind == "tool_error"
    assert failure.detail == "RuntimeError: boom"
    assert "RuntimeError: boom" in result.summary
    assert result.memory_write_recommended is True


def test_partial_workflow_reflection():
    task = Task(title="Pipeline", description="d")
    task.status = TaskStatus.FAILED
    task.error = "ValueError: bad input"
    steps = [
        make_step("read_note", 0, TaskStatus.COMPLETED),
        make_step("summarize", 1, TaskStatus.FAILED, error="ValueError: bad input"),
        make_step("format_note", 2, TaskStatus.PENDING),
    ]
    result = ReflectionEngine().reflect_on_task(
        task,
        automation_result=make_automation(WorkflowState.FAILED, steps),
    )

    assert result.outcome == ReflectionOutcome.PARTIAL
    assert result.succeeded is False
    assert len(result.failures) == 1
    assert result.failures[0].tool_name == "summarize"
    assert result.failures[0].step_id == steps[1].id
    assert "1 of 3 step(s)" in result.summary
    assert any("Re-run the remaining steps" in lesson for lesson in result.lessons)


def test_permission_denial_reflection():
    task = Task(title="Delete", description="d")
    task.status = TaskStatus.FAILED
    denial_reason = "Tool 'delete_all' is DANGEROUS: DENY."
    task.error = denial_reason
    result = ReflectionEngine().reflect_on_task(
        task,
        execution_result=make_execution(
            decision=PermissionDecision.DENY,
            reason=denial_reason,
            error=denial_reason,
        ),
    )

    assert result.outcome == ReflectionOutcome.DENIED
    assert result.succeeded is False
    assert result.failures[0].kind == "permission_denial"
    # Reason preserved verbatim — never reinterpreted.
    assert result.failures[0].detail == denial_reason
    assert any("Do not retry automatically" in lesson for lesson in result.lessons)
    assert result.memory_write_recommended is True


def test_unknown_tool_denial_via_step_error():
    task = Task(title="Mystery", description="d")
    task.status = TaskStatus.FAILED
    task.error = "Unknown tool 'nonexistent'."
    steps = [make_step("nonexistent", 0, TaskStatus.FAILED, error="Unknown tool 'nonexistent'.")]
    result = ReflectionEngine().reflect_on_task(
        task,
        automation_result=make_automation(WorkflowState.FAILED, steps),
    )

    assert result.outcome == ReflectionOutcome.DENIED
    assert result.failures[0].kind == "permission_denial"
    assert any("Register or correct the tool" in lesson for lesson in result.lessons)


def test_approval_required_pause_reflection():
    task = Task(title="Email", description="d")
    task.status = TaskStatus.RUNNING
    steps = [
        make_step("send_email", 0, TaskStatus.PENDING),
        make_step("summarize", 1, TaskStatus.PENDING),
    ]
    result = ReflectionEngine().reflect_on_task(
        task,
        automation_result=make_automation(
            WorkflowState.PAUSED,
            steps,
            reason="Tool 'send_email' is SENSITIVE: REQUIRE_APPROVAL.",
        ),
    )

    assert result.outcome == ReflectionOutcome.AWAITING_APPROVAL
    assert result.succeeded is False
    assert result.failures == []
    assert "awaiting user approval" in result.summary
    assert "approve" in result.recommended_next_action.lower()
    assert result.memory_write_recommended is False


def test_tool_failure_reflection():
    task = Task(title="Read", description="d")
    task.status = TaskStatus.FAILED
    task.error = "RuntimeError: storage offline"
    steps = [
        make_step("read_note", 0, TaskStatus.FAILED, error="RuntimeError: storage offline"),
    ]
    result = ReflectionEngine().reflect_on_task(
        task,
        automation_result=make_automation(WorkflowState.FAILED, steps),
    )

    assert result.outcome == ReflectionOutcome.FAILED
    assert result.failures[0].kind == "tool_error"
    assert result.failures[0].detail == "RuntimeError: storage offline"
    assert any("Address the tool failure" in lesson for lesson in result.lessons)


def test_unknown_failure_reflection():
    task = Task(title="Mystery", description="d")
    # PENDING task with no execution artifacts at all.
    result = ReflectionEngine().reflect_on_task(task)

    assert result.outcome == ReflectionOutcome.UNKNOWN
    assert result.succeeded is False
    assert result.failures == []
    assert result.confidence == 0.3
    assert result.memory_write_recommended is False
    assert "could not be determined" in result.summary


def test_agent_level_reflection():
    task = Task(title="Read", description="d")
    task.status = TaskStatus.COMPLETED
    result = ReflectionEngine().reflect_on_task(
        task,
        execution_result=make_execution(
            status=TaskStatus.COMPLETED,
            decision=PermissionDecision.ALLOW,
            reason="Tool 'read_note' is SAFE: ALLOW.",
            output="note contents",
        ),
    )

    assert result.outcome == ReflectionOutcome.SUCCEEDED
    assert result.succeeded is True
    assert "completed successfully" in result.summary


def test_skill_level_reflection_success():
    task = Task(title="Recall", description="d")
    task.status = TaskStatus.COMPLETED
    result = ReflectionEngine().reflect_on_task(
        task,
        skill_result=SkillResult(
            skill_name="memory-recall",
            status=TaskStatus.COMPLETED,
            output=["fact one"],
        ),
    )

    assert result.outcome == ReflectionOutcome.SUCCEEDED
    assert result.succeeded is True


def test_skill_level_reflection_paused():
    task = Task(title="Email", description="d")
    task.status = TaskStatus.RUNNING
    result = ReflectionEngine().reflect_on_task(
        task,
        skill_result=SkillResult(
            skill_name="note-summarizer",
            status=TaskStatus.PENDING,
        ),
    )

    assert result.outcome == ReflectionOutcome.AWAITING_APPROVAL
    assert result.memory_write_recommended is False


def test_skill_level_reflection_failure():
    task = Task(title="s", description="d")
    task.status = TaskStatus.FAILED
    task.error = "skill failed"
    result = ReflectionEngine().reflect_on_task(
        task,
        skill_result=SkillResult(
            skill_name="note-summarizer",
            status=TaskStatus.FAILED,
            error="note-summarizer requires a 'text' parameter.",
        ),
    )

    assert result.outcome == ReflectionOutcome.FAILED
    assert result.failures[0].kind == "skill_error"
    assert "note-summarizer requires" in result.failures[0].detail


# ============================================================
# Determinism, side effects, serialization
# ============================================================

def test_reflection_is_deterministic():
    task = Task(title="Pipeline", description="d")
    task.status = TaskStatus.FAILED
    task.error = "RuntimeError: boom"
    steps = [
        make_step("read_note", 0, TaskStatus.COMPLETED),
        make_step("summarize", 1, TaskStatus.FAILED, error="RuntimeError: boom"),
    ]
    automation = make_automation(WorkflowState.FAILED, steps)
    execution = make_execution(decision=PermissionDecision.ALLOW)

    first = ReflectionEngine().reflect_on_task(task, automation, execution)
    second = ReflectionEngine().reflect_on_task(task, automation, execution)

    assert asdict(first) == asdict(second)


def test_reflection_has_no_side_effects_on_task():
    task = Task(title="Pipeline", description="d")
    task.status = TaskStatus.FAILED
    task.error = "RuntimeError: boom"
    before = snapshot_task(task)
    steps = [make_step("read_note", 0, TaskStatus.FAILED, error="RuntimeError: boom")]

    ReflectionEngine().reflect_on_task(
        task,
        automation_result=make_automation(WorkflowState.FAILED, steps),
    )

    assert snapshot_task(task) == before
    assert steps[0].status == TaskStatus.FAILED
    assert steps[0].error == "RuntimeError: boom"


def test_unexecuted_task_guard():
    task = Task(title="Nothing yet", description="d")
    result = ReflectionEngine().reflect_on_task(task)

    assert result.outcome == ReflectionOutcome.UNKNOWN
    assert result.confidence == 0.3
    assert result.recommended_next_action.startswith("Investigate")
    assert result.memory_write_recommended is False


# ============================================================
# Memory recommendation behavior
# ============================================================

def test_memory_recommendation_matrix():
    engine = ReflectionEngine()

    failed_task = Task(title="a", description="d")
    failed_task.status = TaskStatus.FAILED
    failed_task.error = "RuntimeError: x"
    assert engine.reflect_on_task(
        failed_task,
        execution_result=make_execution(error="RuntimeError: x"),
    ).memory_write_recommended is True

    denied_task = Task(title="b", description="d")
    denied_task.status = TaskStatus.FAILED
    assert engine.reflect_on_task(
        denied_task,
        execution_result=make_execution(
            decision=PermissionDecision.DENY,
            reason="Tool 'x' is DANGEROUS: DENY.",
        ),
    ).memory_write_recommended is True

    paused_task = Task(title="c", description="d")
    paused_task.status = TaskStatus.RUNNING
    assert engine.reflect_on_task(
        paused_task,
        automation_result=make_automation(WorkflowState.PAUSED, []),
    ).memory_write_recommended is False

    ok_task = Task(title="e", description="d")
    ok_task.status = TaskStatus.COMPLETED
    assert engine.reflect_on_task(ok_task).memory_write_recommended is False

    unknown_task = Task(title="f", description="d")
    assert engine.reflect_on_task(unknown_task).memory_write_recommended is False


# ============================================================
# Serialization
# ============================================================

def test_json_serialization_round_trip():
    task = Task(title="Pipeline", description="d")
    task.status = TaskStatus.FAILED
    task.error = "RuntimeError: boom"
    steps = [make_step("read_note", 0, TaskStatus.FAILED, error="RuntimeError: boom")]
    result = ReflectionEngine().reflect_on_task(
        task,
        automation_result=make_automation(WorkflowState.FAILED, steps),
    )

    as_dict = result.to_dict()
    assert as_dict["outcome"] == "FAILED"
    assert as_dict["failures"][0]["kind"] == "tool_error"

    payload = json.dumps(result.to_dict())
    restored = json.loads(payload)
    assert restored["task_id"] == task.id
    assert restored["outcome"] == "FAILED"
    assert restored["confidence"] == result.confidence

    # dataclasses.asdict works directly too.
    assert asdict(result)["outcome"] == ReflectionOutcome.FAILED


# ============================================================
# Security: no tool execution, no permission bypass
# ============================================================

class CountingExecutor:
    """Fails the test if anything ever executes."""

    def __init__(self):
        self.calls = []

    def __call__(self, tool_name, params):
        self.calls.append((tool_name, params))
        raise AssertionError("ReflectionEngine must never execute tools")


def test_reflection_never_executes_tools_or_bypasses_permissions():
    # A live agent stack exists, but reflection receives none
    # of it — only finished artifacts.
    executor = CountingExecutor()
    registry = ToolRegistry()
    registry.register("read_note", "Read a note", "memory", RiskLevel.SAFE)
    registry.register("delete_all", "Delete", "system", RiskLevel.DANGEROUS)

    from backend.agents.executor import Agent
    from backend.permissions.policy import PermissionPolicy

    agent = Agent(
        name="agent",
        registry=registry,
        permission_policy=PermissionPolicy(registry),
        tool_executor=executor,
    )

    task = Task(title="Delete", description="d")
    task.status = TaskStatus.FAILED
    denial_reason = "Tool 'delete_all' is DANGEROUS: DENY."
    task.error = denial_reason

    engine = ReflectionEngine()
    result = engine.reflect_on_task(
        task,
        execution_result=make_execution(
            decision=PermissionDecision.DENY,
            reason=denial_reason,
            error=denial_reason,
        ),
    )

    # Nothing executed, nothing bypassed, reason verbatim.
    assert executor.calls == []
    assert result.outcome == ReflectionOutcome.DENIED
    assert result.failures[0].detail == denial_reason

    # The engine holds no security-sensitive references.
    assert not hasattr(engine, "_registry")
    assert not hasattr(engine, "_policy")
    assert not hasattr(engine, "_agent")
    assert not hasattr(engine, "_memory")

"""
GHOST — foundational automation engine (M3-E).

Runs a Task through an ordered list of steps, where every
step executes a tool through the existing M3-D agent:

  Task -> AutomationEngine -> ordered TaskSteps
       -> Agent -> PermissionPolicy -> ToolRegistry
       -> execution result -> next step / pause / failure

Rules:
- Steps run strictly sequentially in `order` — deterministic
  and synchronous.
- Permission checking is NOT duplicated here: each step
  goes through Agent.execute, which consults the shared
  PermissionPolicy before any tool runs.
- A successful step advances to the next one.
- A step requiring approval PAUSES the workflow (not a
  failure); the step stays PENDING for a later approval
  step to resume.
- A denied or failed step stops the workflow and records
  the failure on the step and the task.
- All steps succeeding marks the Task COMPLETED.

This is not a second orchestrator: model-level
orchestration remains in core.orchestrator; the engine is
a task-level runner that reuses the Agent executor.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from backend.agents.executor import Agent, ExecutionResult
from backend.core.task import Task, TaskStatus
from backend.permissions.policy import PermissionDecision


class TaskStep:
    """
    One ordered unit of work inside a Task.

    Status reuses TaskStatus — one status vocabulary for
    tasks and steps, no second state model.
    """

    def __init__(
        self,
        tool_name: str,
        params: Optional[dict] = None,
        order: int = 0,
        title: str = "",
    ):
        self.id: str = str(uuid4())
        self.order: int = order
        self.title: str = title or tool_name
        self.tool_name: str = tool_name
        self.params: dict = dict(params or {})
        self.status: TaskStatus = TaskStatus.PENDING
        self.result: Any = None
        self.error: Optional[str] = None

    def __repr__(self) -> str:
        return (
            f"TaskStep(id={self.id!r}, order={self.order}, "
            f"tool={self.tool_name!r}, status={self.status.value})"
        )


class WorkflowState(Enum):
    """Outcome of one automation run over a full step list."""

    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    # The plan contained no executable steps. Nothing ran, so
    # the workflow did not succeed: the task must not be
    # terminalized as COMPLETED by an empty loop.
    NO_STEPS = "NO_STEPS"


@dataclass
class AutomationResult:
    task_id: str
    state: WorkflowState
    steps: list = field(default_factory=list)
    reason: str = ""
    # Set only when a paused workflow is terminalized by an
    # explicit human denial in TaskRunner. This is an audit
    # artifact, not a new workflow state.
    approval_denied: bool = False


class AutomationEngine:
    """
    Executes a Task's steps sequentially through the
    shared Agent executor.
    """

    def __init__(self, agent: Agent):
        self._agent = agent

    def run(
        self,
        task: Task,
        steps: list,
    ) -> AutomationResult:
        """
        Run all steps in order. The task's status/result/
        error fields reflect the final workflow outcome.
        """

        ordered = sorted(steps, key=lambda step: step.order)

        if not ordered:
            # An empty plan executed nothing. Leave the task in
            # its pre-run (PENDING) state — a zero-iteration
            # loop is not a successful run.
            return AutomationResult(
                task_id=task.id,
                state=WorkflowState.NO_STEPS,
                steps=[],
                reason="plan contained no executable steps",
            )

        task.status = TaskStatus.RUNNING

        for step in ordered:

            # Agent.execute() correctly marks an individual
            # successful tool call COMPLETED. A workflow may
            # still have later steps, though, so restore the
            # workflow-level task status before each next step.
            # In particular, a following SENSITIVE step must
            # pause a resumable RUNNING task, not a COMPLETED one.
            task.status = TaskStatus.RUNNING

            result = self._agent.execute(
                task,
                step.tool_name,
                step.params,
            )

            self._sync_step(step, result)

            if result.decision == PermissionDecision.REQUIRE_APPROVAL:
                # Waiting on the user — not a failure. The
                # step stays PENDING so it can be resumed.
                return AutomationResult(
                    task_id=task.id,
                    state=WorkflowState.PAUSED,
                    steps=ordered,
                    reason=result.reason,
                )

            if result.status == TaskStatus.FAILED:
                task.status = TaskStatus.FAILED
                task.error = result.error or result.reason
                return AutomationResult(
                    task_id=task.id,
                    state=WorkflowState.FAILED,
                    steps=ordered,
                    reason=task.error,
                )

        # Every step completed.
        task.status = TaskStatus.COMPLETED
        task.result = {
            step.tool_name: step.result for step in ordered
        }
        task.error = None
        return AutomationResult(
            task_id=task.id,
            state=WorkflowState.COMPLETED,
            steps=ordered,
        )

    async def run_async(
        self,
        task: Task,
        steps: list,
    ) -> AutomationResult:
        """
        Async twin of run() (M4 step 3), for workflows whose
        steps need the model gateway.

        Sequential order, permission-gated execution, pause on
        REQUIRE_APPROVAL, fail-closed on denial/failure, and the
        final COMPLETED bookkeeping are all identical to run().
        The synchronous run() is left untouched because it is
        proven code; this method exists so a FastAPI request can
        await one workflow without asyncio.run(), a nested loop,
        or a thread bridge.

        Completed steps are never re-executed by this method:
        callers resume with the remaining step list, exactly as
        TaskRunner already does.
        """

        ordered = sorted(steps, key=lambda step: step.order)

        if not ordered:
            # Same semantics as run(): an empty plan executed
            # nothing and must not read as success.
            return AutomationResult(
                task_id=task.id,
                state=WorkflowState.NO_STEPS,
                steps=[],
                reason="plan contained no executable steps",
            )

        task.status = TaskStatus.RUNNING

        for step in ordered:

            # Same workflow-level status restoration the sync
            # path performs: a later SENSITIVE step must pause a
            # RUNNING task, not a COMPLETED one.
            task.status = TaskStatus.RUNNING

            result = await self._agent.execute_async(
                task,
                step.tool_name,
                step.params,
            )

            self._sync_step(step, result)

            if result.decision == PermissionDecision.REQUIRE_APPROVAL:
                return AutomationResult(
                    task_id=task.id,
                    state=WorkflowState.PAUSED,
                    steps=ordered,
                    reason=result.reason,
                )

            if result.status == TaskStatus.FAILED:
                task.status = TaskStatus.FAILED
                task.error = result.error or result.reason
                return AutomationResult(
                    task_id=task.id,
                    state=WorkflowState.FAILED,
                    steps=ordered,
                    reason=task.error,
                )

        task.status = TaskStatus.COMPLETED
        task.result = {
            step.tool_name: step.result for step in ordered
        }
        task.error = None
        return AutomationResult(
            task_id=task.id,
            state=WorkflowState.COMPLETED,
            steps=ordered,
        )

    @staticmethod
    def _sync_step(
        step: TaskStep,
        result: ExecutionResult,
    ) -> None:
        """Copy the agent outcome onto the step record."""

        if result.decision == PermissionDecision.REQUIRE_APPROVAL:
            step.status = TaskStatus.PENDING
            return

        step.status = result.status

        if result.status == TaskStatus.COMPLETED:
            step.result = result.output
        elif result.status == TaskStatus.FAILED:
            step.error = result.error or result.reason

"""
GHOST — reflection engine (M3-G).

Deterministic, read-only classification of execution
artifacts into a ReflectionResult.

Evidence priority (checked in this order):
1. DENY evidence (ExecutionResult.decision == DENY, a
   policy denial reason, or a recorded human approval
   denial) -> DENIED.
2. Pause evidence (WorkflowState.PAUSED, or a PENDING
   skill result) -> AWAITING_APPROVAL.
3. Task COMPLETED -> SUCCEEDED.
4. Task FAILED:
   - with earlier completed steps -> PARTIAL,
   - otherwise -> FAILED.
5. Completed skill/execution artifacts on a non-terminal
   task -> SUCCEEDED (reflecting a sub-result).
6. Anything else -> UNKNOWN (low confidence).

The engine never re-evaluates or reinterprets the
PermissionPolicy: denial is recognized only from the
decision value or the policy's own verbatim reason text,
which is preserved unchanged in ReflectionFailure.detail.
"""

from typing import List, Optional

from backend.agents.executor import ExecutionResult
from backend.automation.engine import AutomationResult, WorkflowState
from backend.core.task import Task, TaskStatus
from backend.permissions.policy import PermissionDecision
from backend.reflection.result import (
    ReflectionFailure,
    ReflectionOutcome,
    ReflectionResult,
)
from backend.skills.skill import SkillResult


# Reason-text markers produced by PermissionPolicy.evaluate()
# (see backend/permissions/policy.py). Used ONLY to label a
# recorded failure as a denial; the text itself is preserved.
_DENIAL_MARKERS = ("Unknown tool", "DANGEROUS")

_KIND_PERMISSION = "permission_denial"
_KIND_TOOL = "tool_error"
_KIND_SKILL = "skill_error"
_KIND_UNKNOWN = "unknown"

_CONFIDENCE = {
    ReflectionOutcome.SUCCEEDED: 1.0,
    ReflectionOutcome.DENIED: 0.95,
    ReflectionOutcome.FAILED: 0.9,
    ReflectionOutcome.AWAITING_APPROVAL: 0.9,
    ReflectionOutcome.PARTIAL: 0.8,
    ReflectionOutcome.UNKNOWN: 0.3,
}


class ReflectionEngine:
    """Post-execution analyzer. Holds no security-sensitive
    references: no registry, no policy, no agent, no memory."""

    def reflect_on_task(
        self,
        task: Task,
        automation_result: Optional[AutomationResult] = None,
        execution_result: Optional[ExecutionResult] = None,
        skill_result: Optional[SkillResult] = None,
    ) -> ReflectionResult:
        """
        Analyze one finished (or paused) execution and return
        a structured ReflectionResult. Read-only: the task
        and all artifacts are left untouched.
        """

        failures = self._collect_failures(
            task,
            automation_result,
            execution_result,
            skill_result,
        )

        outcome = self._classify(
            task,
            automation_result,
            execution_result,
            skill_result,
            failures,
        )

        return ReflectionResult(
            task_id=task.id,
            outcome=outcome,
            succeeded=outcome == ReflectionOutcome.SUCCEEDED,
            summary=self._summarize(
                task,
                outcome,
                automation_result,
                failures,
            ),
            failures=failures,
            causes=self._causes(failures),
            lessons=self._lessons(outcome, failures),
            recommended_next_action=self._next_action(outcome),
            confidence=_CONFIDENCE[outcome],
            memory_write_recommended=(
                outcome
                in (
                    ReflectionOutcome.FAILED,
                    ReflectionOutcome.PARTIAL,
                    ReflectionOutcome.DENIED,
                )
                and bool(failures)
            ),
        )

    # ========================================================
    # EVIDENCE COLLECTION (read-only)
    # ========================================================

    def _collect_failures(
        self,
        task: Task,
        automation_result,
        execution_result,
        skill_result,
    ) -> List[ReflectionFailure]:

        failures: List[ReflectionFailure] = []

        if automation_result is not None:
            approval_denied = automation_result.approval_denied
            for step in automation_result.steps:
                if step.status == TaskStatus.FAILED:
                    detail = step.error or "no failure detail recorded"
                    failures.append(
                        ReflectionFailure(
                            step_id=step.id,
                            tool_name=step.tool_name,
                            # No decision is available on a bare
                            # step: only the policy's own verbatim
                            # reason text may label it a denial
                            # (see _failure_kind); a generic tool
                            # error must stay a tool error.
                            kind=self._failure_kind(
                                detail,
                                None,
                                approval_denied=approval_denied,
                            ),
                            detail=detail,
                        )
                    )

        if execution_result is not None:
            if (
                execution_result.decision == PermissionDecision.DENY
                or execution_result.status == TaskStatus.FAILED
            ):
                detail = (
                    execution_result.error
                    or execution_result.reason
                    or "no failure detail recorded"
                )
                failures.append(
                    ReflectionFailure(
                        step_id=None,
                        tool_name=None,
                        kind=self._failure_kind(
                            detail,
                            execution_result.decision,
                        ),
                        detail=detail,
                    )
                )

        if skill_result is not None and skill_result.status == TaskStatus.FAILED:
            failures.append(
                ReflectionFailure(
                    step_id=None,
                    tool_name=None,
                    kind=_KIND_SKILL,
                    detail=skill_result.error or "no failure detail recorded",
                )
            )

        if task.status == TaskStatus.FAILED and not failures:
            failures.append(
                ReflectionFailure(
                    step_id=None,
                    tool_name=None,
                    kind=_KIND_UNKNOWN,
                    detail=task.error or "no failure detail recorded",
                )
            )

        return failures

    @staticmethod
    def _failure_kind(
        detail: str,
        decision,
        approval_denied: bool = False,
    ) -> str:
        """
        Label a failure. A DENY decision is authoritative;
        otherwise the policy's own reason text is recognized.
        No permission logic is re-implemented here.
        """

        if approval_denied or decision == PermissionDecision.DENY:
            return _KIND_PERMISSION

        if any(marker in detail for marker in _DENIAL_MARKERS):
            return _KIND_PERMISSION

        return _KIND_TOOL

    # ========================================================
    # CLASSIFICATION
    # ========================================================

    def _classify(
        self,
        task: Task,
        automation_result,
        execution_result,
        skill_result,
        failures,
    ) -> ReflectionOutcome:

        paused = (
            (
                automation_result is not None
                and automation_result.state == WorkflowState.PAUSED
            )
            or (
                execution_result is not None
                and execution_result.decision
                == PermissionDecision.REQUIRE_APPROVAL
            )
            or (
                skill_result is not None
                and skill_result.status == TaskStatus.PENDING
            )
        )

        denied = (
            (
                automation_result is not None
                and automation_result.approval_denied
            )
            or (
                execution_result is not None
                and execution_result.decision == PermissionDecision.DENY
            )
            or any(
                failure.kind == _KIND_PERMISSION
                for failure in failures
            )
        )

        if denied:
            return ReflectionOutcome.DENIED

        if paused:
            return ReflectionOutcome.AWAITING_APPROVAL

        if task.status == TaskStatus.COMPLETED:
            return ReflectionOutcome.SUCCEEDED

        if task.status == TaskStatus.FAILED:
            has_completed_steps = (
                automation_result is not None
                and any(
                    step.status == TaskStatus.COMPLETED
                    for step in automation_result.steps
                )
            )
            if has_completed_steps and failures:
                return ReflectionOutcome.PARTIAL
            return ReflectionOutcome.FAILED

        # Non-terminal task, but a sub-artifact completed.
        sub_completed = (
            execution_result is not None
            and execution_result.status == TaskStatus.COMPLETED
        ) or (
            skill_result is not None
            and skill_result.status == TaskStatus.COMPLETED
        )
        if sub_completed:
            return ReflectionOutcome.SUCCEEDED

        return ReflectionOutcome.UNKNOWN

    # ========================================================
    # NARRATIVE FIELDS (deterministic, evidence-based)
    # ========================================================

    def _summarize(
        self,
        task: Task,
        outcome: ReflectionOutcome,
        automation_result,
        failures,
    ) -> str:

        title = task.title

        if outcome == ReflectionOutcome.SUCCEEDED:
            if automation_result is not None:
                completed = sum(
                    1
                    for step in automation_result.steps
                    if step.status == TaskStatus.COMPLETED
                )
                return (
                    f"Task '{title}' completed successfully: "
                    f"all {completed} step(s) succeeded."
                )
            return f"Task '{title}' completed successfully."

        if outcome == ReflectionOutcome.PARTIAL:
            total = len(automation_result.steps)
            completed = sum(
                1
                for step in automation_result.steps
                if step.status == TaskStatus.COMPLETED
            )
            return (
                f"Task '{title}' partially succeeded: "
                f"{completed} of {total} step(s) completed "
                "before a failure stopped the workflow."
            )

        if outcome == ReflectionOutcome.FAILED:
            if failures:
                first = failures[0]
                where = (
                    f" at step '{first.tool_name}'"
                    if first.tool_name
                    else ""
                )
                return f"Task '{title}' failed{where}: {first.detail}"
            return f"Task '{title}' failed."

        if outcome == ReflectionOutcome.DENIED:
            detail = failures[0].detail if failures else ""
            if (
                automation_result is not None
                and automation_result.approval_denied
            ):
                return (
                    f"Task '{title}' was declined by the user: "
                    f"{detail}"
                )
            return (
                f"Task '{title}' was blocked by the "
                f"permission policy: {detail}"
            )

        if outcome == ReflectionOutcome.AWAITING_APPROVAL:
            return (
                f"Task '{title}' is paused awaiting user "
                "approval; nothing has failed."
            )

        return (
            f"Task '{title}' outcome could not be determined "
            "from the available evidence."
        )

    @staticmethod
    def _causes(failures) -> List[str]:

        prefix = {
            _KIND_PERMISSION: "permission denial",
            _KIND_TOOL: "tool failure",
            _KIND_SKILL: "skill failure",
            _KIND_UNKNOWN: "cause not recorded",
        }

        return [
            f"{prefix[failure.kind]}: {failure.detail}"
            for failure in failures
        ]

    @staticmethod
    def _lessons(outcome, failures) -> List[str]:

        if outcome == ReflectionOutcome.SUCCEEDED:
            return []

        if outcome == ReflectionOutcome.AWAITING_APPROVAL:
            return ["Resume after the user approves the pending step."]

        if outcome == ReflectionOutcome.UNKNOWN:
            return [
                "Collect complete execution artifacts to reflect reliably."
            ]

        lessons: List[str] = []

        for failure in failures:
            if failure.kind == _KIND_PERMISSION:
                if "was denied by the user." in failure.detail:
                    lessons.append(
                        "Do not retry automatically; the user denied "
                        "the pending step."
                    )
                elif "Unknown tool" in failure.detail:
                    lessons.append(
                        "Register or correct the tool name before retrying."
                    )
                else:
                    lessons.append(
                        "Do not retry automatically; the permission "
                        "policy must be changed by the user."
                    )
            elif failure.kind == _KIND_TOOL:
                lessons.append(
                    "Address the tool failure before retrying."
                )
            elif failure.kind == _KIND_SKILL:
                lessons.append(
                    "Fix or avoid the failing skill."
                )
            else:
                lessons.append(
                    "Investigate the task state before retrying."
                )

        if outcome == ReflectionOutcome.PARTIAL:
            lessons.append(
                "Re-run the remaining steps after fixing the failure."
            )

        # Deterministic, duplicate-free ordering.
        seen = set()
        unique = []
        for lesson in lessons:
            if lesson not in seen:
                seen.add(lesson)
                unique.append(lesson)
        return unique

    @staticmethod
    def _next_action(outcome: ReflectionOutcome) -> str:

        return {
            ReflectionOutcome.SUCCEEDED: (
                "No further action required."
            ),
            ReflectionOutcome.PARTIAL: (
                "Fix the failing step, then re-run the remaining steps."
            ),
            ReflectionOutcome.FAILED: (
                "Fix the failing step and retry the task."
            ),
            ReflectionOutcome.DENIED: (
                "Do not retry automatically; resolve the permission "
                "or tool-registration issue first."
            ),
            ReflectionOutcome.AWAITING_APPROVAL: (
                "Ask the user to approve the pending step, then resume."
            ),
            ReflectionOutcome.UNKNOWN: (
                "Investigate the task state before retrying."
            ),
        }[outcome]

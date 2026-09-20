"""
GHOST — skill interface (M3-F).

A Skill plans and executes work for a Task using the
existing agent execution pipeline. Skills NEVER call
tools, files, or network directly: tool steps go through
the Agent (which consults the PermissionPolicy first) or
through the AutomationEngine that drives the same Agent.

Params conventions for run():
- "automation_engine": an AutomationEngine instance.
  Direct skill.run() calls may omit it; tool-using skills
  then build one around the given agent.
- "skill_registry": a SkillRegistry (system-introspection
  skills such as skill-catalog read it here).
- "permission_policy": a PermissionPolicy (skills that
  explain permissions read it here).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from backend.automation.engine import WorkflowState
from backend.core.task import Task, TaskStatus


@dataclass
class SkillResult:
    """
    Outcome of one skill invocation.

    status reuses TaskStatus — one status vocabulary
    across tasks, steps, and skills. A workflow paused
    for approval maps to PENDING (waiting, not failed).
    """

    skill_name: str
    status: TaskStatus
    output: Any = None
    error: Optional[str] = None
    steps: Optional[list] = None


def status_from_workflow(state: WorkflowState) -> TaskStatus:
    """Map an AutomationEngine outcome onto TaskStatus."""

    if state == WorkflowState.COMPLETED:
        return TaskStatus.COMPLETED

    if state == WorkflowState.PAUSED:
        return TaskStatus.PENDING

    return TaskStatus.FAILED


class Skill(ABC):
    """
    Base class for all GHOST skills.

    Subclasses set `metadata` (SkillMetadata) and implement
    run(). run() must be deterministic given its inputs.
    """

    metadata: Any  # SkillMetadata; typed loosely to avoid a cycle

    @abstractmethod
    def run(
        self,
        task: Task,
        agent: Any,
        params: dict,
    ) -> SkillResult:
        """Execute the skill for the task."""

"""
GHOST builtin skill: task-breakdown (M3-F).

Breaks a goal into an ordered list of subtasks — pure
deterministic planning, no tools, no permissions needed.
The produced plan can later be turned into TaskSteps for
the AutomationEngine by a higher layer.

Splitting rules (deterministic):
- params["subtasks"], if provided, is used verbatim in
  order.
- otherwise the goal is split on newlines, semicolons or
  commas; a goal that yields no separators becomes one
  subtask.
"""

from backend.core.task import Task, TaskStatus
from backend.skills.metadata import SkillMetadata
from backend.skills.skill import Skill, SkillResult


class TaskBreakdownSkill(Skill):

    metadata = SkillMetadata(
        name="task-breakdown",
        description=(
            "Break a goal into ordered subtasks ready to "
            "become task steps."
        ),
        category="productivity",
        version="1.0",
        required_tools=[],
        entrypoint=(
            "backend.skills.builtin.task_breakdown:TaskBreakdownSkill"
        ),
    )

    def run(
        self,
        task: Task,
        agent,
        params: dict,
    ) -> SkillResult:

        goal = str(params.get("goal", "")).strip()

        if not goal:
            return SkillResult(
                skill_name=self.metadata.name,
                status=TaskStatus.FAILED,
                error="task-breakdown requires a 'goal' parameter.",
            )

        subtasks = params.get("subtasks")

        if subtasks:
            titles = [str(item).strip() for item in subtasks]
            titles = [title for title in titles if title]
        else:
            import re

            parts = re.split(r"[\n;,]+", goal)
            titles = [part.strip() for part in parts if part.strip()]

        if not titles:
            titles = [goal]

        output = [
            {"order": order, "title": title}
            for order, title in enumerate(titles)
        ]

        return SkillResult(
            skill_name=self.metadata.name,
            status=TaskStatus.COMPLETED,
            output=output,
        )

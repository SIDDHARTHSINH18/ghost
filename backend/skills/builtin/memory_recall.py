"""
GHOST builtin skill: memory-recall (M3-F).

Searches the user's long-term memory through the
"memory_search" tool (SAFE). The tool itself is provided
by the ToolRegistry — this skill only plans the step, so
it stays deterministic and mock-testable.
"""

from backend.agents.executor import Agent
from backend.automation.engine import AutomationEngine, TaskStep
from backend.core.task import Task
from backend.skills.metadata import SkillMetadata
from backend.skills.skill import (
    Skill,
    SkillResult,
    status_from_workflow,
)
from backend.tools.registry import RiskLevel


class MemoryRecallSkill(Skill):

    metadata = SkillMetadata(
        name="memory-recall",
        description=(
            "Search the user's long-term memory for relevant "
            "facts and return the best matches."
        ),
        category="memory",
        version="1.0",
        required_tools=["memory_search"],
        risk_level=RiskLevel.SAFE,
        entrypoint=(
            "backend.skills.builtin.memory_recall:MemoryRecallSkill"
        ),
    )

    def run(
        self,
        task: Task,
        agent: Agent,
        params: dict,
    ) -> SkillResult:

        query = str(params.get("query", "")).strip()

        if not query:
            return SkillResult(
                skill_name=self.metadata.name,
                status=TaskStatus.FAILED,
                error="memory-recall requires a 'query' parameter.",
            )

        engine = params.get("automation_engine") or AutomationEngine(agent)

        step = TaskStep(
            tool_name="memory_search",
            params={"query": query},
            order=0,
            title="Search memory",
        )

        outcome = engine.run(task, [step])

        if outcome.state.value == "COMPLETED":
            output = step.result
        else:
            output = None

        return SkillResult(
            skill_name=self.metadata.name,
            status=status_from_workflow(outcome.state),
            output=output,
            error=task.error if outcome.state.value == "FAILED" else None,
            steps=[step],
        )

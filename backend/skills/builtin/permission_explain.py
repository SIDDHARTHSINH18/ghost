"""
GHOST builtin skill: permission-explain (M3-F).

Explains what the PermissionPolicy would decide for a
tool, and why. Read-only and deterministic: it evaluates
the policy but executes nothing. The policy is provided
under the "permission_policy" params key (injected by
SkillRunner).
"""

from backend.core.task import Task, TaskStatus
from backend.skills.metadata import SkillMetadata
from backend.skills.runner import PERMISSION_POLICY_KEY
from backend.skills.skill import Skill, SkillResult


class PermissionExplainSkill(Skill):

    metadata = SkillMetadata(
        name="permission-explain",
        description=(
            "Explain the permission decision GHOST would "
            "make for a tool and the reason behind it."
        ),
        category="system",
        version="1.0",
        required_tools=[],
        entrypoint=(
            "backend.skills.builtin.permission_explain:PermissionExplainSkill"
        ),
    )

    def run(
        self,
        task: Task,
        agent,
        params: dict,
    ) -> SkillResult:

        policy = params.get(PERMISSION_POLICY_KEY)

        if policy is None:
            return SkillResult(
                skill_name=self.metadata.name,
                status=TaskStatus.FAILED,
                error=(
                    "permission-explain requires a PermissionPolicy "
                    f"under the '{PERMISSION_POLICY_KEY}' parameter."
                ),
            )

        tool_name = str(params.get("tool_name", "")).strip()

        if not tool_name:
            return SkillResult(
                skill_name=self.metadata.name,
                status=TaskStatus.FAILED,
                error="permission-explain requires a 'tool_name' parameter.",
            )

        result = policy.evaluate(tool_name)

        output = {
            "tool": tool_name,
            "decision": result.decision.value,
            "reason": result.reason,
        }

        return SkillResult(
            skill_name=self.metadata.name,
            status=TaskStatus.COMPLETED,
            output=output,
        )

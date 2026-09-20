"""
GHOST builtin skill: skill-catalog (M3-F).

Reports the skills registered in the SkillRegistry.
Metadata-only: listing the catalog never loads any skill
implementation. The registry is provided under the
"skill_registry" params key (injected by SkillRunner).
"""

from backend.core.task import Task, TaskStatus
from backend.skills.metadata import SkillMetadata
from backend.skills.runner import SKILL_REGISTRY_KEY
from backend.skills.skill import Skill, SkillResult


class SkillCatalogSkill(Skill):

    metadata = SkillMetadata(
        name="skill-catalog",
        description=(
            "List the skills available in GHOST with their "
            "category and description."
        ),
        category="system",
        version="1.0",
        required_tools=[],
        entrypoint=(
            "backend.skills.builtin.skill_catalog:SkillCatalogSkill"
        ),
    )

    def run(
        self,
        task: Task,
        agent,
        params: dict,
    ) -> SkillResult:

        registry = params.get(SKILL_REGISTRY_KEY)

        if registry is None:
            return SkillResult(
                skill_name=self.metadata.name,
                status=TaskStatus.FAILED,
                error=(
                    "skill-catalog requires a SkillRegistry under "
                    f"the '{SKILL_REGISTRY_KEY}' parameter."
                ),
            )

        output = [
            {
                "name": metadata.name,
                "category": metadata.category,
                "description": metadata.description,
                "version": metadata.version,
            }
            for metadata in sorted(
                registry.list_metadata(),
                key=lambda metadata: metadata.name,
            )
        ]

        return SkillResult(
            skill_name=self.metadata.name,
            status=TaskStatus.COMPLETED,
            output=output,
        )

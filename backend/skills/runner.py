"""
GHOST — skill runner (M3-F).

Thin integration layer between the Skill System and the
existing M3 pipeline. The runner NEVER executes tools and
NEVER checks permissions itself: it loads the selected
skill and hands it the shared Agent, whose execute() path
consults the PermissionPolicy before any tool runs, plus
an AutomationEngine built on that same Agent for
multi-step skills.

System services a skill may need are provided through
well-known params keys (see backend/skills/skill.py):
"skill_registry" and "permission_policy". The runner
injects them; direct skill.run() callers may pass them
explicitly.
"""

from backend.automation.engine import AutomationEngine
from backend.core.task import Task
from backend.skills.loader import SkillLoader
from backend.skills.registry import SkillRegistry
from backend.skills.skill import SkillResult


SKILL_REGISTRY_KEY = "skill_registry"
PERMISSION_POLICY_KEY = "permission_policy"
AUTOMATION_ENGINE_KEY = "automation_engine"


class SkillRunner:
    def __init__(
        self,
        agent,
        skill_registry: SkillRegistry,
        loader: SkillLoader,
        permission_policy=None,
        automation_engine: AutomationEngine | None = None,
    ):
        self._agent = agent
        self._skills = skill_registry
        self._loader = loader
        self._permissions = permission_policy
        self._engine = automation_engine or AutomationEngine(agent)

    def execute(
        self,
        skill_name: str,
        task: Task,
        params: dict | None = None,
    ) -> SkillResult:
        """
        Load (lazily) and run one skill for the task.

        Unknown skills fail here, before anything runs.
        """

        # Clear, early failure for unknown skills.
        self._skills.get_metadata(skill_name)

        skill = self._loader.load(skill_name)

        run_params = dict(params or {})
        run_params.setdefault(SKILL_REGISTRY_KEY, self._skills)

        if self._permissions is not None:
            run_params.setdefault(
                PERMISSION_POLICY_KEY,
                self._permissions,
            )

        run_params.setdefault(AUTOMATION_ENGINE_KEY, self._engine)

        return skill.run(task, self._agent, run_params)

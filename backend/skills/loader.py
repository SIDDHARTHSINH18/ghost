"""
GHOST — skill loader (M3-F).

Lazy loading: a skill's implementation module is imported
only when its name is requested, and the created instance
is cached. Registration and routing (SkillRegistry /
SkillRouter) never trigger an import — with ~396+ skills
the resident cost is metadata only.
"""

import importlib
from typing import Dict

from backend.skills.metadata import SkillMetadata
from backend.skills.registry import SkillRegistry


class SkillLoader:
    def __init__(self, registry: SkillRegistry):
        self._registry = registry
        self._cache: Dict[str, object] = {}

    def load(self, name: str):
        """
        Return the cached skill instance, creating it on
        first request by importing the metadata's declared
        entrypoint ("module.path:ClassName").
        """

        if name in self._cache:
            return self._cache[name]

        metadata: SkillMetadata = self._registry.get_metadata(name)

        module_name, separator, class_name = (
            metadata.entrypoint.partition(":")
        )

        if not separator or not module_name or not class_name:
            raise ValueError(
                f"Skill '{name}' has an invalid entrypoint: "
                f"'{metadata.entrypoint}' (expected 'module.path:ClassName')."
            )

        module = importlib.import_module(module_name)

        skill_class = getattr(module, class_name, None)

        if skill_class is None:
            raise ValueError(
                f"Entrypoint '{metadata.entrypoint}' for skill "
                f"'{name}' does not define '{class_name}'."
            )

        skill = skill_class()

        self._cache[name] = skill

        return skill

    def is_loaded(self, name: str) -> bool:
        return name in self._cache

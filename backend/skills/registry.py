"""
GHOST — skill registry (M3-F).

Metadata-only index of known skills. Registration and
listing never import skill implementations — that is the
point of the metadata/implementation split. Skill code is
loaded later, on demand, by SkillLoader.
"""

from typing import Dict, List

from backend.skills.metadata import SkillMetadata


class SkillRegistry:
    def __init__(self):
        self._skills: Dict[str, SkillMetadata] = {}

    def register_metadata(self, metadata: SkillMetadata) -> None:
        if not metadata.name:
            raise ValueError("Skill name cannot be empty.")

        if metadata.name in self._skills:
            raise ValueError(
                f"Skill '{metadata.name}' is already registered."
            )

        self._skills[metadata.name] = metadata

    def get_metadata(self, name: str) -> SkillMetadata:
        if name not in self._skills:
            raise KeyError(f"Skill '{name}' not found.")
        return self._skills[name]

    def list_metadata(self) -> List[SkillMetadata]:
        return list(self._skills.values())

    def count(self) -> int:
        return len(self._skills)

"""
GHOST — skill router (M3-F), deterministic v1.

Ranks skills for a user requirement using only
SkillMetadata (name / description / category) — no model
call, no skill import, fully deterministic. Requirements
with no lexical match return an empty list: "no skill"
is a safe outcome, not an error (callers fall back to
plain chat).
"""

import re
from typing import List, Optional

from backend.skills.metadata import SkillMetadata
from backend.skills.registry import SkillRegistry


_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")

# Words too generic to help routing.
_STOP_WORDS = {
    "a", "an", "and", "for", "in", "is", "it", "me", "my",
    "of", "on", "the", "this", "to", "with",
}

_NAME_WEIGHT = 3
_CATEGORY_WEIGHT = 2
_DESCRIPTION_WEIGHT = 1


def _tokenize(text: str) -> List[str]:
    return [
        token
        for token in _TOKEN_SPLIT.split(text.lower())
        if token and token not in _STOP_WORDS
    ]


class SkillRouter:
    def __init__(
        self,
        registry: SkillRegistry,
        default_limit: int = 5,
    ):
        self._registry = registry
        self.default_limit = default_limit

    def select(
        self,
        requirement: str,
        limit: Optional[int] = None,
    ) -> List[SkillMetadata]:
        """
        Return matching skills, best first. Deterministic:
        same requirement -> same ranking (ties break by
        skill name).
        """

        if not requirement or not requirement.strip():
            return []

        limit = limit if limit is not None else self.default_limit

        requirement_tokens = set(_tokenize(requirement))

        if not requirement_tokens:
            return []

        scored = []

        for metadata in self._registry.list_metadata():

            score = 0

            for token in _tokenize(metadata.name):
                if token in requirement_tokens:
                    score += _NAME_WEIGHT

            for token in _tokenize(metadata.category):
                if token in requirement_tokens:
                    score += _CATEGORY_WEIGHT

            for token in _tokenize(metadata.description):
                if token in requirement_tokens:
                    score += _DESCRIPTION_WEIGHT

            if score > 0:
                scored.append((score, metadata.name, metadata))

        scored.sort(key=lambda item: (-item[0], item[1]))

        return [metadata for _, _, metadata in scored[:limit]]

"""
GHOST — skill metadata (M3-F).

SkillMetadata is the ONLY thing that stays resident for
registration and routing, no matter how many skills exist
(~396+ target). It is deliberately tiny and imports no
skill implementation code.
"""

from dataclasses import dataclass, field
from typing import List

from backend.tools.registry import RiskLevel


@dataclass
class SkillMetadata:
    """
    Static description of a skill.

    risk_level is the union of the risk of the tools the
    skill invokes (derived offline, kept explicit here) so
    catalogs and UIs can display it without loading the
    implementation. Actual enforcement never happens here:
    every step goes through the Agent -> PermissionPolicy
    path at run time.
    """

    name: str
    description: str
    category: str
    version: str = "1.0"
    required_tools: List[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.SAFE
    entrypoint: str = ""

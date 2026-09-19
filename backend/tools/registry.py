from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class RiskLevel(Enum):
    SAFE = "SAFE"
    SENSITIVE = "SENSITIVE"
    DANGEROUS = "DANGEROUS"


@dataclass
class ToolMetadata:
    name: str
    description: str
    category: str
    risk_level: RiskLevel


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolMetadata] = {}

    def register(
        self,
        name: str,
        description: str,
        category: str,
        risk_level: RiskLevel,
    ) -> None:
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered.")

        self._tools[name] = ToolMetadata(
            name=name,
            description=description,
            category=category,
            risk_level=risk_level,
        )

    def get_tool(self, name: str) -> ToolMetadata:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found.")
        return self._tools[name]

    def list_tools(self) -> List[ToolMetadata]:
        return list(self._tools.values())

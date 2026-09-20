"""
GHOST — reflection result types (M3-G).

Pure dataclasses, JSON-serializable via to_dict() (or
dataclasses.asdict). These structures are the stable
contract consumed by later layers (M3-H work-pattern
learning, memory bridge) — ReflectionEngine produces
them; nothing else interprets them here.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import List, Optional


class ReflectionOutcome(Enum):
    """Deterministic classification of one execution."""

    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    DENIED = "DENIED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    UNKNOWN = "UNKNOWN"


@dataclass
class ReflectionFailure:
    """
    One recorded failure, quoting the existing reason/error
    strings verbatim — never re-derived permission logic.

    kind is one of:
      "permission_denial"  (DENY decision or its reason text)
      "tool_error"         (tool execution raised / failed)
      "skill_error"        (the skill itself reported failure)
      "unknown"            (failure recorded without detail)
    """

    step_id: Optional[str]
    tool_name: Optional[str]
    kind: str
    detail: str


@dataclass
class ReflectionResult:
    task_id: str
    outcome: ReflectionOutcome
    succeeded: bool
    summary: str
    failures: List[ReflectionFailure] = field(default_factory=list)
    causes: List[str] = field(default_factory=list)
    lessons: List[str] = field(default_factory=list)
    recommended_next_action: str = ""
    confidence: float = 0.0
    memory_write_recommended: bool = False

    def to_dict(self) -> dict:
        """
        JSON-safe dict: the outcome enum becomes its value;
        nested failures become plain dicts via asdict().
        """

        data = asdict(self)
        data["outcome"] = self.outcome.value
        return data

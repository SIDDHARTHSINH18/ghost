"""
GHOST — foundational permission policy (M3-C).

Deterministic mapping from a tool's RiskLevel (defined by
backend/tools.registry) to a permission decision:

  SAFE       -> ALLOW             (executes automatically)
  SENSITIVE  -> REQUIRE_APPROVAL  (explicit user approval)
  DANGEROUS  -> DENY              (blocked)

Fail-closed by design: an unknown tool, or a risk level
with no mapping, is always DENY. Overrides are explicit
and per-RiskLevel, keeping behavior predictable and easy
to extend in later M3 steps (approval workflows, per-tool
rules) without changing this core decision path.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from backend.tools.registry import RiskLevel, ToolRegistry


class PermissionDecision(Enum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


DEFAULT_RISK_POLICY = {
    RiskLevel.SAFE: PermissionDecision.ALLOW,
    RiskLevel.SENSITIVE: PermissionDecision.REQUIRE_APPROVAL,
    RiskLevel.DANGEROUS: PermissionDecision.DENY,
}


@dataclass
class PermissionResult:
    decision: PermissionDecision
    reason: str


class PermissionPolicy:
    """
    Decides what may happen to a tool before it runs.

    Reads tool metadata from the shared ToolRegistry —
    it does not define its own risk levels, so there is
    exactly one risk model in GHOST.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        risk_policy: dict | None = None,
        approval_grants: Any = None,
    ):
        self._registry = registry
        self._risk_policy = (
            dict(DEFAULT_RISK_POLICY)
            if risk_policy is None
            else dict(risk_policy)
        )
        # Optional one-shot approval grants (M3-H step 5):
        # an object with consume(task_id, tool_name) -> bool.
        # When a REQUIRE_APPROVAL decision would pause a
        # task, an explicitly GRANTED approval for that
        # exact task+tool is consumed to allow exactly that
        # one execution. DENY is never overridden, SAFE is
        # unaffected, and without a grant nothing changes.
        self._approval_grants = approval_grants

    def set_policy(
        self,
        risk_level: RiskLevel,
        decision: PermissionDecision,
    ) -> None:
        """Explicit override for one risk level."""
        self._risk_policy[risk_level] = decision

    def evaluate(
        self,
        tool_name: str,
        task_id: str | None = None,
    ) -> PermissionResult:
        """
        Deterministic decision for the named tool.
        Unknown tools fail closed (DENY).
        """

        try:
            tool = self._registry.get_tool(tool_name)
        except KeyError:
            return PermissionResult(
                PermissionDecision.DENY,
                f"Unknown tool '{tool_name}'.",
            )

        decision = self._risk_policy.get(
            tool.risk_level,
            PermissionDecision.DENY,
        )

        # Explicit one-shot approval (M3-H step 5): only a
        # REQUIRE_APPROVAL decision may be upgraded, and
        # only by consuming a GRANTED approval recorded for
        # this exact task + tool. DENY stays DENY.
        if (
            decision == PermissionDecision.REQUIRE_APPROVAL
            and task_id is not None
            and self._approval_grants is not None
            and self._approval_grants.consume(task_id, tool_name)
        ):
            return PermissionResult(
                PermissionDecision.ALLOW,
                (
                    f"Tool '{tool_name}' is "
                    f"{tool.risk_level.value}: ALLOW "
                    "(explicit user approval granted "
                    "for this task)."
                ),
            )

        if tool.risk_level not in self._risk_policy:
            reason = (
                f"No policy for risk level "
                f"'{tool.risk_level.value}'; denied."
            )
        else:
            reason = (
                f"Tool '{tool_name}' is "
                f"{tool.risk_level.value}: {decision.value}."
            )

        return PermissionResult(decision, reason)

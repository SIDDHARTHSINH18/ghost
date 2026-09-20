"""
GHOST — production M3 service wiring (M3-H step 1).

Builds the shared runtime objects for the agent pipeline
using the existing M3 implementations exactly as they are
(no M3-A..M3-G file is modified):

  ToolRegistry -> PermissionPolicy -> production executor
    -> Agent -> AutomationEngine
  plus SkillRegistry/SkillLoader/SkillRouter/SkillRunner
  and ReflectionEngine singletons.

Import direction is strictly one-way:
  agent_services -> tools/permissions/agents/automation/
  skills/reflection. Nothing below imports this module
  back (no circular imports), and nothing exposes these
  services through an API yet (no main.py change).

There is exactly one model gateway (core.orchestrator)
and this module creates none.
"""

from backend.agents.executor import Agent
from backend.approval.service import ApprovalService
from backend.automation.engine import AutomationEngine
from backend.permissions.policy import PermissionPolicy
from backend.reflection.engine import ReflectionEngine
from backend.skills.builtin import register_builtin_skills
from backend.skills.loader import SkillLoader
from backend.skills.registry import SkillRegistry
from backend.skills.router import SkillRouter
from backend.skills.runner import SkillRunner
from backend.tools.builtin.fs import (
    fs_file_exists,
    fs_list_directory,
    fs_read_file,
)
from backend.tools.registry import RiskLevel, ToolRegistry


# ============================================================
# TOOL REGISTRY (production)
# ============================================================

tool_registry = ToolRegistry()


def register_builtin_tools(registry: ToolRegistry) -> None:
    """Register every real builtin tool with explicit
    category and risk level. New tools are added here."""

    registry.register(
        name="fs_read_file",
        description=(
            "Read a local text file (absolute path, "
            "max 1 MB, read-only)."
        ),
        category="filesystem",
        risk_level=RiskLevel.SAFE,
    )
    registry.register(
        name="fs_list_directory",
        description=(
            "List immediate entries in a local directory "
            "(absolute path, read-only)."
        ),
        category="filesystem",
        risk_level=RiskLevel.SAFE,
    )
    registry.register(
        name="fs_file_exists",
        description=(
            "Check whether a local regular file exists "
            "(absolute path, read-only)."
        ),
        category="filesystem",
        risk_level=RiskLevel.SAFE,
    )


register_builtin_tools(tool_registry)


# ============================================================
# PRODUCTION TOOL EXECUTOR
# ============================================================
#
# The ONLY bridge from the Agent to real tool code.
# Defensive by design:
# - dispatch table is a fixed, code-defined mapping
# - a tool name must exist in the ToolRegistry AND in
#   the table before anything runs
# - unknown/unregistered names raise (the Agent maps
#   the failure to a FAILED task; the PermissionPolicy
#   has already denied them before this point anyway)

TOOL_IMPLEMENTATIONS = {
    "fs_read_file": fs_read_file,
    "fs_list_directory": fs_list_directory,
    "fs_file_exists": fs_file_exists,
}


def production_tool_executor(tool_name: str, params: dict):
    """
    Execute one registered builtin tool. Params are
    untrusted: each tool validates its own inputs.
    """

    try:
        tool_registry.get_tool(tool_name)
    except KeyError:
        raise KeyError(
            f"Tool '{tool_name}' is not registered."
        )

    implementation = TOOL_IMPLEMENTATIONS.get(tool_name)

    if implementation is None:
        raise KeyError(
            f"Tool '{tool_name}' is registered but has "
            "no implementation wired."
        )

    return implementation(params if isinstance(params, dict) else {})


# ============================================================
# SINGLETONS
# ============================================================

# Explicit approval records (M3-H step 5). Shared by the
# policy (one-shot grant consumption) and the API layer
# (decision endpoints), so there is exactly one approval
# store.
approval_service = ApprovalService()

permission_policy = PermissionPolicy(
    tool_registry,
    approval_grants=approval_service,
)

agent = Agent(
    name="ghost-agent",
    registry=tool_registry,
    permission_policy=permission_policy,
    tool_executor=production_tool_executor,
)

automation_engine = AutomationEngine(agent)

skill_registry = SkillRegistry()
register_builtin_skills(skill_registry)

skill_loader = SkillLoader(skill_registry)
skill_router = SkillRouter(skill_registry)

skill_runner = SkillRunner(
    agent=agent,
    skill_registry=skill_registry,
    loader=skill_loader,
    permission_policy=permission_policy,
    automation_engine=automation_engine,
)

reflection_engine = ReflectionEngine()

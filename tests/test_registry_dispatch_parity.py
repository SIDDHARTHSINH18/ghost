"""
M4 step 4 — registry / dispatch / permission / spec parity.

GHOST has exactly one tool registry, one dispatch table, one
permission policy and one spec builder. They are maintained
separately, so a new tool can silently be registered without an
implementation, dispatched without a risk level, or planned
without appearing in the registry. These tests assert the
cross-component invariants that make that impossible to ship.

All assertions run against the PRODUCTION singletons, so adding
a tool without wiring it fails here rather than at runtime.
"""

import asyncio
import inspect

import pytest

import backend.core.agent_services as agent_services

from backend.agents.executor import Agent
from backend.api.tasks import planner as production_planner
from backend.core.execution_spec import build_execution_spec
from backend.core.planner import PlannedStep
from backend.core.task import Task, TaskStatus
from backend.permissions.policy import PermissionDecision
from backend.tools.registry import RiskLevel

from backend.core.agent_services import (
    TOOL_IMPLEMENTATIONS,
    agent as production_agent,
    permission_policy,
    production_tool_executor,
    tool_registry,
)


# ============================================================
# REGISTRY <-> DISPATCH TABLE
# ============================================================

def test_every_registered_tool_has_an_implementation():
    unwired = [
        tool.name
        for tool in tool_registry.list_tools()
        if tool.name not in TOOL_IMPLEMENTATIONS
    ]

    assert unwired == []


def test_every_implementation_is_registered():
    # A dispatch entry with no metadata has no risk level and
    # would be denied by the fail-closed policy anyway: forbid it.
    unregistered = sorted(
        name for name in TOOL_IMPLEMENTATIONS
        if name not in {tool.name for tool in tool_registry.list_tools()}
    )

    assert unregistered == []


def test_implementations_are_callable():
    for name, implementation in TOOL_IMPLEMENTATIONS.items():
        assert callable(implementation), name


def test_registry_and_dispatch_are_the_same_objects_as_the_agent_uses():
    # One registry, one policy, one executor: the Agent must be
    # built from these exact singletons, not lookalikes.
    assert production_agent._registry is tool_registry
    assert production_agent._permissions is permission_policy
    assert (
        production_agent._execute_tool is production_tool_executor
    )


def test_the_planner_catalog_is_exactly_the_registry():
    assert set(production_planner._tool_catalog) == {
        tool.name for tool in tool_registry.list_tools()
    }


def test_every_registered_tool_is_described_and_categorised():
    for tool in tool_registry.list_tools():
        assert tool.description.strip(), tool.name
        assert tool.category.strip(), tool.name
        assert isinstance(tool.risk_level, RiskLevel), tool.name


# ============================================================
# REGISTRY <-> PERMISSION POLICY
# ============================================================

EXPECTED_DECISION = {
    RiskLevel.SAFE: PermissionDecision.ALLOW,
    RiskLevel.SENSITIVE: PermissionDecision.REQUIRE_APPROVAL,
    RiskLevel.DANGEROUS: PermissionDecision.DENY,
}


def test_permission_decisions_match_registered_risk_levels():
    for tool in tool_registry.list_tools():
        result = permission_policy.evaluate(tool.name)

        assert result.decision is EXPECTED_DECISION[tool.risk_level], (
            tool.name
        )


def test_unknown_tool_is_denied():
    result = permission_policy.evaluate("definitely_not_a_tool")

    assert result.decision is PermissionDecision.DENY


# ============================================================
# REGISTRY <-> EXECUTION SPEC
# ============================================================

def test_spec_risk_summary_matches_the_registry_for_every_tool():
    for tool in tool_registry.list_tools():
        planning = _planning_for(tool.name)

        spec = build_execution_spec(
            planning,
            task_id="parity-task",
            registry=tool_registry,
        )

        assert spec.steps[0].tool == tool.name
        assert spec.risk_level == tool.risk_level.value
        assert spec.approval_required is (
            tool.risk_level is RiskLevel.SENSITIVE
        )


def test_spec_denies_a_tool_the_registry_does_not_know():
    spec = build_execution_spec(
        _planning_for("ghost_only_tool"),
        task_id="parity-task",
        registry=tool_registry,
    )

    # Fail closed, mirroring PermissionPolicy on an unknown name.
    assert spec.risk_level == RiskLevel.DANGEROUS.value


# ============================================================
# DISPATCH TABLE <-> AGENT (sync/async contract)
# ============================================================

ASYNC_TOOLS = sorted(
    name
    for name, implementation in TOOL_IMPLEMENTATIONS.items()
    if inspect.iscoroutinefunction(implementation)
)


def test_async_tools_are_dispatched_as_coroutine_functions():
    # Derived from the table, not a hardcoded name list: adding an
    # async tool automatically extends the parametrized cases below.
    assert ASYNC_TOOLS


@pytest.mark.parametrize("tool_name", ASYNC_TOOLS)
def test_sync_agent_path_refuses_every_async_tool(tool_name):
    task = Task(title="parity", description="sync path contract")

    result = production_agent.execute(task, tool_name, {})

    assert result.status is TaskStatus.FAILED
    assert "execute_async" in result.error
    assert task.result is None


@pytest.mark.parametrize("tool_name", ASYNC_TOOLS)
def test_async_agent_path_awaits_every_async_tool(tool_name):
    # The contract has both halves: async tools really run on the
    # async path. {} is deliberately invalid, so the awaited
    # coroutine reaches the tool's own validation and fails
    # there — which also proves no gateway call is made.
    task = Task(title="parity", description="async path contract")

    result = asyncio.run(
        production_agent.execute_async(task, tool_name, {})
    )

    assert result.status is TaskStatus.FAILED
    assert "requires a" in result.error
    assert task.result is None


# ============================================================
# EXECUTOR GUARD RAILS
# ============================================================

def test_executor_refuses_an_unregistered_name():
    with pytest.raises(KeyError, match="is not registered"):
        production_tool_executor("no_such_tool", {})


def test_executor_refuses_a_registered_tool_without_wiring(monkeypatch):
    monkeypatch.setattr(agent_services, "TOOL_IMPLEMENTATIONS", {})

    with pytest.raises(KeyError, match="no implementation wired"):
        production_tool_executor("fs_read_file", {})


def test_executor_passes_a_dict_even_when_params_are_not():
    # Untrusted params must still reach a tool as a mapping.
    with pytest.raises(Exception) as exc_info:
        production_tool_executor("fs_read_file", "not-a-dict")

    assert "requires a 'path' parameter" in str(exc_info.value)


def test_agent_never_executes_a_denied_tool():
    calls = []

    def spy(tool_name, params):
        calls.append(tool_name)
        return "unused"

    watcher = Agent(
        name="watcher",
        registry=tool_registry,
        permission_policy=permission_policy,
        tool_executor=spy,
    )

    task = Task(title="parity", description="deny must not dispatch")

    result = watcher.execute(task, "ghost_only_tool")

    assert result.status is TaskStatus.FAILED
    assert calls == []


# ============================================================
# HELPERS
# ============================================================

def _planning_for(tool_name):
    from backend.core.planner import PlanningResult, PlanningSource

    return PlanningResult(
        request=f"use {tool_name}",
        ready=True,
        task_title="parity",
        task_description="parity",
        steps=[
            PlannedStep(
                description=f"call {tool_name}",
                tool=tool_name,
                params={},
            )
        ],
        assumptions=[],
        source=PlanningSource.MODEL,
        planned_at="2026-01-01T00:00:00",
    )

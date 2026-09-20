import pytest
from backend.permissions.policy import (
    DEFAULT_RISK_POLICY,
    PermissionDecision,
    PermissionPolicy,
)
from backend.tools.registry import RiskLevel, ToolRegistry


def make_registry():
    registry = ToolRegistry()
    registry.register("read_note", "Read a note", "memory", RiskLevel.SAFE)
    registry.register("send_email", "Send an email", "comms", RiskLevel.SENSITIVE)
    registry.register("delete_all", "Delete everything", "system", RiskLevel.DANGEROUS)
    return registry


def test_safe_action_allowed():
    policy = PermissionPolicy(make_registry())
    result = policy.evaluate("read_note")
    assert result.decision == PermissionDecision.ALLOW
    assert "SAFE" in result.reason


def test_sensitive_action_requires_approval():
    policy = PermissionPolicy(make_registry())
    result = policy.evaluate("send_email")
    assert result.decision == PermissionDecision.REQUIRE_APPROVAL
    assert "SENSITIVE" in result.reason


def test_dangerous_action_denied():
    policy = PermissionPolicy(make_registry())
    result = policy.evaluate("delete_all")
    assert result.decision == PermissionDecision.DENY
    assert "DANGEROUS" in result.reason


def test_unknown_tool_denied():
    policy = PermissionPolicy(make_registry())
    result = policy.evaluate("nonexistent_tool")
    assert result.decision == PermissionDecision.DENY
    assert "Unknown tool" in result.reason


def test_decisions_are_deterministic():
    policy = PermissionPolicy(make_registry())
    for name in ("read_note", "send_email", "delete_all"):
        first = policy.evaluate(name)
        second = policy.evaluate(name)
        assert first.decision == second.decision
        assert first.reason == second.reason


def test_default_risk_policy_mapping():
    assert DEFAULT_RISK_POLICY == {
        RiskLevel.SAFE: PermissionDecision.ALLOW,
        RiskLevel.SENSITIVE: PermissionDecision.REQUIRE_APPROVAL,
        RiskLevel.DANGEROUS: PermissionDecision.DENY,
    }


def test_decision_values():
    assert PermissionDecision.ALLOW.value == "ALLOW"
    assert PermissionDecision.REQUIRE_APPROVAL.value == "REQUIRE_APPROVAL"
    assert PermissionDecision.DENY.value == "DENY"


def test_custom_override_changes_decision():
    policy = PermissionPolicy(make_registry())
    policy.set_policy(RiskLevel.SENSITIVE, PermissionDecision.DENY)
    assert policy.evaluate("send_email").decision == PermissionDecision.DENY


def test_custom_initial_policy():
    policy = PermissionPolicy(
        make_registry(),
        risk_policy={
            RiskLevel.DANGEROUS: PermissionDecision.REQUIRE_APPROVAL,
        },
    )
    result = policy.evaluate("delete_all")
    assert result.decision == PermissionDecision.REQUIRE_APPROVAL


def test_default_policy_not_mutated_by_instance():
    policy = PermissionPolicy(make_registry())
    policy.set_policy(RiskLevel.SAFE, PermissionDecision.DENY)
    fresh = PermissionPolicy(make_registry())
    assert fresh.evaluate("read_note").decision == PermissionDecision.ALLOW

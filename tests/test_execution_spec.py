"""
M4 step 2 — ExecutionSpec.

Covers deterministic construction, serialization, equality
of specs built from identical inputs, tool-less plans,
fail-closed risk summary, and required-field validation.
"""

import json

import pytest

from backend.core.execution_spec import (
    ExecutionSpec,
    SpecStep,
    build_execution_spec,
)
from backend.core.planner import PlannedStep, PlanningResult, PlanningSource
from backend.tools.registry import RiskLevel, ToolRegistry


@pytest.fixture
def registry():
    reg = ToolRegistry()
    reg.register(
        name="fs_read_file",
        description="read",
        category="filesystem",
        risk_level=RiskLevel.SAFE,
    )
    reg.register(
        name="fs_write_file",
        description="write",
        category="filesystem",
        risk_level=RiskLevel.SENSITIVE,
    )
    reg.register(
        name="rm_rf",
        description="danger",
        category="system",
        risk_level=RiskLevel.DANGEROUS,
    )
    return reg


def make_planning(steps=None, ready=True, request="do the thing"):
    return PlanningResult(
        request=request,
        ready=ready,
        task_title="Title",
        task_description="Description",
        steps=steps or [],
        assumptions=["a1"],
        source=PlanningSource.MODEL,
        planned_at="2026-01-01T00:00:00",
    )


# --------------------------------------------------------
# DETERMINISTIC CONSTRUCTION
# --------------------------------------------------------

def test_build_from_ready_planning(registry):
    planning = make_planning(
        [
            PlannedStep(description="read it", tool="fs_read_file",
                        params={"path": "/tmp/a"}),
        ]
    )

    spec = build_execution_spec(planning, task_id="t-1", registry=registry)

    assert spec.task_id == "t-1"
    assert spec.request == "do the thing"
    assert spec.planning_source == "MODEL"
    assert spec.step_count == 1
    assert spec.steps[0].tool == "fs_read_file"
    assert spec.steps[0].order == 0
    assert spec.steps[0].params == {"path": "/tmp/a"}


def test_identical_inputs_produce_equal_specs(registry):
    planning = make_planning(
        [
            PlannedStep(description="one", tool="fs_read_file"),
            PlannedStep(description="two", tool="fs_write_file"),
        ]
    )

    first = build_execution_spec(planning, task_id="t-1", registry=registry)
    second = build_execution_spec(planning, task_id="t-1", registry=registry)

    assert first == second
    assert first.to_dict() == second.to_dict()


def test_step_order_is_sequential_even_when_steps_dropped(registry):
    planning = make_planning(
        [
            PlannedStep(description="advisory", tool=None),
            PlannedStep(description="one", tool="fs_read_file"),
            PlannedStep(description="advisory too", tool="   "),
            PlannedStep(description="two", tool="fs_read_file"),
        ]
    )

    spec = build_execution_spec(planning, task_id="t-2", registry=registry)

    assert [step.order for step in spec.steps] == [0, 1]
    assert [step.tool for step in spec.steps] == [
        "fs_read_file",
        "fs_read_file",
    ]


def test_spec_is_immutable(registry):
    spec = build_execution_spec(make_planning(), task_id="t-3", registry=registry)

    with pytest.raises(Exception):
        spec.task_id = "hacked"

    with pytest.raises(Exception):
        spec.steps = ()


def test_spec_step_defaults():
    step = SpecStep(order=0, description="d", tool="fs_read_file")

    assert step.params == {}
    assert step.to_dict()["params"] == {}


# --------------------------------------------------------
# SERIALIZATION
# --------------------------------------------------------

def test_to_dict_is_json_serializable(registry):
    spec = build_execution_spec(
        make_planning([PlannedStep(description="x", tool="fs_read_file")]),
        task_id="t-4",
        registry=registry,
        skill_name="task-breakdown",
        skill_risk_level=RiskLevel.SAFE,
        provider="gemini",
        model="gemini-flash",
        memory_context="some memory",
        document_id="doc-9",
    )

    payload = json.dumps(spec.to_dict(), sort_keys=True)

    decoded = json.loads(payload)

    assert decoded["task_id"] == "t-4"
    assert decoded["skill"] == "task-breakdown"
    assert decoded["provider"] == "gemini"
    assert decoded["steps"][0]["tool"] == "fs_read_file"


def test_to_dict_field_set_is_stable(registry):
    spec = build_execution_spec(make_planning(), task_id="t-5", registry=registry)

    assert set(spec.to_dict()) == {
        "task_id",
        "request",
        "planning_source",
        "steps",
        "skill",
        "skill_risk_level",
        "provider",
        "model",
        "context_refs",
        "assumptions",
        "risk_level",
        "approval_required",
        "expected_output",
        "created_at",
    }


# --------------------------------------------------------
# TOOL-LESS PLANS
# --------------------------------------------------------

def test_tool_only_plan_is_not_executable_but_valid(registry):
    spec = build_execution_spec(make_planning(), task_id="t-6", registry=registry)

    assert spec.steps == ()
    assert spec.has_executable_steps is False
    assert spec.risk_level == RiskLevel.SAFE.value
    assert spec.approval_required is False


def test_all_advisory_steps_drop_to_zero_executable(registry):
    planning = make_planning(
        [
            PlannedStep(description="think", tool=None),
            PlannedStep(description="reflect", tool=None),
        ]
    )

    spec = build_execution_spec(planning, task_id="t-7", registry=registry)

    assert spec.step_count == 0
    assert spec.to_dict()["steps"] == []


# --------------------------------------------------------
# RISK SUMMARY (single risk model, fail closed)
# --------------------------------------------------------

def test_risk_level_is_highest_across_steps(registry):
    planning = make_planning(
        [
            PlannedStep(description="a", tool="fs_read_file"),
            PlannedStep(description="b", tool="fs_write_file"),
        ]
    )

    spec = build_execution_spec(planning, task_id="t-8", registry=registry)

    assert spec.risk_level == RiskLevel.SENSITIVE.value
    assert spec.approval_required is True


def test_dangerous_step_marks_dangerous_and_not_auto_approvable(registry):
    planning = make_planning(
        [PlannedStep(description="boom", tool="rm_rf")]
    )

    spec = build_execution_spec(planning, task_id="t-9", registry=registry)

    assert spec.risk_level == RiskLevel.DANGEROUS.value
    # DANGEROUS is denied outright by the policy, not queued
    # for approval.
    assert spec.approval_required is False


def test_unknown_tool_is_fail_closed(registry):
    planning = make_planning(
        [PlannedStep(description="mystery", tool="not_registered")]
    )

    spec = build_execution_spec(planning, task_id="t-10", registry=registry)

    assert spec.risk_level == RiskLevel.DANGEROUS.value


def test_missing_registry_cannot_claim_safety(registry):
    planning = make_planning(
        [PlannedStep(description="a", tool="fs_read_file")]
    )

    spec = build_execution_spec(planning, task_id="t-11", registry=None)

    assert spec.risk_level == RiskLevel.DANGEROUS.value


# --------------------------------------------------------
# CONTEXT REFERENCES (references only, never content)
# --------------------------------------------------------

def test_context_refs_record_presence_not_payload(registry):
    secret_document = "full text of the uploaded contract " * 50

    spec = build_execution_spec(
        make_planning(),
        task_id="t-12",
        registry=registry,
        memory_context="user prefers concise answers",
        document_context=secret_document,
        document_id="doc-1",
    )

    assert "memory" in spec.context_refs
    assert "document-context" in spec.context_refs
    assert "document:doc-1" in spec.context_refs
    assert secret_document not in json.dumps(spec.to_dict())
    assert "concise" not in json.dumps(spec.to_dict())


def test_absent_context_yields_no_refs(registry):
    spec = build_execution_spec(make_planning(), task_id="t-13", registry=registry)

    assert spec.context_refs == ()


# --------------------------------------------------------
# SKILL FIELDS
# --------------------------------------------------------

def test_selected_skill_is_recorded(registry):
    spec = build_execution_spec(
        make_planning(),
        task_id="t-14",
        registry=registry,
        skill_name="task-breakdown",
        skill_risk_level=RiskLevel.SAFE,
    )

    assert spec.skill == "task-breakdown"
    assert spec.skill_risk_level == "SAFE"


def test_no_skill_matched_keeps_skill_none(registry):
    spec = build_execution_spec(make_planning(), task_id="t-15", registry=registry)

    assert spec.skill is None
    assert spec.skill_risk_level is None


# --------------------------------------------------------
# VALIDATION
# --------------------------------------------------------

def test_empty_task_id_rejected(registry):
    with pytest.raises(ValueError, match="task_id"):
        build_execution_spec(make_planning(), task_id="   ", registry=registry)


def test_blank_task_id_rejected():
    with pytest.raises(ValueError, match="task_id"):
        ExecutionSpec(
            task_id="",
            request="r",
            planning_source="MODEL",
        )


def test_blank_request_rejected():
    with pytest.raises(ValueError, match="request"):
        ExecutionSpec(
            task_id="t",
            request="  ",
            planning_source="MODEL",
        )


def test_blank_planning_source_rejected():
    with pytest.raises(ValueError, match="planning_source"):
        ExecutionSpec(task_id="t", request="r", planning_source="")


def test_unready_planning_cannot_become_a_spec(registry):
    planning = PlanningResult(
        request="vague",
        ready=False,
        questions=["what?"],
        source=PlanningSource.MODEL,
    )

    with pytest.raises(ValueError, match="unready"):
        build_execution_spec(planning, task_id="t-16", registry=registry)


def test_missing_planning_rejected(registry):
    with pytest.raises(ValueError):
        build_execution_spec(None, task_id="t-17", registry=registry)


def test_non_string_task_id_rejected():
    with pytest.raises(ValueError, match="task_id"):
        ExecutionSpec(task_id=123, request="r", planning_source="MODEL")

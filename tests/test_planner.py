"""
Focused tests for the M3-H Step 3 Planner.

Covers the eight required cases:
1. clear request -> no clarification
2. clarification genuinely required
3. unnecessary questions avoided
4. exactly 7-question ceiling allowed
5. >7 model questions capped to 7
6. sensible/default planning
7. malformed planner output
8. Planner never executes tools

The gateway is always a fake — no network, no provider.
"""

import asyncio
import json

from backend.core.planner import (
    ABSOLUTE_MAX_QUESTIONS,
    PlannedStep,
    Planner,
    PlanningSource,
)


def plan_sync(planner: Planner, request: str, **kwargs):
    return asyncio.run(planner.plan(request, **kwargs))


class FakeGateway:
    """
    Duck-typed stand-in for the Orchestrator gateway.
    Records generate() calls, returns a canned response.
    """

    def __init__(self, response):
        self._response = response
        self.generate_calls = []

    async def generate(self, **kwargs):
        self.generate_calls.append(kwargs)
        return self._response


class StrictGateway:
    """
    Gateway that fails loudly on ANY attribute access
    other than generate() — used to prove the Planner
    touches nothing else on the gateway.
    """

    def __init__(self, response):
        self._response = response
        self.generate_calls = []

    def __getattr__(self, name):
        raise AssertionError(
            f"Planner accessed gateway attribute {name!r}; "
            "only generate() is allowed."
        )

    async def generate(self, **kwargs):
        self.generate_calls.append(kwargs)
        return self._response


class ExplodingExecutor:
    """Sentinel: if the Planner ever executes, this fires."""

    def __call__(self, *args, **kwargs):
        raise AssertionError("Planner must never execute tools")

    def __getattr__(self, name):
        raise AssertionError(
            f"Planner touched executor attribute {name!r}"
        )


def model_plan_response(**overrides) -> str:
    """A well-formed planner JSON payload from the model."""

    payload = {
        "enough_information": True,
        "task_title": "Summarize the project notes",
        "task_description": "Read the notes and summarize them.",
        "steps": [
            {
                "description": "Read the notes file",
                "tool": "fs_read_file",
                "params": {"path": "/tmp/notes.txt"},
            }
        ],
        "assumptions": ["Notes are stored in /tmp/notes.txt"],
        "clarifying_questions": [],
    }
    payload.update(overrides)
    return json.dumps(payload)


def clarification_response(questions, **overrides) -> str:
    return model_plan_response(
        enough_information=False,
        task_title=None,
        task_description=None,
        steps=[],
        clarifying_questions=questions,
        **overrides,
    )


# ============================================================
# 1. Clear request -> no clarification
# ============================================================

def test_clear_request_produces_ready_plan_without_questions():
    gateway = FakeGateway(model_plan_response())
    result = plan_sync(
        Planner(gateway),
        "Summarize my project notes stored in /tmp/notes.txt",
    )

    assert result.ready is True
    assert result.source is PlanningSource.MODEL
    assert result.parse_ok is True
    assert result.questions == []
    assert result.task_title == "Summarize the project notes"
    assert result.task_description == (
        "Read the notes and summarize them."
    )
    assert len(result.steps) == 1
    assert result.steps[0].tool == "fs_read_file"
    assert result.steps[0].params == {"path": "/tmp/notes.txt"}
    # Exactly one gateway call, through generate() only.
    assert len(gateway.generate_calls) == 1


# ============================================================
# 2. Clarification genuinely required
# ============================================================

def test_unclear_request_requires_clarification():
    gateway = FakeGateway(
        clarification_response(
            [
                "Which notes do you mean?",
                "Where are they saved?",
            ]
        )
    )
    result = plan_sync(Planner(gateway), "summarize the notes")

    assert result.ready is False
    assert result.task_title is None
    assert result.steps == []
    assert result.questions == [
        "Which notes do you mean?",
        "Where are they saved?",
    ]
    assert result.parse_ok is True
    assert result.source is PlanningSource.MODEL


# ============================================================
# 3. Unnecessary questions avoided
# ============================================================

def test_questions_dropped_when_a_complete_plan_exists():
    gateway = FakeGateway(
        model_plan_response(
            clarifying_questions=[
                "Which output format do you want?",
                "How long should the summary be?",
            ]
        )
    )
    result = plan_sync(
        Planner(gateway),
        "Summarize my project notes stored in /tmp/notes.txt",
    )

    # A complete plan makes the questions unnecessary.
    assert result.ready is True
    assert result.questions == []
    assert any(
        "question" in assumption.lower()
        for assumption in result.assumptions
    )


def test_empty_and_duplicate_questions_are_filtered():
    gateway = FakeGateway(
        clarification_response(
            ["", "   ", None, "Which notes?", "Which notes?"]
        )
    )
    result = plan_sync(Planner(gateway), "summarize the notes")

    assert result.ready is False
    assert result.questions == ["Which notes?"]


# ============================================================
# 4. Exactly 7 questions allowed
# ============================================================

def test_exactly_seven_questions_are_allowed():
    questions = [f"Question {i}?" for i in range(1, 8)]
    gateway = FakeGateway(clarification_response(questions))
    result = plan_sync(Planner(gateway), "vague request")

    assert result.ready is False
    assert len(result.questions) == ABSOLUTE_MAX_QUESTIONS == 7
    assert result.questions == questions
    assert result.questions_truncated is False
    assert result.questions_dropped == 0


# ============================================================
# 5. More than 7 model questions capped to 7
# ============================================================

def test_more_than_seven_questions_capped_to_seven():
    questions = [f"Question {i}?" for i in range(1, 11)]  # 10
    gateway = FakeGateway(clarification_response(questions))
    result = plan_sync(Planner(gateway), "vague request")

    assert len(result.questions) == 7
    # First 7 kept (highest priority = model's own order);
    # nothing invented for the rest.
    assert result.questions == questions[:7]
    assert result.questions_truncated is True
    assert result.questions_dropped == 3


# ============================================================
# 6. Sensible/default planning
# ============================================================

def test_deterministic_default_planning_without_model():
    result = plan_sync(
        Planner(),
        "Summarize the architecture assessment document in docs/",
    )

    assert result.ready is True
    assert result.source is PlanningSource.DETERMINISTIC
    assert result.parse_ok is True
    assert result.questions == []
    assert result.task_title == (
        "Summarize the architecture assessment document in docs/"
    )
    assert result.task_description == (
        "Summarize the architecture assessment document in docs/"
    )
    assert any(
        "deterministic" in assumption.lower()
        for assumption in result.assumptions
    )


def test_too_short_request_asks_single_clarification():
    result = plan_sync(Planner(), "help")

    assert result.ready is False
    assert len(result.questions) == 1
    assert result.source is PlanningSource.DETERMINISTIC


def test_empty_request_asks_single_clarification():
    result = plan_sync(Planner(), "   ")

    assert result.ready is False
    assert len(result.questions) == 1


# ============================================================
# 7. Malformed planner output
# ============================================================

def test_malformed_model_output_falls_back_safely():
    gateway = FakeGateway(
        "Sure! I think we should maybe read some stuff "
        "first and then perhaps summarize things."
    )
    result = plan_sync(
        Planner(gateway),
        "Summarize the quarterly report in reports/q3.pdf",
    )

    assert result.parse_ok is False
    assert result.source is PlanningSource.FALLBACK_MALFORMED
    assert result.raw_response == (
        "Sure! I think we should maybe read some stuff "
        "first and then perhaps summarize things."
    )
    assert any(
        "malformed" in assumption.lower()
        for assumption in result.assumptions
    )
    # Falls back to a deterministic plan for a substantive
    # request instead of crashing or inventing content.
    assert result.ready is True
    assert result.task_title


def test_fenced_but_invalid_json_falls_back_safely():
    gateway = FakeGateway("```json\n{not valid json at all}\n```")
    result = plan_sync(Planner(gateway), "Plan my week in detail")

    assert result.parse_ok is False
    assert result.source is PlanningSource.FALLBACK_MALFORMED
    assert result.raw_response == (
        "```json\n{not valid json at all}\n```"
    )


def test_gateway_exception_falls_back_safely():
    class BrokenGateway:
        async def generate(self, **kwargs):
            raise RuntimeError("gateway down")

    result = plan_sync(
        Planner(BrokenGateway()),
        "Summarize the quarterly report in reports/q3.pdf",
    )

    assert result.parse_ok is False
    assert result.source is PlanningSource.FALLBACK_ERROR
    assert result.ready is True
    assert any(
        "gateway failed" in assumption.lower()
        for assumption in result.assumptions
    )


# ============================================================
# 8. Planner never executes tools
# ============================================================

def test_planner_never_executes_tools_or_bypasses_policy():
    gateway = StrictGateway(
        model_plan_response()  # plan explicitly references a tool
    )
    executor = ExplodingExecutor()

    planner = Planner(gateway)

    # No execution machinery exists on the Planner at all.
    assert not hasattr(planner, "_registry")
    assert not hasattr(planner, "_executor")
    assert not hasattr(planner, "_permissions")
    assert not hasattr(planner, "execute")

    result = plan_sync(
        planner,
        "Read /tmp/notes.txt and summarize it",
    )

    assert result.ready is True

    # Steps are inert data, never callables.
    for step in result.steps:
        assert isinstance(step, PlannedStep)
        assert not callable(step)

    # The result is pure audit data, JSON-safe.
    json.dumps(result.to_dict())

    assert len(gateway.generate_calls) == 1

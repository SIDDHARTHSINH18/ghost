"""
M4 step 6 — memory bridge (Reflection -> Memory).

ReflectionEngine has flagged ``memory_write_recommended`` since
M3-G with no consumer. These tests pin the consumer:

- only a recommended reflection is stored
- stored text is built from reflection fields only, and is
  length-bounded (memory is replayed into later prompts)
- the existing MemoryService stays the only writer, including
  its duplicate handling
- a store failure is reported and audited, and never turns a
  successful task into a failed one
"""

import pytest

from backend.agents.memory_bridge import (
    MAX_LIST_ITEMS,
    MAX_MEMORY_CHARS,
    MemoryBridge,
)
from backend.audit.log import AuditLog, AuditStage
from backend.core.memory import MemoryService
from backend.core.task import Task, TaskStatus
from backend.reflection.engine import ReflectionEngine
from backend.reflection.result import (
    ReflectionFailure,
    ReflectionOutcome,
    ReflectionResult,
)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def memory(tmp_path):
    return MemoryService(storage_path=str(tmp_path / "memory.json"))


@pytest.fixture
def audit(tmp_path):
    return AuditLog(storage_path=str(tmp_path / "audit.jsonl"))


@pytest.fixture
def bridge(memory, audit):
    return MemoryBridge(memory=memory, audit=audit)


def failed_reflection(**overrides) -> ReflectionResult:
    data = dict(
        task_id="task-1",
        outcome=ReflectionOutcome.FAILED,
        succeeded=False,
        summary="1 of 2 steps failed.",
        failures=[
            ReflectionFailure(
                step_id="s-1",
                tool_name="fs_read_file",
                kind="tool_error",
                detail="File not found.",
            )
        ],
        causes=["the planned path does not exist"],
        lessons=["confirm the path before reading"],
        recommended_next_action="ask the user for the real path",
        confidence=0.8,
        memory_write_recommended=True,
    )
    data.update(overrides)
    return ReflectionResult(**data)


def successful_reflection() -> ReflectionResult:
    return ReflectionResult(
        task_id="task-1",
        outcome=ReflectionOutcome.SUCCEEDED,
        succeeded=True,
        summary="Both steps completed.",
        failures=[],
        causes=[],
        lessons=[],
        recommended_next_action="",
        confidence=0.9,
        memory_write_recommended=False,
    )


def make_task(title="Read the notes", description="read it"):
    return Task(
        id="task-1",
        title=title,
        description=description,
    )


# ============================================================
# ONLY RECOMMENDED WRITES
# ============================================================

def test_successful_task_stores_nothing(bridge, memory):
    report = bridge.record_outcome(make_task(), successful_reflection())

    assert report.written is False
    assert report.status == "skipped"
    assert memory.get_all() == []


def test_missing_reflection_stores_nothing(bridge, memory):
    report = bridge.record_outcome(make_task(), None)

    assert report.status == "skipped"
    assert memory.get_all() == []


def test_recommendation_without_evidence_is_ignored(bridge, memory):
    reflection = failed_reflection(failures=[])

    report = bridge.record_outcome(make_task(), reflection)

    assert report.status == "skipped"
    assert memory.get_all() == []


def test_denied_operation_is_stored(bridge, memory):
    reflection = failed_reflection(
        outcome=ReflectionOutcome.DENIED,
        summary="The step was denied by policy.",
    )

    report = bridge.record_outcome(make_task(), reflection)

    assert report.written is True
    assert "DENIED" in report.content


def test_partial_outcome_is_stored(bridge, memory):
    report = bridge.record_outcome(
        make_task(),
        failed_reflection(outcome=ReflectionOutcome.PARTIAL),
    )

    assert report.written is True


# ============================================================
# CONTENT: DERIVED, BOUNDED, USEFUL
# ============================================================

def test_content_carries_only_reflection_fields(bridge, memory):
    task = make_task(title="Summarise the report")

    report = bridge.record_outcome(task, failed_reflection())

    record = memory.get_all()[0]

    assert "Summarise the report" in record["content"]
    assert "FAILED" in record["content"]
    assert "1 of 2 steps failed." in record["content"]
    assert "Cause: the planned path does not exist" in record["content"]
    assert "Lesson: confirm the path before reading" in record["content"]
    assert "Next time: ask the user for the real path" in record["content"]


def test_content_is_bounded(bridge, memory):
    reflection = failed_reflection(
        summary="z" * 5000,
        causes=["long cause " * 200],
    )

    report = bridge.record_outcome(make_task(), reflection)

    assert len(report.content) <= MAX_MEMORY_CHARS + 3
    assert memory.get_all()[0]["content"] == report.content


def test_lists_are_capped(bridge, memory):
    reflection = failed_reflection(
        causes=[f"cause {index}" for index in range(20)],
        lessons=[f"lesson {index}" for index in range(20)],
    )

    report = bridge.record_outcome(make_task(), reflection)

    assert report.content.count("cause ") == MAX_LIST_ITEMS
    assert report.content.count("lesson ") == MAX_LIST_ITEMS


def test_memory_metadata_records_provenance(bridge, memory):
    bridge.record_outcome(make_task(), failed_reflection())

    record = memory.get_all()[0]

    assert record["type"] == "task_outcome"
    assert record["source"] == "reflection"
    assert record["importance"] == pytest.approx(0.7)
    assert record["confidence"] == pytest.approx(0.8)
    assert "reflection" in record["tags"]
    assert "failed" in record["tags"]
    assert "tool:fs_read_file" in record["tags"]
    assert record["metadata"]["task_id"] == "task-1"
    assert record["metadata"]["outcome"] == "FAILED"
    assert record["metadata"]["tools"] == ["fs_read_file"]


@pytest.mark.parametrize(
    ("outcome", "importance"),
    [
        (ReflectionOutcome.FAILED, 0.7),
        (ReflectionOutcome.PARTIAL, 0.6),
        (ReflectionOutcome.DENIED, 0.6),
    ],
)
def test_importance_follows_the_outcome(
    bridge,
    memory,
    outcome,
    importance,
):
    bridge.record_outcome(
        make_task(title=f"task {outcome.value}"),
        failed_reflection(outcome=outcome),
    )

    assert memory.get_all()[-1]["importance"] == pytest.approx(
        importance
    )


# ============================================================
# ONE MEMORY SYSTEM (reused store semantics)
# ============================================================

def test_repeated_identical_outcome_does_not_duplicate(
    bridge,
    memory,
):
    task = make_task()

    first = bridge.record_outcome(task, failed_reflection())
    second = bridge.record_outcome(task, failed_reflection())

    assert first.written is True
    assert len(memory.get_all()) == 1

    # add_memory upgrades the existing entry instead of adding a
    # second copy; the bridge reports the surviving id.
    assert second.memory_id == memory.get_all()[0]["id"]


def test_bridge_does_not_touch_the_task(bridge):
    task = make_task()

    before = (task.status, task.result, task.error, task.reflection)

    bridge.record_outcome(task, failed_reflection())

    assert (task.status, task.result, task.error, task.reflection) == (
        before
    )


def test_project_scoping_is_passed_through(memory, audit):
    scoped = MemoryBridge(memory=memory, audit=audit, project="ghost")

    scoped.record_outcome(make_task(), failed_reflection())

    assert memory.get_all()[0]["project"] == "ghost"


# ============================================================
# FAILURES NEVER BREAK THE TASK
# ============================================================

def test_store_error_is_reported_not_raised(memory, audit, monkeypatch):
    bridge = MemoryBridge(memory=memory, audit=audit)

    def explode(**kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(memory, "add_memory", explode)

    report = bridge.record_outcome(make_task(), failed_reflection())

    assert report.written is False
    assert report.status == "failed"
    assert report.error.startswith("OSError: disk full")

    rows = audit.read(stage=AuditStage.MEMORY)

    assert rows[0]["event"] == "failed"
    assert rows[0]["data"]["error"].startswith("OSError: disk full")


def test_empty_store_result_is_reported(memory, audit, monkeypatch):
    bridge = MemoryBridge(memory=memory, audit=audit)

    monkeypatch.setattr(memory, "add_memory", lambda **kwargs: {})

    report = bridge.record_outcome(make_task(), failed_reflection())

    assert report.status == "failed"
    assert "no memory id" in report.error


def test_audit_cannot_block_the_write(memory, tmp_path):
    # A directory as the storage path makes every append fail with
    # OSError, exactly like a full or read-only disk would.
    broken_audit = AuditLog(storage_path=str(tmp_path))

    bridge = MemoryBridge(memory=memory, audit=broken_audit)

    report = bridge.record_outcome(make_task(), failed_reflection())

    assert report.written is True
    assert len(memory.get_all()) == 1


def test_bridge_without_audit_still_writes(memory):
    report = MemoryBridge(memory=memory).record_outcome(
        make_task(),
        failed_reflection(),
    )

    assert report.written is True


# ============================================================
# AUDIT RECORD
# ============================================================

def test_every_call_emits_exactly_one_memory_row(bridge, audit):
    bridge.record_outcome(make_task(), failed_reflection())
    bridge.record_outcome(make_task(), successful_reflection())

    rows = audit.read(stage=AuditStage.MEMORY)

    assert [row["event"] for row in rows] == ["written", "skipped"]
    assert rows[0]["task_id"] == "task-1"
    assert rows[0]["status"] == "FAILED"
    assert rows[0]["data"]["memory_id"]


def test_written_row_carries_the_stored_text(bridge, audit):
    report = bridge.record_outcome(make_task(), failed_reflection())

    row = audit.read(stage=AuditStage.MEMORY)[0]

    assert row["data"]["written"] is True
    assert row["data"]["content"] == report.content


def test_a_secret_in_a_lesson_never_reaches_the_audit_file(
    bridge,
    audit,
):
    bridge.record_outcome(
        make_task(),
        failed_reflection(
            lessons=["rotate the leaked api_key: nvapi-SECRETSECRET123"],
        ),
    )

    raw = open(audit.storage_path, encoding="utf-8").read()

    assert "nvapi-SECRETSECRET123" not in raw
    assert "[redacted]" in raw


# ============================================================
# INTEGRATION: real engine output feeds the bridge
# ============================================================

def test_real_reflection_of_a_failed_task_is_memorised(memory, audit):
    from backend.core.agent_services import (
        agent,
        reflection_engine,
    )

    task = Task(title="Delete everything", description="rm -rf /")

    # Unknown tool -> fail-closed DENY -> real DENIED reflection.
    execution = agent.execute(task, "rm_rf", {"path": "/"})

    assert execution.status is TaskStatus.FAILED

    reflection = reflection_engine.reflect_on_task(
        task,
        execution_result=execution,
    )

    assert reflection.memory_write_recommended is True

    report = MemoryBridge(memory=memory, audit=audit).record_outcome(
        task,
        reflection,
    )

    assert report.written is True
    assert "DENIED" in report.content

    stored = memory.get_all()[0]

    assert stored["source"] == "reflection"
    assert stored["metadata"]["task_id"] == task.id
    assert audit.read(task_id=task.id, stage=AuditStage.MEMORY)

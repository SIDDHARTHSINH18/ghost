"""
M4 step 1 — append-only audit log.

Covers: append/read, ordering, task correlation,
append-only surface, environment path override, secret
sanitization, and JSON serialization.
"""

import json
import os

import pytest

from backend.audit import AUDIT_PATH_ENV, AuditLog, AuditStage


@pytest.fixture
def audit_file(tmp_path):
    return str(tmp_path / "audit.jsonl")


@pytest.fixture
def log(audit_file):
    return AuditLog(storage_path=audit_file)


# --------------------------------------------------------
# APPEND / READ
# --------------------------------------------------------

def test_append_returns_row_with_required_fields(log):
    row = log.append(
        task_id="task-1",
        stage=AuditStage.PLANNED,
        data={"ready": True},
        event="planner",
        status="MODEL",
    )

    assert row is not None
    assert row["task_id"] == "task-1"
    assert row["stage"] == "planned"
    assert row["event"] == "planner"
    assert row["status"] == "MODEL"
    assert row["data"] == {"ready": True}
    assert row["timestamp"]
    assert isinstance(row["sequence"], int)


def test_read_round_trips_appended_rows(log):
    log.append("task-a", AuditStage.SPEC, {"step_count": 2})
    log.append("task-a", AuditStage.TOOL, {"tool": "fs_read_file"})

    rows = log.read()

    assert len(rows) == 2
    assert [row["stage"] for row in rows] == ["spec", "tool"]


def test_append_persists_one_json_object_per_line(log, audit_file):
    log.append("task-x", AuditStage.RESULT, {"ok": True})
    log.append("task-x", AuditStage.MEMORY, {"written": False})

    with open(audit_file, "r", encoding="utf-8") as handle:
        lines = [line for line in handle.read().splitlines() if line]

    assert len(lines) == 2

    for line in lines:
        parsed = json.loads(line)
        assert isinstance(parsed, dict)


# --------------------------------------------------------
# ORDERING
# --------------------------------------------------------

def test_rows_are_returned_in_append_order(log):
    for index in range(6):
        log.append(
            "task-order",
            AuditStage.TOOL,
            {"index": index},
            event=f"step-{index}",
        )

    rows = log.read(task_id="task-order")

    assert [row["event"] for row in rows] == [
        f"step-{index}" for index in range(6)
    ]


def test_sequence_numbers_increase_monotonically(log):
    rows = [
        log.append("task-seq", AuditStage.TOOL, {"i": i})
        for i in range(4)
    ]

    sequences = [row["sequence"] for row in rows]

    assert sequences == sorted(sequences)
    assert len(set(sequences)) == len(sequences)


def test_limit_keeps_most_recent_rows_in_order(log):
    for index in range(5):
        log.append("task-lim", AuditStage.TOOL, {"i": index})

    rows = log.read(task_id="task-lim", limit=2)

    assert [row["data"]["i"] for row in rows] == [3, 4]


# --------------------------------------------------------
# TASK CORRELATION
# --------------------------------------------------------

def test_read_filters_by_task_id(log):
    log.append("task-1", AuditStage.PLANNED, {"a": 1})
    log.append("task-2", AuditStage.PLANNED, {"b": 2})
    log.append("task-1", AuditStage.RESULT, {"c": 3})

    assert len(log.read(task_id="task-1")) == 2
    assert len(log.read(task_id="task-2")) == 1
    assert len(log.read(task_id="missing")) == 0
    assert len(log.read()) == 3


def test_read_filters_by_stage(log):
    log.append("task-1", AuditStage.SKILL, {"skill": None})
    log.append("task-1", AuditStage.SKILL, {"skill": "x"})
    log.append("task-1", AuditStage.TOOL, {"tool": "y"})

    assert len(log.read(task_id="task-1", stage=AuditStage.SKILL)) == 2
    assert len(log.read(task_id="task-1", stage="tool")) == 1


def test_task_id_may_be_absent_for_pre_task_stages(log):
    row = log.append(None, AuditStage.REQUEST, {"text": "hello"})

    assert row["task_id"] is None
    assert log.read(task_id=None) == [row]


def test_count_reports_stored_rows(log):
    assert log.count() == 0

    log.append("task-1", AuditStage.PLANNED, {})
    log.append("task-1", AuditStage.SPEC, {})

    assert log.count() == 2


# --------------------------------------------------------
# APPEND-ONLY SURFACE
# --------------------------------------------------------

def test_log_exposes_no_update_or_delete_api(log):
    for forbidden in ("update", "delete", "remove", "truncate", "clear", "write"):
        assert not hasattr(log, forbidden), (
            f"AuditLog must be append-only but exposes {forbidden}()"
        )


def test_appending_never_rewrites_existing_rows(log, audit_file):
    log.append("task-1", AuditStage.PLANNED, {"v": 1})

    with open(audit_file, "r", encoding="utf-8") as handle:
        first_content = handle.read()

    log.append("task-2", AuditStage.PLANNED, {"v": 2})

    with open(audit_file, "r", encoding="utf-8") as handle:
        second_content = handle.read()

    assert second_content.startswith(first_content)
    assert len(second_content) > len(first_content)


def test_second_instance_continues_the_same_file(tmp_path, audit_file):
    AuditLog(storage_path=audit_file).append("task-1", AuditStage.TOOL, {})
    resumed = AuditLog(storage_path=audit_file)
    row = resumed.append("task-1", AuditStage.TOOL, {})

    assert resumed.count() == 2
    assert row["sequence"] == 2


# --------------------------------------------------------
# ENVIRONMENT PATH OVERRIDE
# --------------------------------------------------------

def test_storage_path_argument_wins_over_env(tmp_path, monkeypatch, audit_file):
    elsewhere = str(tmp_path / "env-audit.jsonl")
    monkeypatch.setenv(AUDIT_PATH_ENV, elsewhere)

    log = AuditLog(storage_path=audit_file)
    log.append("task-1", AuditStage.TOOL, {})

    assert os.path.exists(audit_file)
    assert not os.path.exists(elsewhere)


def test_env_var_redirects_the_store(tmp_path, monkeypatch):
    elsewhere = tmp_path / "custom" / "audit.jsonl"
    monkeypatch.setenv(AUDIT_PATH_ENV, str(elsewhere))

    log = AuditLog()

    assert log.storage_path == os.path.abspath(str(elsewhere))

    log.append("task-1", AuditStage.TOOL, {})

    assert elsewhere.exists()


def test_default_path_lives_in_backend_data_not_packaged_assets(monkeypatch):
    monkeypatch.delenv(AUDIT_PATH_ENV, raising=False)

    log = AuditLog(storage_path=None)

    # No env override: default is the backend data directory,
    # alongside memory.json — never inside frontend/ or
    # desktop/ build output.
    normal = log.storage_path.replace("\\", "/")

    assert normal.endswith("backend/data/audit.jsonl")
    assert "desktop" not in normal
    assert "frontend" not in normal


# --------------------------------------------------------
# SENSITIVE DATA
# --------------------------------------------------------

def test_forbidden_keys_are_redacted_at_any_depth(log):
    row = log.append(
        "task-1",
        AuditStage.MODEL,
        {
            "api_key": "super-secret",
            "nested": {"Authorization": "Bearer abc123", "keep": 1},
            "items": [{"password": "hunter2"}],
        },
    )

    assert row["data"]["api_key"] == "[redacted]"
    assert row["data"]["nested"]["Authorization"] == "[redacted]"
    assert row["data"]["nested"]["keep"] == 1
    assert row["data"]["items"][0]["password"] == "[redacted]"


def test_secrets_inside_free_text_are_redacted(log):
    row = log.append(
        "task-1",
        AuditStage.MODEL,
        {
            "raw": (
                "request failed: api_key = nvapi-ABCDEF123456 "
                "please retry"
            )
        },
    )

    text = row["data"]["raw"]

    assert "nvapi-ABCDEF123456" not in text
    assert "ABCDEF123456" not in text
    assert "[redacted]" in text


def test_bare_provider_key_is_redacted_without_assignment(log):
    row = log.append(
        "task-1",
        AuditStage.ERROR,
        {"detail": "upstream rejected sk-XYZ123456789"},
    )

    assert "sk-XYZ123456789" not in row["data"]["detail"]


def test_long_raw_output_is_truncated(log):
    payload = "x" * 9000

    row = log.append("task-1", AuditStage.PLANNED, {"raw_response": payload})

    stored = row["data"]["raw_response"]

    assert len(stored) < len(payload)
    assert "[truncated" in stored


def test_depth_and_size_are_bounded(log):
    deep = current = {}

    for _ in range(20):
        current["next"] = current = {}

    big = {"items": list(range(500))}

    row = log.append("task-1", AuditStage.RESULT, {"deep": deep, **big})

    assert isinstance(row["data"], dict)
    assert len(row["data"]["items"]) <= 50


# --------------------------------------------------------
# SERIALIZATION
# --------------------------------------------------------

def test_rows_are_json_serializable_with_exotic_values(log):
    class Opaque:
        def __str__(self):
            return "opaque-value"

    row = log.append(
        "task-1",
        AuditStage.RESULT,
        {
            "enum": AuditStage.MEMORY,
            "obj": Opaque(),
            "tuple": (1, 2),
            "float": 1.5,
        },
    )

    line = json.dumps(row, ensure_ascii=False, default=str)

    assert json.loads(line)["data"]["enum"] == "memory"
    assert json.loads(line)["data"]["obj"] == "opaque-value"


def test_unparseable_lines_are_skipped_on_read(log, audit_file):
    log.append("task-1", AuditStage.TOOL, {})

    with open(audit_file, "a", encoding="utf-8") as handle:
        handle.write("this is not json\n")
        handle.write("\n")

    log.append("task-1", AuditStage.TOOL, {})

    assert len(log.read()) == 2


def test_read_on_missing_file_returns_empty(tmp_path):
    log = AuditLog(storage_path=str(tmp_path / "absent" / "audit.jsonl"))

    assert log.read() == []
    assert log.count() == 0


def test_append_survives_unwritable_target_without_raising(tmp_path):
    # A directory where a file must be written cannot be
    # opened for append: auditing must fail safe, not raise.
    blocked = tmp_path / "blocked"
    blocked.mkdir()

    log = AuditLog(storage_path=str(blocked))

    assert log.append("task-1", AuditStage.TOOL, {}) is None

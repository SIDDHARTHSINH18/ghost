"""Focused tests for M3-H6 safe filesystem tools."""

import os

import pytest

from backend.core import agent_services
from backend.core.task import Task, TaskStatus
from backend.permissions.policy import PermissionDecision
from backend.tools.builtin.fs import (
    ToolExecutionError,
    fs_file_exists,
    fs_list_directory,
    fs_read_file,
)
from backend.tools.registry import RiskLevel


def test_list_directory_returns_immediate_entries_in_name_order(tmp_path):
    (tmp_path / "zeta.txt").write_text("z", encoding="utf-8")
    (tmp_path / "alpha.txt").write_text("a", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "hidden.txt").write_text(
        "hidden", encoding="utf-8"
    )

    assert fs_list_directory({"path": str(tmp_path)}) == [
        "alpha.txt",
        "nested",
        "zeta.txt",
    ]


def test_list_directory_rejects_missing_file_relative_and_invalid_paths(tmp_path):
    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")

    for params in (
        {"path": str(tmp_path / "missing")},
        {"path": str(file_path)},
        {"path": "relative/path"},
        {},
        {"path": "  "},
        {"path": 123},
        None,
    ):
        with pytest.raises(ToolExecutionError):
            fs_list_directory(params)


def test_tools_reject_requested_symlinks_where_supported(tmp_path):
    target_dir = tmp_path / "target-dir"
    target_dir.mkdir()
    target_file = tmp_path / "target-file.txt"
    target_file.write_text("content", encoding="utf-8")
    dir_link = tmp_path / "dir-link"
    file_link = tmp_path / "file-link.txt"

    try:
        os.symlink(target_dir, dir_link, target_is_directory=True)
        os.symlink(target_file, file_link)
    except (NotImplementedError, OSError):
        pytest.skip("symbolic links are not supported by this test host")

    with pytest.raises(ToolExecutionError, match="symbolic link"):
        fs_list_directory({"path": str(dir_link)})
    with pytest.raises(ToolExecutionError, match="symbolic link"):
        fs_file_exists({"path": str(file_link)})


def test_file_exists_reports_regular_file_presence_and_validates_paths(tmp_path):
    file_path = tmp_path / "exists.txt"
    file_path.write_text("present", encoding="utf-8")

    assert fs_file_exists({"path": str(file_path)}) is True
    assert fs_file_exists({"path": str(tmp_path / "missing.txt")}) is False
    assert fs_file_exists({"path": str(tmp_path)}) is False

    for params in ({"path": "relative.txt"}, {}, {"path": ""}, None):
        with pytest.raises(ToolExecutionError):
            fs_file_exists(params)


def test_existing_fs_read_file_behavior_is_preserved(tmp_path):
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello", encoding="utf-8")

    assert fs_read_file({"path": str(file_path)}) == "hello"
    with pytest.raises(ToolExecutionError):
        fs_read_file({"path": str(tmp_path)})


def test_new_tools_are_registered_safe_and_execute_through_production_path(tmp_path):
    file_path = tmp_path / "present.txt"
    file_path.write_text("present", encoding="utf-8")

    for tool_name in ("fs_list_directory", "fs_file_exists"):
        metadata = agent_services.tool_registry.get_tool(tool_name)
        assert metadata.risk_level is RiskLevel.SAFE

    list_task = Task(title="List directory", description="d")
    list_result = agent_services.agent.execute(
        list_task,
        "fs_list_directory",
        {"path": str(tmp_path)},
    )
    assert list_result.decision is PermissionDecision.ALLOW
    assert list_result.status is TaskStatus.COMPLETED
    assert list_result.output == ["present.txt"]

    exists_task = Task(title="Check file", description="d")
    exists_result = agent_services.agent.execute(
        exists_task,
        "fs_file_exists",
        {"path": str(file_path)},
    )
    assert exists_result.decision is PermissionDecision.ALLOW
    assert exists_result.status is TaskStatus.COMPLETED
    assert exists_result.output is True


def test_unknown_tool_remains_rejected_before_production_execution():
    task = Task(title="Unknown", description="d")

    result = agent_services.agent.execute(
        task,
        "fs_not_a_real_tool",
        {},
    )

    assert result.decision is PermissionDecision.DENY
    assert result.status is TaskStatus.FAILED
    assert "Unknown tool" in result.error

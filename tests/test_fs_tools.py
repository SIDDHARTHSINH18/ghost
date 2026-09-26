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

    # A relative path is now resolved against the canonical
    # execution root: "relative.txt" is a valid reference to a
    # file that does not exist, so it reports False instead of
    # raising. Truly invalid parameters still raise.
    assert fs_file_exists({"path": "relative.txt"}) is False

    for params in ({}, {"path": ""}, None):
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


# ============================================================
# Centralized relative-path resolution (execution boundary)
# ============================================================

def test_dot_resolves_to_canonical_root(tmp_path, monkeypatch):
    """'.' must resolve to the canonical execution root, not 404."""

    (tmp_path / "alpha.txt").write_text("a", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    monkeypatch.setenv("ENMA_WORKSPACE_ROOT", str(tmp_path))

    assert fs_list_directory({"path": "."}) == [
        "alpha.txt",
        "sub",
    ]


def test_dot_slash_relative_paths_resolve_against_root(
    tmp_path, monkeypatch
):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "inner.txt").write_text(
        "i", encoding="utf-8"
    )
    (tmp_path / "top.txt").write_text("t", encoding="utf-8")
    monkeypatch.setenv("ENMA_WORKSPACE_ROOT", str(tmp_path))

    assert fs_list_directory({"path": "./sub"}) == ["inner.txt"]
    assert fs_file_exists({"path": "sub/inner.txt"}) is True
    assert fs_read_file({"path": "./top.txt"}) == "t"


def test_relative_traversal_above_root_is_rejected(
    tmp_path, monkeypatch
):
    outside = tmp_path / ".." / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    monkeypatch.setenv("ENMA_WORKSPACE_ROOT", str(tmp_path / "root"))
    (tmp_path / "root").mkdir()

    for bad in (
        "..",
        "../outside.txt",
        "sub/../../outside.txt",
        ".\..\outside.txt",
    ):
        with pytest.raises(
            ToolExecutionError, match="escapes the execution root"
        ):
            fs_list_directory({"path": bad})

    # The outside file was never read.
    assert "secret" in outside.read_text(encoding="utf-8")


def test_absolute_paths_are_preserved_unchanged(tmp_path, monkeypatch):
    """Pre-sanctioned absolute-path behavior must not change."""

    outside = tmp_path / "absolute-outside.txt"
    outside.write_text("reachable", encoding="utf-8")
    monkeypatch.setenv("ENMA_WORKSPACE_ROOT", str(tmp_path / "root"))
    (tmp_path / "root").mkdir()

    # An absolute path outside the workspace root remains
    # addressable exactly as before (permission policy still
    # gates every real execution).
    assert fs_read_file({"path": str(outside)}) == "reachable"
    assert fs_list_directory({"path": str(tmp_path)}) == [
        "absolute-outside.txt",
        "root",
    ]


def test_env_override_sets_the_canonical_root(tmp_path, monkeypatch):
    monkeypatch.setenv("ENMA_WORKSPACE_ROOT", str(tmp_path / "ws"))
    (tmp_path / "ws").mkdir()
    (tmp_path / "ws" / "here.txt").write_text("h", encoding="utf-8")

    assert fs_list_directory({"path": "."}) == ["here.txt"]

    monkeypatch.delenv("ENMA_WORKSPACE_ROOT")

    # Without the override the resolver falls back to the
    # repository root (never raises just for resolving).
    assert fs_file_exists({"path": "."}) is False

"""
GHOST — safe filesystem read tools (M3-H steps 1 and 6).

fs_read_file: read a local text file. Read-only.

Safety constraints, enforced HERE in code (treat params
as untrusted model output):
- path must be a non-empty absolute path string
- path must exist and be a regular file (no dirs, no
  device/symlink tricks via isfile + islink rejection)
- file size must be <= MAX_FILE_SIZE_BYTES
- decoded as UTF-8 with errors="replace" (never raises
  on binary junk; result is always deterministic text)
- no writing, no globbing, no traversal logic, no shell
"""

import os

from pathlib import Path

MAX_FILE_SIZE_BYTES = 1024 * 1024  # 1 MB


class ToolExecutionError(Exception):
    """Raised for any invalid/unreadable path so the
    Agent maps it to a FAILED task with this message."""


def _validated_absolute_path(params: dict, tool_name: str) -> tuple[str, Path]:
    """Validate the shared untrusted ``path`` parameter.

    The tools deliberately reject a symlink at the requested path rather
    than resolving it, so a caller cannot use these read-only tools to
    follow an indirect filesystem reference.
    """

    raw_path = params.get("path") if isinstance(params, dict) else None

    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ToolExecutionError(
            f"{tool_name} requires a 'path' parameter."
        )

    path = raw_path.strip()

    if not os.path.isabs(path):
        raise ToolExecutionError(
            f"Path must be absolute: '{path}'."
        )

    path_obj = Path(path)

    if path_obj.is_symlink():
        raise ToolExecutionError(
            f"Refusing to follow symbolic link: '{path}'."
        )

    return path, path_obj


def fs_read_file(params: dict) -> str:
    """
    Read one local text file.

    params: {"path": <absolute filesystem path>}
    Returns the decoded file contents.
    """

    raw_path = params.get("path") if isinstance(params, dict) else None

    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ToolExecutionError(
            "fs_read_file requires a 'path' parameter."
        )

    path = raw_path.strip()

    if not os.path.isabs(path):
        raise ToolExecutionError(
            f"Path must be absolute: '{path}'."
        )

    path_obj = Path(path)

    if path_obj.is_symlink():
        raise ToolExecutionError(
            f"Refusing to follow symbolic link: '{path}'."
        )

    if not path_obj.exists():
        raise ToolExecutionError(
            f"File not found: '{path}'."
        )

    if not path_obj.is_file():
        raise ToolExecutionError(
            f"Path is not a regular file: '{path}'."
        )

    try:
        size = path_obj.stat().st_size
    except OSError as error:
        raise ToolExecutionError(
            f"Cannot stat '{path}': {error.strerror}."
        )

    if size > MAX_FILE_SIZE_BYTES:
        raise ToolExecutionError(
            f"File too large ({size} bytes; limit "
            f"{MAX_FILE_SIZE_BYTES} bytes): '{path}'."
        )

    try:
        return path_obj.read_text(
            encoding="utf-8",
            errors="replace",
        )
    except OSError as error:
        raise ToolExecutionError(
            f"Cannot read '{path}': {error.strerror}."
        )


def fs_list_directory(params: dict) -> list[str]:
    """Return the immediate entries of one directory in name order.

    No entry is opened or traversed; only its name is returned. The
    requested directory itself must be an existing, non-symlink directory.
    """

    path, path_obj = _validated_absolute_path(
        params,
        "fs_list_directory",
    )

    if not path_obj.exists():
        raise ToolExecutionError(
            f"Directory not found: '{path}'."
        )

    if not path_obj.is_dir():
        raise ToolExecutionError(
            f"Path is not a directory: '{path}'."
        )

    try:
        return sorted(entry.name for entry in path_obj.iterdir())
    except OSError as error:
        raise ToolExecutionError(
            f"Cannot list directory '{path}': {error.strerror}."
        )


def fs_file_exists(params: dict) -> bool:
    """Report whether an absolute, non-symlink path is a regular file.

    Missing paths and non-file paths are normal ``False`` results. No file
    contents are opened or read.
    """

    _, path_obj = _validated_absolute_path(
        params,
        "fs_file_exists",
    )

    try:
        return path_obj.is_file()
    except OSError as error:
        raise ToolExecutionError(
            f"Cannot inspect path: {error.strerror}."
        )

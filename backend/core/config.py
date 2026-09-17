"""
GHOST — runtime configuration.

Resource/safety limits are read from the environment on
every call, so they can be changed via .env or system
environment without code changes, and tests can
monkeypatch them.

Deliberately ABSENT from this module: any limit on the
NUMBER of documents. Document count is unbounded; the
real constraints are file size, aggregate storage, and
processing serialization (docs/06-mvp-roadmap.md, M1).
"""

import os

from dataclasses import dataclass


DEFAULT_MAX_UPLOAD_MB = 50

DEFAULT_MAX_TOTAL_STORAGE_MB = 500

DEFAULT_ALLOWED_EXTENSIONS = ".pdf,.docx,.txt"


@dataclass(frozen=True)
class UploadLimits:

    max_upload_bytes: int

    max_total_storage_bytes: int

    allowed_extensions: tuple


def _env_int_mb(name: str, default_mb: int) -> int:
    """
    Read an MB value from the environment; invalid or
    negative values fall back to the default.
    """

    raw = os.getenv(name)

    if raw is None:
        return default_mb * 1024 * 1024

    try:
        value_mb = int(raw)
    except ValueError:
        return default_mb * 1024 * 1024

    if value_mb < 0:
        return default_mb * 1024 * 1024

    return value_mb * 1024 * 1024


def get_upload_limits() -> UploadLimits:
    """
    Current upload limits from the environment.

    GHOST_MAX_UPLOAD_MB          — per-file size cap
    GHOST_MAX_TOTAL_STORAGE_MB   — aggregate cap across all
                                   uploaded documents
    GHOST_ALLOWED_EXTENSIONS     — comma/semicolon separated,
                                   e.g. ".pdf,.docx,.txt"
    """

    max_upload_bytes = _env_int_mb(
        "GHOST_MAX_UPLOAD_MB",
        DEFAULT_MAX_UPLOAD_MB,
    )

    max_total_storage_bytes = _env_int_mb(
        "GHOST_MAX_TOTAL_STORAGE_MB",
        DEFAULT_MAX_TOTAL_STORAGE_MB,
    )

    raw_extensions = os.getenv(
        "GHOST_ALLOWED_EXTENSIONS",
    )

    if raw_extensions and raw_extensions.strip():

        allowed = tuple(
            ext.strip().lower()
            for ext
            in raw_extensions.replace(
                ";",
                ",",
            ).split(",")
            if ext.strip()
        )

    else:

        allowed = tuple(
            ext.strip().lower()
            for ext
            in DEFAULT_ALLOWED_EXTENSIONS.split(",")
        )

    return UploadLimits(
        max_upload_bytes=max_upload_bytes,
        max_total_storage_bytes=max_total_storage_bytes,
        allowed_extensions=allowed,
    )

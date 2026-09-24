"""
GHOST — append-only audit log (M4 step 1).

One JSONL row per pipeline stage transition, correlated by
task_id. This is the audit artifact required by
docs/02-target-architecture.md (Security Sentinel: "Approval
Router -> Audit Log", storage "append-only for audit").

Guarantees enforced here:

- APPEND-ONLY. There is deliberately no update(), delete()
  or truncate() method: the file is only ever opened "a".
  Rows carry a monotonic sequence number so a rewritten or
  reordered file is detectable.
- NO SECRETS. Every value is sanitized before it is
  serialized: credential-bearing keys are dropped,
  credential-shaped substrings are redacted, and long
  strings (raw model output, document text) are truncated.
  Sanitization is applied to the whole row, so a secret
  nested in a provider payload cannot slip through.
- FAIL-SAFE. An audit write must never break the pipeline
  that is being audited: append() returns None on I/O
  failure after logging, and read() degrades to the rows
  that did parse.

Storage path follows the existing memory convention
(backend/core/memory.py, GHOST_MEMORY_PATH): default
backend/data/audit.jsonl, overridable with GHOST_AUDIT_PATH
so tests never touch the real file.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# Environment override, mirroring GHOST_MEMORY_PATH.
AUDIT_PATH_ENV = "GHOST_AUDIT_PATH"

# Raw model output and document excerpts are the main
# unbounded-risk fields.
MAX_STRING_CHARS = 2000

MAX_COLLECTION_ITEMS = 50

_REDACTED = "[redacted]"

_TRUNCATED_MARK = "...[truncated"

# Keys whose values must never reach disk, at any depth.
FORBIDDEN_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "passwd",
    "secret",
    "client_secret",
    "access_token",
    "refresh_token",
    "token",
    "tokens",
    "session_token",
    "credentials",
    "cookie",
    "cookies",
    "set_cookie",
    "private_key",
}

# Credential names appearing as "key: value" / "key=value"
# inside free text (model output, error strings).
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b("
    r"api[_-]?key|apikey|authorization|password|passwd|"
    r"secret|client[_-]?secret|access[_-]?token|"
    r"refresh[_-]?token|bearer|token"
    r")(\s*[:=]\s*)([\"']?)([^\s\"',;]+)([\"']?)"
)

# Well-known provider key prefixes, redacted wherever they
# appear even without an assignment operator.
_PREFERAL_KEY = re.compile(
    r"\b(nvapi-[A-Za-z0-9_\-]{6,}|sk-[A-Za-z0-9_\-]{6,}|"
    r"ghp_[A-Za-z0-9]{6,}|gho_[A-Za-z0-9]{6,}|"
    r"xox[baprs]-[A-Za-z0-9\-]{6,}|AIza[0-9A-Za-z_\-]{6,})"
)


def redact_text(text: str) -> str:
    """
    Scrub credential-shaped substrings out of free text.

    Module-level and public because the audit log is not the
    only place untrusted text needs scrubbing before it can be
    stored or returned: a provider exception can carry a request
    URL containing an API key, and that text lands in task errors.
    Callers other than this module must reuse this implementation
    instead of writing a second secret matcher.
    """

    text = _SECRET_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}{match.group(2)}"
        f"{match.group(3)}{_REDACTED}{match.group(5)}",
        text,
    )

    return _PREFERAL_KEY.sub(_REDACTED, text)


class AuditStage(str, Enum):
    """Every stage of the ENMA pipeline that can emit a row.

    Values are stable strings: they are the on-disk format,
    so they must not be renamed casually.
    """

    REQUEST = "request"
    PLANNED = "planned"
    SPEC = "spec"
    SKILL = "skill"
    PERMISSION = "permission"
    TOOL = "tool"
    MODEL = "model"
    RESULT = "result"
    REFLECTION = "reflection"
    MEMORY = "memory"
    APPROVAL = "approval"
    ERROR = "error"


class AuditLog:
    """Append-only JSONL audit store."""

    def __init__(
        self,
        storage_path: Optional[str] = None,
        max_string_chars: int = MAX_STRING_CHARS,
    ):
        if storage_path is None:
            storage_path = os.getenv(AUDIT_PATH_ENV)

        if storage_path is None:
            current_file = os.path.abspath(__file__)

            # backend/audit/log.py -> backend/audit -> backend
            # -> project root; the store lives beside memory.json.
            project_root = os.path.abspath(
                os.path.join(
                    os.path.dirname(current_file),
                    "..",
                    "..",
                )
            )

            storage_path = os.path.join(
                project_root,
                "backend",
                "data",
                "audit.jsonl",
            )

        self.storage_path = os.path.abspath(storage_path)
        self.max_string_chars = int(max_string_chars)

        directory = os.path.dirname(self.storage_path)

        if directory:
            os.makedirs(directory, exist_ok=True)

        # One lock per instance; append() is called from both
        # sync and async callers, so the write must be atomic.
        self._lock = threading.Lock()

        self._sequence = self._existing_row_count()

    # --------------------------------------------------------
    # WRITE PATH (append only)
    # --------------------------------------------------------

    def append(
        self,
        task_id: Optional[str],
        stage: Any,
        data: Optional[Dict[str, Any]] = None,
        event: Optional[str] = None,
        status: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Append one audit row and return it.

        ``stage`` accepts an AuditStage or its string value.
        Returns None when the write failed — auditing never
        raises into the pipeline.
        """

        # Sequence numbering and the write itself share one
        # lock hold, so append order and sequence order always
        # agree — an interleaved pair could otherwise emit
        # sequence 2 before sequence 1.
        with self._lock:
            row = {
                "sequence": self._take_sequence_locked(),
                "timestamp": timestamp or self._now(),
                "task_id": self._clean_scalar(task_id),
                "stage": self._stage_value(stage),
                "event": self._clean_scalar(event),
                "status": self._clean_scalar(status),
                "data": self._sanitize(
                    data if isinstance(data, dict) else {}
                ),
            }

            line = json.dumps(
                row,
                ensure_ascii=False,
                default=str,
            )

            try:
                with open(
                    self.storage_path,
                    "a",
                    encoding="utf-8",
                ) as handle:
                    handle.write(line + "\n")
                    handle.flush()
            except OSError:
                # A broken audit file must not fail a task.
                return None

        return row

    # --------------------------------------------------------
    # READ PATH
    # --------------------------------------------------------

    def read(
        self,
        task_id: Optional[str] = None,
        stage: Any = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return stored rows in append order, optionally
        filtered by task_id and/or stage.

        ``limit`` keeps the most recent N matching rows (still
        in append order). Unparseable lines are skipped.
        """

        rows = self._read_lines()

        stage_value = self._stage_value(stage) if stage else None

        matched = [
            row
            for row in rows
            if (task_id is None or row.get("task_id") == task_id)
            and (stage_value is None or row.get("stage") == stage_value)
        ]

        if limit is not None and limit >= 0:
            return matched[-int(limit):]

        return matched

    def count(self) -> int:
        """Total rows currently stored."""

        return len(self._read_lines())

    # --------------------------------------------------------
    # SANITIZATION
    # --------------------------------------------------------

    def _sanitize(self, value: Any, _depth: int = 0):
        """
        Recursively make ``value`` safe and serializable:
        forbidden keys dropped, secrets redacted, sizes
        bounded, depth bounded.
        """

        if _depth > 6:
            return "[max-depth]"

        if value is None or isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            return value

        if isinstance(value, str):
            return self._clean_string(value)

        if isinstance(value, Enum):
            return self._clean_scalar(value.value)

        if isinstance(value, dict):
            cleaned = {}

            for key, item in list(value.items())[:MAX_COLLECTION_ITEMS]:
                key_text = str(key)

                if key_text.lower().replace("-", "_") in FORBIDDEN_KEYS:
                    cleaned[key_text] = _REDACTED
                    continue

                cleaned[key_text] = self._sanitize(
                    item,
                    _depth + 1,
                )

            return cleaned

        if isinstance(value, (list, tuple, set)):
            items = list(value)[:MAX_COLLECTION_ITEMS]
            return [
                self._sanitize(item, _depth + 1) for item in items
            ]

        # Dataclasses, exceptions, and anything exotic.
        if hasattr(value, "to_dict") and callable(value.to_dict):
            try:
                return self._sanitize(
                    value.to_dict(),
                    _depth + 1,
                )
            except Exception:
                pass

        return self._clean_string(str(value))

    def _clean_string(self, text: str) -> str:
        original_length = len(text)

        if original_length > self.max_string_chars:
            text = text[: self.max_string_chars]

        text = redact_text(text)

        if original_length > self.max_string_chars:
            text += (
                f"{_TRUNCATED_MARK} "
                f"{original_length - self.max_string_chars} chars]"
            )

        return text

    def _clean_scalar(self, value: Any) -> Optional[str]:
        if value is None:
            return None

        if isinstance(value, Enum):
            value = value.value

        return self._clean_string(str(value))

    @staticmethod
    def _stage_value(stage: Any) -> str:
        if isinstance(stage, AuditStage):
            return stage.value

        return str(stage)

    # --------------------------------------------------------
    # STORAGE HELPERS
    # --------------------------------------------------------

    def _read_lines(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.storage_path):
            return []

        rows: List[Dict[str, Any]] = []

        try:
            with open(
                self.storage_path,
                "r",
                encoding="utf-8",
            ) as handle:
                for line in handle:
                    line = line.strip()

                    if not line:
                        continue

                    try:
                        parsed = json.loads(line)
                    except (ValueError, TypeError):
                        continue

                    if isinstance(parsed, dict):
                        rows.append(parsed)
        except OSError:
            return []

        return rows

    def _existing_row_count(self) -> int:
        return len(self._read_lines())

    def _take_sequence_locked(self) -> int:
        """Caller must hold self._lock."""

        self._sequence += 1
        return self._sequence

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

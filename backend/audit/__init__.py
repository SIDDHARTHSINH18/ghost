"""
GHOST — Audit layer (M4 step 1).

Append-only, secret-free record of every ENMA pipeline
stage transition, correlated by task_id:

  request -> planned -> spec -> skill -> permission
          -> tool/model -> result -> reflection -> memory

Nothing else in GHOST writes audit rows: components keep
their existing to_dict() audit views (PlanningResult,
ReflectionResult, ApprovalRecord, ExecutionSpec) and the
pipeline passes them to AuditLog, so there is exactly one
audit store.
"""

from backend.audit.log import (
    AUDIT_PATH_ENV,
    AuditLog,
    AuditStage,
    redact_text,
)

__all__ = [
    "AUDIT_PATH_ENV",
    "AuditLog",
    "AuditStage",
    "redact_text",
]

"""
GHOST — approval domain (M3-H step 5).

Explicit, auditable approval decisions for SENSITIVE
actions. See backend/approval/service.py.
"""

from backend.approval.service import (
    ApprovalDeniedError,
    ApprovalRecord,
    ApprovalRequiredError,
    ApprovalService,
    ApprovalStatus,
)

__all__ = [
    "ApprovalDeniedError",
    "ApprovalRecord",
    "ApprovalRequiredError",
    "ApprovalService",
    "ApprovalStatus",
]

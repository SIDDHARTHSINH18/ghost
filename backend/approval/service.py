"""
GHOST — explicit approval service (M3-H step 5).

Represents the human decision point for SENSITIVE
actions:

  approval required (PENDING)
    -> granted (GRANTED)   -> one-shot execution grant
    -> denied  (DENIED)    -> action can never run

The service is a RECORD KEEPER only. It computes no risk
decisions and holds no risk model: whether an action may
run is still decided exclusively by PermissionPolicy
(M3-C), which consumes a GRANTED record as a one-shot,
task-scoped exception at the moment of execution.

Lifecycle: PENDING -> GRANTED | DENIED -> CONSUMED
(a GRANTED record is consumed by the policy when the
approved action actually executes; DENIED is final).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4


class ApprovalStatus(Enum):
    PENDING = "PENDING"
    GRANTED = "GRANTED"
    DENIED = "DENIED"
    CONSUMED = "CONSUMED"


class ApprovalDeniedError(Exception):
    """Resume refused: the pending action was explicitly denied."""


class ApprovalRequiredError(Exception):
    """Resume refused: no approval decision exists yet."""


@dataclass
class ApprovalRecord:
    """
    One explicit approval decision for one pending
    action (task + tool, step recorded for audit).
    """

    approval_id: str
    task_id: str
    tool_name: str
    step_id: Optional[str]
    status: ApprovalStatus
    reason: str
    created_at: str
    decided_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "approval_id": self.approval_id,
            "task_id": self.task_id,
            "tool_name": self.tool_name,
            "step_id": self.step_id,
            "status": self.status.value,
            "reason": self.reason,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
        }


class ApprovalService:
    """
    In-memory, synchronous store of explicit approval
    decisions. Nothing here approves automatically:
    every transition to GRANTED/DENIED comes from an
    explicit decide() call.
    """

    def __init__(self):
        self._approvals: Dict[str, ApprovalRecord] = {}

    def create(
        self,
        task_id: str,
        tool_name: str,
        step_id: Optional[str] = None,
        reason: str = "",
    ) -> ApprovalRecord:
        """Register that an action is awaiting approval."""

        record = ApprovalRecord(
            approval_id=str(uuid4()),
            task_id=task_id,
            tool_name=tool_name,
            step_id=step_id,
            status=ApprovalStatus.PENDING,
            reason=reason or "",
            created_at=datetime.now().isoformat(),
        )

        self._approvals[record.approval_id] = record

        return record

    def get(self, approval_id: str) -> ApprovalRecord:
        if approval_id not in self._approvals:
            raise KeyError(
                f"Approval '{approval_id}' not found."
            )
        return self._approvals[approval_id]

    def list_pending(self) -> List[ApprovalRecord]:
        return [
            record
            for record in self._approvals.values()
            if record.status == ApprovalStatus.PENDING
        ]

    def list_for_task(self, task_id: str) -> List[ApprovalRecord]:
        return [
            record
            for record in self._approvals.values()
            if record.task_id == task_id
        ]

    def decide(
        self,
        approval_id: str,
        approved: bool,
    ) -> ApprovalRecord:
        """
        Apply an explicit human decision. Only PENDING
        records can be decided; a second decision is
        refused loudly (no silent overrides).
        """

        record = self.get(approval_id)

        if record.status != ApprovalStatus.PENDING:
            raise ValueError(
                f"Approval '{approval_id}' was already "
                f"decided ({record.status.value})."
            )

        record.status = (
            ApprovalStatus.GRANTED
            if approved
            else ApprovalStatus.DENIED
        )
        record.decided_at = datetime.now().isoformat()

        return record

    # --------------------------------------------------------
    # Grant lookup / consumption (used by PermissionPolicy)
    # --------------------------------------------------------

    def grants_for(
        self,
        task_id: str,
        tool_name: str,
    ) -> List[ApprovalRecord]:
        """Unused one-shot grants for this exact task+tool."""

        return [
            record
            for record in self._approvals.values()
            if (
                record.task_id == task_id
                and record.tool_name == tool_name
                and record.status == ApprovalStatus.GRANTED
            )
        ]

    def has_denial(
        self,
        task_id: str,
        tool_name: str,
    ) -> bool:
        return any(
            record.task_id == task_id
            and record.tool_name == tool_name
            and record.status == ApprovalStatus.DENIED
            for record in self._approvals.values()
        )

    def consume(
        self,
        task_id: str,
        tool_name: str,
    ) -> bool:
        """
        Consume one GRANTED grant for this exact task+tool
        (oldest first). Returns True when a grant existed;
        the consumed record can never authorize again.
        Called only by PermissionPolicy at execution time.
        """

        grants = self.grants_for(task_id, tool_name)

        if not grants:
            return False

        grants[0].status = ApprovalStatus.CONSUMED

        return True

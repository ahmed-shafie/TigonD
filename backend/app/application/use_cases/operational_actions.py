import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ...domain.exceptions import ApprovalRequired, ResourceNotFound, ValidationBlocked
from ...models import OperationalAction, OperationalActionApprovalResult, OperationalActionRequest
from ..ports.repositories import OperationalActionStore

IMPACTS = {
    "deploy": ["Creates or updates a stopped NiFi process group", "Injects secrets directly from Vault at execution time", "Does not start data movement"],
    "start": ["Starts data movement", "May increase source and target load", "Runtime status is checked after execution"],
    "stop": ["Stops new processing", "Queued flow files remain preserved", "Can be restarted with a new approval"],
    "retry": ["Retries the failed runtime action once", "Uses the existing versioned flow", "Duplicate retries are blocked"],
}


class OperationalActionService:
    """Approval state machine; state lives in the store and tokens are kept only as hashes."""

    def __init__(self, store: OperationalActionStore, approval_minutes: int = 5):
        self.store = store
        self.approval_minutes = approval_minutes

    def propose(self, request: OperationalActionRequest, actor: str) -> OperationalAction:
        expires = datetime.now(timezone.utc) + timedelta(minutes=self.approval_minutes)
        action = OperationalAction(
            action_id=str(uuid4()), action=request.action, deployment_id=request.deployment_id,
            reason=request.reason, proposed_by=actor, impact_summary=IMPACTS[request.action],
            approval_expires_at=expires.isoformat(),
        )
        self.store.insert(action)
        return action

    def get(self, action_id: str) -> OperationalAction:
        action = self.store.get(action_id)
        if action is None:
            raise ResourceNotFound(action_id)
        if action.status in {"proposed", "approved"} and self._expired(action):
            expired = action.model_copy(update={"status": "expired"})
            stored = self.store.update(expired, expected_status=action.status)
            return stored or self.store.get(action_id) or action
        return action

    def decide(self, action_id: str, decision: str, actor: str) -> OperationalActionApprovalResult:
        action = self.get(action_id)
        if action.status != "proposed":
            raise ValidationBlocked("Action is no longer awaiting approval")
        if decision == "rejected":
            cancelled = action.model_copy(update={"status": "cancelled", "approved_by": actor})
            stored = self.store.update(cancelled, expected_status="proposed")
            if stored is None:
                raise ValidationBlocked("Action is no longer awaiting approval")
            return OperationalActionApprovalResult(action=stored)
        token = secrets.token_urlsafe(32)
        approved = action.model_copy(update={"status": "approved", "approved_by": actor})
        stored = self.store.update(approved, expected_status="proposed", token_hash=self._hash(token))
        if stored is None:
            raise ValidationBlocked("Action is no longer awaiting approval")
        return OperationalActionApprovalResult(action=stored, approval_token=token)

    def begin(self, action_id: str, token: str, idempotency_key: str) -> OperationalAction:
        replayed = self.store.find_by_idempotency_key(idempotency_key)
        if replayed is not None:
            return replayed
        action = self.get(action_id)
        if action.status != "approved" or self.store.token_hash(action_id) != self._hash(token):
            raise ApprovalRequired("A valid unexpired approval token is required")
        executing = action.model_copy(update={"status": "executing"})
        stored = self.store.update(executing, expected_status="approved", idempotency_key=idempotency_key)
        if stored is None:
            raise ApprovalRequired("A valid unexpired approval token is required")
        return stored

    def finish(self, action_id: str, idempotency_key: str, result: str, rollback: str | None = None) -> OperationalAction:
        action = self.get(action_id)
        finished = action.model_copy(update={
            "status": "failed" if rollback else "succeeded",
            "result_summary": result, "rollback_summary": rollback,
        })
        stored = self.store.update(finished, expected_status=action.status, idempotency_key=idempotency_key)
        if stored is None:
            raise ValidationBlocked("Action is no longer executing")
        return stored

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _expired(action: OperationalAction) -> bool:
        return datetime.now(timezone.utc) >= datetime.fromisoformat(action.approval_expires_at)

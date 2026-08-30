import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from threading import Lock
from uuid import uuid4

from ...domain.exceptions import ApprovalRequired, ResourceNotFound, ValidationBlocked
from ...models import OperationalAction, OperationalActionApprovalResult, OperationalActionRequest


class OperationalActionService:
    """Thread-safe approval state machine; tokens are stored only as hashes."""

    def __init__(self, approval_minutes: int = 5):
        self.approval_minutes = approval_minutes
        self._actions: dict[str, OperationalAction] = {}
        self._token_hashes: dict[str, str] = {}
        self._idempotency: dict[str, OperationalAction] = {}
        self._lock = Lock()

    def propose(self, request: OperationalActionRequest, actor: str) -> OperationalAction:
        expires = datetime.now(timezone.utc) + timedelta(minutes=self.approval_minutes)
        impacts = {
            "deploy": ["Creates or updates a stopped NiFi process group", "Injects secrets directly from Vault at execution time", "Does not start data movement"],
            "start": ["Starts data movement", "May increase source and target load", "Runtime status is checked after execution"],
            "stop": ["Stops new processing", "Queued flow files remain preserved", "Can be restarted with a new approval"],
            "retry": ["Retries the failed runtime action once", "Uses the existing versioned flow", "Duplicate retries are blocked"],
        }
        action = OperationalAction(
            action_id=str(uuid4()), action=request.action, deployment_id=request.deployment_id,
            reason=request.reason, proposed_by=actor, impact_summary=impacts[request.action],
            approval_expires_at=expires.isoformat(),
        )
        with self._lock:
            self._actions[action.action_id] = action
        return action

    def get(self, action_id: str) -> OperationalAction:
        try:
            action = self._actions[action_id]
        except KeyError as exc:
            raise ResourceNotFound(action_id) from exc
        if action.status in {"proposed", "approved"} and self._expired(action):
            action = action.model_copy(update={"status": "expired"})
            self._actions[action_id] = action
        return action

    def decide(self, action_id: str, decision: str, actor: str) -> OperationalActionApprovalResult:
        with self._lock:
            action = self.get(action_id)
            if action.status != "proposed":
                raise ValidationBlocked("Action is no longer awaiting approval")
            if decision == "rejected":
                rejected = action.model_copy(update={"status": "cancelled", "approved_by": actor})
                self._actions[action_id] = rejected
                return OperationalActionApprovalResult(action=rejected)
            token = secrets.token_urlsafe(32)
            approved = action.model_copy(update={"status": "approved", "approved_by": actor})
            self._actions[action_id] = approved
            self._token_hashes[action_id] = self._hash(token)
            return OperationalActionApprovalResult(action=approved, approval_token=token)

    def begin(self, action_id: str, token: str, idempotency_key: str) -> OperationalAction:
        with self._lock:
            if idempotency_key in self._idempotency:
                return self._idempotency[idempotency_key]
            action = self.get(action_id)
            if action.status != "approved" or self._token_hashes.get(action_id) != self._hash(token):
                raise ApprovalRequired("A valid unexpired approval token is required")
            executing = action.model_copy(update={"status": "executing"})
            self._actions[action_id] = executing
            self._idempotency[idempotency_key] = executing
            del self._token_hashes[action_id]
            return executing

    def finish(self, action_id: str, idempotency_key: str, result: str, rollback: str | None = None) -> OperationalAction:
        with self._lock:
            action = self._actions[action_id]
            finished = action.model_copy(update={"status": "failed" if rollback else "succeeded", "result_summary": result, "rollback_summary": rollback})
            self._actions[action_id] = finished
            self._idempotency[idempotency_key] = finished
            return finished

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _expired(action: OperationalAction) -> bool:
        return datetime.now(timezone.utc) >= datetime.fromisoformat(action.approval_expires_at)


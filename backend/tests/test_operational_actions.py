import pytest

from app.application.use_cases.operational_actions import OperationalActionService
from app.infrastructure.action_store import InMemoryOperationalActionStore
from app.domain.exceptions import ApprovalRequired
from app.models import OperationalActionRequest


def request(action="start"):
    return OperationalActionRequest(action=action, deployment_id="deployment-1", reason="Operator requested controlled execution")


def test_action_requires_approval_and_exposes_impact():
    service = OperationalActionService(InMemoryOperationalActionStore())
    action = service.propose(request(), "developer-a")
    assert action.status == "proposed"
    assert action.risk_level == "high"
    assert action.impact_summary
    with pytest.raises(ApprovalRequired):
        service.begin(action.action_id, "invalid-token", "request-0001")


def test_token_is_single_use_and_idempotency_returns_same_result():
    service = OperationalActionService(InMemoryOperationalActionStore())
    action = service.propose(request(), "developer-a")
    approved = service.decide(action.action_id, "approved", "admin-b")
    begun = service.begin(action.action_id, approved.approval_token, "request-0002")
    assert begun.status == "executing"
    finished = service.finish(action.action_id, "request-0002", "NiFi flow changed to running")
    repeated = service.begin(action.action_id, "wrong-token", "request-0002")
    assert repeated == finished
    assert repeated.status == "succeeded"


def test_rejection_permanently_cancels_action():
    service = OperationalActionService(InMemoryOperationalActionStore())
    action = service.propose(request("deploy"), "developer-a")
    rejected = service.decide(action.action_id, "rejected", "admin-b")
    assert rejected.action.status == "cancelled"
    assert rejected.approval_token is None


def test_state_lives_in_the_store_so_another_worker_sees_the_same_action():
    store = InMemoryOperationalActionStore()
    action = OperationalActionService(store).propose(request("stop"), "developer-a")
    approval = OperationalActionService(store).decide(action.action_id, "approved", "admin-b")
    executing = OperationalActionService(store).begin(action.action_id, approval.approval_token, "request-0003")
    assert executing.status == "executing"
    with pytest.raises(ApprovalRequired):
        OperationalActionService(store).begin(action.action_id, approval.approval_token, "request-0004")

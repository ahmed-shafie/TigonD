"""Integration coverage proving approvals and intelligence state outlive a process.

Runs only when TIGOND_TEST_DATABASE_URL points at a migrated metadata database.
"""
import os

import pytest

from app.application.use_cases.intelligence_loop import IntelligenceLoop
from app.application.use_cases.operational_actions import OperationalActionService
from app.domain.exceptions import ApprovalRequired
from app.infrastructure.action_store import PostgresOperationalActionStore
from app.infrastructure.intelligence_store import PostgresIntelligenceStore
from app.models import (IncidentSignal, MemoryRecordRequest,
                        OperationalActionRequest, RecommendationFeedback)

DATABASE_URL = os.environ.get("TIGOND_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TIGOND_TEST_DATABASE_URL is not configured")


def service() -> OperationalActionService:
    return OperationalActionService(PostgresOperationalActionStore(DATABASE_URL))


def loop() -> IntelligenceLoop:
    return IntelligenceLoop(PostgresIntelligenceStore(DATABASE_URL))


def test_approval_state_and_token_survive_a_restart_and_stay_single_use():
    proposed = service().propose(
        OperationalActionRequest(action="start", deployment_id="deployment-1", reason="Operator requested controlled execution"),
        "developer-a",
    )
    approval = service().decide(proposed.action_id, "approved", "admin-b")

    executing = service().begin(proposed.action_id, approval.approval_token, f"{proposed.action_id}-1")
    assert executing.status == "executing"
    finished = service().finish(proposed.action_id, f"{proposed.action_id}-1", "NiFi flow changed to running")
    assert finished.status == "succeeded"

    replayed = service().begin(proposed.action_id, "wrong-token", f"{proposed.action_id}-1")
    assert replayed == finished
    with pytest.raises(ApprovalRequired):
        service().begin(proposed.action_id, approval.approval_token, f"{proposed.action_id}-2")


def test_raw_approval_tokens_are_never_stored():
    proposed = service().propose(
        OperationalActionRequest(action="stop", deployment_id="deployment-1", reason="Operator requested a controlled stop"),
        "developer-a",
    )
    approval = service().decide(proposed.action_id, "approved", "admin-b")
    store = PostgresOperationalActionStore(DATABASE_URL)
    with store.connect() as db, db.cursor() as cursor:
        cursor.execute("SELECT token_hash, payload::text FROM operational_actions WHERE id = %s", (proposed.action_id,))
        row = cursor.fetchone()
    assert approval.approval_token not in row["payload"]
    assert row["token_hash"] != approval.approval_token


def test_incidents_memory_and_feedback_are_readable_by_another_process():
    deployment_id = f"deployment-{os.getpid()}"
    diagnosis = loop().diagnose(IncidentSignal(deployment_id=deployment_id, message="Column type mismatch", schema_changed=True))
    assert [item.incident_id for item in loop().timeline(deployment_id)] == [diagnosis.incident_id]
    assert any(item.severity in {"critical", "warning"} for item in loop().insights())

    fact = f"Use updated_at as the approved watermark for {deployment_id}"
    loop().remember(MemoryRecordRequest(scope="pipeline", subject_id=deployment_id, fact=fact, source="assessment-12"))
    recalled = loop().recall(f"{deployment_id} watermark", "pipeline")
    assert fact in [item.fact for item in recalled]

    before = loop().metrics().total_feedback
    after = loop().feedback(RecommendationFeedback(recommendation_id="r1", accepted=True, outcome="successful"))
    assert after.total_feedback == before + 1

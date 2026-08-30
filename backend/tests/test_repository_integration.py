"""Integration coverage for proposal versioning and the decision trail.

Runs only when TIGOND_TEST_DATABASE_URL points at a migrated metadata database.
"""
import os
from uuid import uuid4

import pytest

from app.models import PipelineProposal
from app.repository import SourceRepository
from app.vault import MemorySecretStore

DATABASE_URL = os.environ.get("TIGOND_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TIGOND_TEST_DATABASE_URL is not configured")


def proposal(version: int = 1) -> PipelineProposal:
    return PipelineProposal(
        proposal_id=str(uuid4()), version=version, status="draft", runtime="nifi",
        source_object="public.customers", target_pattern="bronze/public/customers",
        load_strategy="incremental", schedule="0 * * * *", business_key="customer_id",
        watermark_column="updated_at", mappings=[], quality_gates=[], transformations=[],
        assumptions=[], risks=[], confidence=90, explanation=f"Version {version}", requirement="Ingest customers hourly.",
    )


@pytest.fixture
def repo():
    return SourceRepository(DATABASE_URL, MemorySecretStore())


def test_versions_are_numbered_per_lineage_and_decisions_are_recorded(repo):
    first = repo.save_pipeline_proposal(proposal, None, "tester")
    second = repo.save_pipeline_proposal(proposal, None, "tester")
    assert second.version == first.version + 1
    assert second.explanation == f"Version {second.version}"

    decided = repo.decide_pipeline_proposal(second.proposal_id, "approved", "Reviewed with the data owner", "tester")
    assert decided.status == "approved"
    with repo.connect() as db, db.cursor() as cursor:
        cursor.execute("SELECT decision_reason, decided_by, decided_at FROM pipeline_proposals WHERE id=%s",
                       (second.proposal_id,))
        row = cursor.fetchone()
    assert row["decision_reason"] == "Reviewed with the data owner"
    assert row["decided_by"] == "tester"
    assert row["decided_at"] is not None

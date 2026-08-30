from app.models import PipelineDraft, PipelineProposalPatch, PipelineProposalRequest, SourceAssessment
from app.proposals import PipelineProposalEngine


def assessment():
    return SourceAssessment(
        assessment_id="a1", source_id="s1", schema_name="public", table_name="customers", quality_score=92,
        pii_columns=["mobile_number"], business_key_candidates=["customer_id"], watermark_candidates=["updated_at"],
        recommended_runtime="nifi", confidence=91, runtime_scores=[], summary="Normalize mobile numbers.",
        pipeline_draft=PipelineDraft(load_strategy="incremental", business_key="customer_id", watermark_column="updated_at",
            source_object="public.customers", target_pattern="bronze/public/customers",
            quality_gates=["completeness >= 95%"], status="approved"),
    )


def test_compiler_combines_language_and_profile_evidence():
    request = PipelineProposalRequest(requirement="Ingest customers incrementally every hour, normalize mobile and quarantine invalid records.")
    proposal = PipelineProposalEngine().compile(request, assessment(), 4)
    assert proposal.version == 4
    assert proposal.runtime == "nifi"
    assert proposal.schedule == "0 * * * *"
    assert proposal.execution_allowed is False
    assert "route invalid records to quarantine" in proposal.quality_gates
    assert any(mapping.transformation == "normalize_e164" for mapping in proposal.mappings)


def test_real_time_requirement_selects_cdc_and_surfaces_risk():
    request = PipelineProposalRequest(requirement="Ingest from public.transactions in real-time with CDC to the bronze zone.")
    proposal = PipelineProposalEngine().compile(request, None, 1)
    assert proposal.load_strategy == "cdc"
    assert proposal.runtime == "kafka_debezium"
    assert proposal.schedule == "continuous"
    assert any("replication privileges" in risk for risk in proposal.risks)


def test_visual_revision_is_versioned_and_compared_before_approval():
    engine = PipelineProposalEngine()
    original = engine.compile(PipelineProposalRequest(requirement="Ingest customers incrementally every hour with quality checks."), assessment(), 1)
    revised = engine.revise(original, PipelineProposalPatch(schedule="0 */2 * * *", quality_gates=["completeness >= 99%"]), 2)
    validation = engine.validate(revised, original)
    assert revised.parent_proposal_id == original.proposal_id
    assert revised.version == 2
    assert validation.valid is True
    assert "quality gates changed" in validation.changes_from_previous
    assert any(change.startswith("schedule:") for change in validation.changes_from_previous)


def test_validation_blocks_incremental_without_watermark():
    engine = PipelineProposalEngine()
    original = engine.compile(PipelineProposalRequest(requirement="Ingest customers incrementally every hour."), assessment(), 1)
    revised = engine.revise(original, PipelineProposalPatch(watermark_column=""), 2)
    validation = engine.validate(revised)
    assert validation.valid is False
    assert any("watermark" in blocker.lower() for blocker in validation.blockers)

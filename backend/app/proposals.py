import re
from uuid import uuid4

from .models import ColumnMapping, PipelineProposal, PipelineProposalPatch, PipelineProposalRequest, ProposalValidation, SourceAssessment

COMPILABLE_RUNTIMES = frozenset({"nifi"})
RUNTIME_ADAPTER_NOTE = (
    "The {runtime} execution adapter is not available yet, so approval records the decision "
    "without generating a flow specification."
)


class PipelineProposalEngine:
    """Turns a natural-language requirement into a deterministic, reviewable draft."""

    def compile(self, request: PipelineProposalRequest, assessment: SourceAssessment | None, version: int) -> PipelineProposal:
        text = request.requirement.lower()
        source = assessment.pipeline_draft.source_object if assessment else self._source(text)
        near_real_time = any(term in text for term in ("real time", "real-time", "cdc", "immediately"))
        incremental = any(term in text for term in ("incremental", "hourly", "watermark", "changed rows"))
        strategy = "cdc" if near_real_time else "incremental" if incremental or assessment else "full"
        runtime = "kafka_debezium" if near_real_time else (assessment.recommended_runtime if assessment else "nifi")
        schedule = "continuous" if near_real_time else "0 * * * *" if "hour" in text else "0 2 * * *"
        business_key = assessment.pipeline_draft.business_key if assessment else ("customer_id" if "customer" in text else None)
        watermark = assessment.pipeline_draft.watermark_column if assessment else ("updated_at" if strategy == "incremental" else None)
        transformations = []
        mappings = [ColumnMapping(source="*", target="*", transformation="direct")]
        if "mobile" in text or "phone" in text or (assessment and "mobile_number" in assessment.pii_columns):
            transformations.append("Normalize mobile_number to E.164 format")
            mappings.append(ColumnMapping(source="mobile_number", target="mobile_number", transformation="normalize_e164"))
        if "mask" in text or (assessment and assessment.pii_columns):
            transformations.append("Mask detected PII in previews and non-production outputs")
        quarantine = any(term in text for term in ("quarantine", "invalid", "reject")) or bool(assessment)
        gates = list(assessment.pipeline_draft.quality_gates) if assessment else ["row count > 0", "schema contract valid"]
        if quarantine:
            gates.append("route invalid records to quarantine")
        assumptions = ["Target uses Parquet in the bronze zone", "Human approval is required before compilation or deployment"]
        risks = []
        if strategy == "incremental" and not watermark:
            risks.append("No verified watermark column; incremental extraction needs review")
        if not business_key:
            risks.append("No verified business key; deduplication may be incomplete")
        if near_real_time:
            risks.append("CDC requires database replication privileges and retention sizing")
        confidence = max(60, (assessment.confidence if assessment else 72) - 5 * len(risks))
        target = assessment.pipeline_draft.target_pattern if assessment else f"bronze/{source.replace('.', '/')}"
        return PipelineProposal(
            proposal_id=str(uuid4()), version=version, requirement=request.requirement,
            runtime=runtime, source_object=source, target_pattern=target, load_strategy=strategy,
            schedule=schedule, business_key=business_key, watermark_column=watermark,
            mappings=mappings, quality_gates=list(dict.fromkeys(gates)), transformations=transformations,
            assumptions=assumptions, risks=risks, confidence=confidence,
            explanation=f"{runtime.upper()} fits the requested {strategy} delivery pattern. The draft combines the requirement with profiled source evidence and remains non-executable until approval.",
        )

    @staticmethod
    def _source(text: str) -> str:
        match = re.search(r"(?:from|ingest)\s+([a-z_][\w]*(?:\.[a-z_][\w]*)?)", text)
        return match.group(1) if match else "public.customers"

    def revise(self, proposal: PipelineProposal, patch: PipelineProposalPatch, version: int) -> PipelineProposal:
        updates = {field: getattr(patch, field) for field in patch.model_fields_set}
        changed = {field: value for field, value in updates.items() if getattr(proposal, field) != value}
        updates.update({"proposal_id": str(uuid4()), "version": version, "status": "draft",
                        "parent_proposal_id": proposal.proposal_id, "execution_allowed": False})
        revised = proposal.model_copy(update=updates)
        revised.confidence = max(50, proposal.confidence - (2 if changed else 0))
        revised.explanation = f"Version {version} applies reviewed visual-editor changes to version {proposal.version}. It remains non-executable until revalidated and approved."
        return revised

    def validate(self, proposal: PipelineProposal, previous: PipelineProposal | None = None) -> ProposalValidation:
        blockers, warnings = [], []
        if not proposal.mappings:
            blockers.append("At least one source-to-target mapping is required")
        if not proposal.target_pattern.strip():
            blockers.append("Target pattern is required")
        if proposal.load_strategy == "incremental" and not proposal.watermark_column:
            blockers.append("Incremental load requires a watermark column")
        if proposal.load_strategy == "cdc" and proposal.runtime != "kafka_debezium":
            blockers.append("CDC proposals require Kafka + Debezium runtime")
        if proposal.runtime not in COMPILABLE_RUNTIMES:
            warnings.append(RUNTIME_ADAPTER_NOTE.format(runtime=proposal.runtime))
        if not proposal.quality_gates:
            warnings.append("No quality gate protects the target")
        if not proposal.business_key:
            warnings.append("No business key is configured for deduplication")
        warnings.extend(proposal.risks)
        changes = []
        if previous:
            for field in ("runtime", "load_strategy", "schedule", "target_pattern", "business_key", "watermark_column"):
                if getattr(previous, field) != getattr(proposal, field):
                    changes.append(f"{field}: {getattr(previous, field)} → {getattr(proposal, field)}")
            if previous.mappings != proposal.mappings:
                changes.append(f"mappings changed: {len(previous.mappings)} → {len(proposal.mappings)}")
            if previous.quality_gates != proposal.quality_gates:
                changes.append("quality gates changed")
            if previous.transformations != proposal.transformations:
                changes.append("transformations changed")
        score = max(0, 100 - 30 * len(blockers) - 8 * len(warnings))
        return ProposalValidation(proposal_id=proposal.proposal_id, valid=not blockers, score=score,
                                  blockers=blockers, warnings=list(dict.fromkeys(warnings)),
                                  changes_from_previous=changes)

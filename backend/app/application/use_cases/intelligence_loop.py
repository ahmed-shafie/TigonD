from datetime import datetime, timezone
from uuid import uuid4

from ...models import (IncidentDiagnosis, IncidentSignal, IntelligenceMetrics,
                       MemoryRecord, MemoryRecordRequest, ProactiveInsight,
                       RecommendationFeedback)
from ..ports.repositories import IntelligenceStore


class IntelligenceLoop:
    """CPU-first diagnosis, memory and feedback loop grounded in persisted evidence."""

    def __init__(self, store: IntelligenceStore):
        self.store = store

    def diagnose(self, signal: IncidentSignal) -> IncidentDiagnosis:
        text = signal.message.lower()
        if signal.schema_changed or any(x in text for x in ("column", "schema", "type mismatch")):
            category, cause, steps = "schema_drift", "The source schema no longer matches the approved pipeline contract.", ["Compare the current schema with the approved version", "Generate a compatible mapping proposal", "Require approval before rollout"]
        elif signal.quality_score is not None and signal.quality_score < 80:
            category, cause, steps = "data_quality", "Quality evidence fell below the protected threshold.", ["Identify failing columns and rules", "Route invalid records to quarantine", "Review source-system change with the data owner"]
        elif signal.queued_count > 10_000:
            category, cause, steps = "backpressure", "The NiFi queue exceeded the safe flow-file threshold.", ["Inspect slow downstream processors", "Scale the constrained processor group", "Drain the queue before increasing source throughput"]
        elif any(x in text for x in ("connection", "timeout", "refused", "dns")):
            category, cause, steps = "connectivity", "The runtime cannot reach a required endpoint reliably.", ["Verify network and DNS from the runtime", "Test credentials without exposing them", "Retry once after connectivity recovers"]
        elif signal.invalid_processors:
            category, cause, steps = "runtime", "One or more NiFi processors are invalid or misconfigured.", ["Inspect invalid processor properties", "Validate controller services", "Compile a corrected version for approval"]
        else:
            category, cause, steps = "unknown", "Available evidence is insufficient for a confident root cause.", ["Collect processor bulletin and queue evidence", "Correlate the failure with recent changes", "Escalate for human review"]
        severity = "critical" if signal.invalid_processors > 2 or signal.queued_count > 50_000 else "high" if category in {"schema_drift", "data_quality", "backpressure"} else "medium"
        evidence = [signal.message, f"queued_count={signal.queued_count}", f"invalid_processors={signal.invalid_processors}"]
        diagnosis = IncidentDiagnosis(incident_id=str(uuid4()), deployment_id=signal.deployment_id, category=category, severity=severity, confidence=90 if category != "unknown" else 45, root_cause=cause, evidence=evidence, remediation_steps=steps, rollback_recommended=category in {"schema_drift", "data_quality"}, created_at=datetime.now(timezone.utc).isoformat())
        self.store.add_incident(diagnosis)
        return diagnosis

    def timeline(self, deployment_id: str) -> list[IncidentDiagnosis]:
        return self.store.incidents_for_deployment(deployment_id)

    def remember(self, request: MemoryRecordRequest) -> MemoryRecord:
        record = MemoryRecord(**request.model_dump(), memory_id=str(uuid4()), created_at=datetime.now(timezone.utc).isoformat())
        self.store.add_memory(record)
        return record

    def recall(self, query: str, scope: str | None = None) -> list[MemoryRecord]:
        terms = sorted({term for term in query.lower().split() if len(term) > 2})
        candidates = self.store.search_memory(terms, scope)
        scored = [(sum(term in f"{m.subject_id} {m.fact} {m.source}".lower() for term in terms), m) for m in candidates]
        return [item for score, item in sorted(scored, key=lambda pair: pair[0], reverse=True) if score][:20]

    def feedback(self, item: RecommendationFeedback) -> IntelligenceMetrics:
        self.store.add_feedback(item)
        return self.metrics()

    def metrics(self) -> IntelligenceMetrics:
        total, accepted, successful = self.store.feedback_totals()
        return IntelligenceMetrics(total_feedback=total, acceptance_rate=round(100 * accepted / total, 2) if total else 0, successful_outcome_rate=round(100 * successful / total, 2) if total else 0)

    def insights(self) -> list[ProactiveInsight]:
        open_incidents = self.store.open_incidents()
        if not open_incidents:
            return []
        critical = [item for item in open_incidents if item.severity in {"critical", "high"}]
        return [ProactiveInsight(insight_id=str(uuid4()), severity="critical" if critical else "warning", title=f"{len(open_incidents)} open pipeline incidents require review", evidence=[f"{item.category}: {item.root_cause}" for item in open_incidents[-3:]], recommended_action="Review the incident timeline and create a human-approved remediation action")]


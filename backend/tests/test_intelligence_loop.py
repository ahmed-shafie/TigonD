from app.application.use_cases.intelligence_loop import IntelligenceLoop
from app.models import IncidentSignal, MemoryRecordRequest, RecommendationFeedback


def test_diagnoses_schema_drift_with_safe_remediation():
    engine = IntelligenceLoop()
    result = engine.diagnose(IncidentSignal(deployment_id="dep-1", message="Column type mismatch", schema_changed=True))
    assert result.category == "schema_drift"
    assert result.rollback_recommended is True
    assert result.remediation_steps
    assert engine.insights()[0].requires_approval is True


def test_memory_recall_is_scoped_and_grounded():
    engine = IntelligenceLoop()
    engine.remember(MemoryRecordRequest(scope="pipeline", subject_id="customers", fact="Use updated_at as the approved watermark", source="assessment-12"))
    engine.remember(MemoryRecordRequest(scope="user", subject_id="operator-a", fact="Prefers concise summaries", source="explicit-feedback"))
    results = engine.recall("customers watermark", "pipeline")
    assert len(results) == 1
    assert results[0].source == "assessment-12"


def test_feedback_metrics_measure_accuracy_loop():
    engine = IntelligenceLoop()
    metrics = engine.feedback(RecommendationFeedback(recommendation_id="r1", accepted=True, outcome="successful"))
    engine.feedback(RecommendationFeedback(recommendation_id="r2", accepted=False, outcome="failed"))
    metrics = engine.metrics()
    assert metrics.acceptance_rate == 50
    assert metrics.successful_outcome_rate == 50


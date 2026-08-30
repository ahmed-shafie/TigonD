import httpx

from app.assistant import AssistantEngine
from app.models import AssistantRequest


CONTEXT = {
    "source_count": 2, "deployment_count": 1,
    "latest_assessment": {"schema_name":"public", "table_name":"customers", "quality_score":92,
        "pii_columns":["mobile_number"], "summary":"Mobile formatting needs normalization.",
        "recommended_runtime":"nifi", "confidence":91},
    "latest_deployment": {"version":3, "status":"running"},
    "assessment_summary":"public.customers quality 92/100",
    "deployment_summary":"NiFi v3 is running",
}


def test_cpu_fallback_answers_from_context_and_exposes_evidence():
    reply = AssistantEngine("http://ollama", "qwen", False).answer(AssistantRequest(message="Explain the quality evidence"), CONTEXT)
    assert "92/100" in reply.answer
    assert "mobile_number" in reply.answer
    assert reply.mode == "read_only"
    assert reply.model == "tigond-rules-cpu"
    assert any(item.tool == "quality.latest_assessment" for item in reply.tools_used)


def test_optional_ollama_is_local_and_grounded():
    def handler(request: httpx.Request):
        assert request.url.path == "/api/generate"
        assert "quality_score" in request.read().decode()
        return httpx.Response(200, json={"response":"Grounded local answer. Approval is required."})
    engine = AssistantEngine("http://ollama", "qwen", True, httpx.MockTransport(handler))
    reply = engine.answer(AssistantRequest(message="What is the status?"), CONTEXT)
    assert reply.model == "ollama/qwen"
    assert "Approval" in reply.answer

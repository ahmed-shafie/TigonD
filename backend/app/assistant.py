import json

import httpx

from .models import AssistantRequest, AssistantResponse, AssistantToolEvidence


SYSTEM_PROMPT = """You are TigonD AI, a concise data-platform copilot. Answer only from the supplied
platform context. Never invent metrics. Never request, reveal, or infer credentials. This is read-only mode:
you may explain and recommend, but you must say that deployment or runtime changes require human approval."""


class AssistantEngine:
    """Grounded, CPU-first copilot with an optional local Ollama language layer."""

    def __init__(self, ollama_url: str, model: str, enabled: bool = False, transport=None):
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.enabled = enabled
        self.transport = transport

    def answer(self, request: AssistantRequest, context: dict) -> AssistantResponse:
        evidence = self._evidence(request.message, context)
        answer = self._local_answer(request.message, context)
        model = "tigond-rules-cpu"
        if self.enabled:
            generated = self._ollama_answer(request.message, context)
            if generated:
                answer, model = generated, f"ollama/{self.model}"
        return AssistantResponse(
            conversation_id=request.conversation_id or "",
            answer=answer,
            model=model,
            tools_used=evidence,
            suggestions=self._suggestions(context),
        )

    def _ollama_answer(self, message: str, context: dict) -> str | None:
        try:
            with httpx.Client(timeout=12, transport=self.transport, trust_env=False) as client:
                response = client.post(f"{self.ollama_url}/api/generate", json={
                    "model": self.model, "stream": False,
                    "prompt": f"{SYSTEM_PROMPT}\nContext: {json.dumps(context)}\nQuestion: {message}",
                    "options": {"temperature": 0.1, "num_predict": 260},
                })
                response.raise_for_status()
                return response.json().get("response", "").strip() or None
        except (httpx.HTTPError, ValueError):
            return None

    @staticmethod
    def _evidence(message: str, context: dict) -> list[AssistantToolEvidence]:
        text = message.lower()
        evidence = [AssistantToolEvidence(tool="platform.summary", summary=f"{context['source_count']} sources and {context['deployment_count']} flow deployments")]
        if any(word in text for word in ("quality", "score", "pii", "column", "evidence")):
            evidence.append(AssistantToolEvidence(tool="quality.latest_assessment", summary=context.get("assessment_summary") or "No assessment is available"))
        if any(word in text for word in ("flow", "pipeline", "nifi", "failed", "running", "status")):
            evidence.append(AssistantToolEvidence(tool="runtime.deployment_status", summary=context.get("deployment_summary") or "No deployment is available"))
        return evidence

    @staticmethod
    def _local_answer(message: str, context: dict) -> str:
        text = message.lower()
        assessment = context.get("latest_assessment")
        deployment = context.get("latest_deployment")
        if any(word in text for word in ("quality", "score", "pii", "evidence")):
            if not assessment:
                return "No completed assessment is available yet. Connect a source and run intelligent assessment so I can explain its quality evidence."
            pii = ", ".join(assessment.get("pii_columns", [])) or "none detected"
            return (f"The latest quality score is {assessment['quality_score']}/100 for {assessment['schema_name']}.{assessment['table_name']}. "
                    f"Detected PII: {pii}. {assessment['summary']} I am reading assessment metadata only; credentials are excluded.")
        if any(word in text for word in ("why", "runtime", "nifi", "airbyte", "dlt")):
            if not assessment:
                return "I need a source assessment before comparing NiFi, Airbyte and dlt with evidence."
            return (f"TigonD recommends {assessment['recommended_runtime'].upper()} with {assessment['confidence']}% confidence. "
                    f"The decision uses source profile, latency, transformation complexity and connector fit. Any generated flow still requires explicit approval.")
        if any(word in text for word in ("failed", "running", "status", "pipeline", "flow")):
            if not deployment:
                return "There are no generated or deployed flows yet. Approve an assessment before generating a versioned flow proposal."
            return (f"The latest NiFi flow is version {deployment['version']} and its recorded state is {deployment['status']}. "
                    "Phase 3.1 is read-only, so I can diagnose and recommend but cannot start, stop or deploy it.")
        return (f"I can inspect {context['source_count']} connected sources, quality assessments and {context['deployment_count']} flow deployments. "
                "Ask me about source quality, PII, runtime selection or pipeline status. I will ground every answer in TigonD metadata.")

    @staticmethod
    def _suggestions(context: dict) -> list[str]:
        items = ["Explain the latest quality score", "Why was this runtime selected?"]
        items.append("Show the latest pipeline status" if context["deployment_count"] else "What is needed before flow generation?")
        return items

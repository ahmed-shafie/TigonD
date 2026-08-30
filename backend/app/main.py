import httpx
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from psycopg import Error as PostgresError

from .auth import Principal, current_principal, require_roles
from .assistant import AssistantEngine
from .config import get_settings
from .intelligence import IntelligenceEngine
from .models import (AssistantRequest, AssistantResponse, AssessmentRequest, AuditEvent, ConnectionTestResult, DataObject, FlowDeployment, NiFiStatus, PipelineProposal, PipelineProposalPatch, PipelineProposalRequest, ProposalApprovalResult, ProposalDecision, ProposalValidation,
                     PostgresConnection, RecommendationDecision, RegisteredSource, SourceAssessment, TableProfile)
from .nifi import NiFiClient, NiFiError, NiFiFlowCompiler
from .proposals import COMPILABLE_RUNTIMES, RUNTIME_ADAPTER_NOTE, PipelineProposalEngine
from .postgres import PostgresService
from .repository import SourceRepository
from .vault import VaultSecretStore


settings = get_settings()
secret_store = VaultSecretStore(settings.vault_url, settings.vault_token, settings.vault_mount)
repository = SourceRepository(settings.metadata_database_url, secret_store)
postgres = PostgresService(settings.query_timeout_seconds, settings.profile_sample_rows)
intelligence = IntelligenceEngine()
nifi_compiler = NiFiFlowCompiler()
nifi_client = NiFiClient(settings.nifi_url, settings.nifi_username, settings.nifi_password, settings.nifi_verify_ssl)
assistant = AssistantEngine(settings.ollama_url, settings.ollama_model, settings.ollama_enabled)
proposal_engine = PipelineProposalEngine()

app = FastAPI(title="TigonD Ingestion API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["*"],
)


def get_repository() -> SourceRepository:
    return repository


def get_postgres() -> PostgresService:
    return postgres


def get_nifi() -> NiFiClient:
    return nifi_client


def get_assistant() -> AssistantEngine:
    return assistant


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy", "service": "tigond-ingestion-api"}


@app.get("/api/v1/me")
def me(principal: Principal = Depends(current_principal)) -> dict[str, object]:
    return {"username": principal.username, "roles": sorted(principal.roles)}


@app.post("/api/v1/sources/test", response_model=ConnectionTestResult)
def test_source(connection: PostgresConnection, service: PostgresService = Depends(get_postgres), principal: Principal = Depends(require_roles("administrator", "developer"))):
    try:
        return service.test(connection)
    except PostgresError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="PostgreSQL connection failed") from exc


@app.post("/api/v1/sources", response_model=RegisteredSource, status_code=status.HTTP_201_CREATED)
def register_source(
    connection: PostgresConnection,
    repo: SourceRepository = Depends(get_repository),
    service: PostgresService = Depends(get_postgres),
    principal: Principal = Depends(require_roles("administrator", "developer")),
):
    try:
        service.test(connection)
        stored = repo.create(connection, principal.username)
    except PostgresError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="PostgreSQL connection failed") from exc
    return RegisteredSource(
        source_id=stored.source_id, name=stored.name, host=stored.host, database=stored.database,
    )


@app.get("/api/v1/sources", response_model=list[RegisteredSource])
def list_sources(repo: SourceRepository = Depends(get_repository), _: Principal = Depends(require_roles("administrator", "developer", "operator", "quality", "governance"))):
    return repo.list_sources()


@app.get("/api/v1/sources/{source_id}/objects", response_model=list[DataObject])
def discover_objects(
    source_id: str,
    repo: SourceRepository = Depends(get_repository),
    service: PostgresService = Depends(get_postgres),
    _: Principal = Depends(require_roles("administrator", "developer", "operator", "quality", "governance")),
):
    try:
        return service.discover(repo.get_connection(source_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Source not found") from exc
    except PostgresError as exc:
        raise HTTPException(status_code=502, detail="Source discovery failed") from exc


@app.post("/api/v1/sources/{source_id}/profile/{schema_name}/{table_name}", response_model=TableProfile)
def profile_table(
    source_id: str,
    schema_name: str,
    table_name: str,
    repo: SourceRepository = Depends(get_repository),
    service: PostgresService = Depends(get_postgres),
    principal: Principal = Depends(require_roles("administrator", "developer", "quality")),
):
    try:
        profile = service.profile(repo.get_connection(source_id), schema_name, table_name)
        repo.audit(principal.username, "profile.completed", "source", source_id, "success")
        return profile.model_copy(update={"source_id": source_id})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Source not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PostgresError as exc:
        raise HTTPException(status_code=502, detail="Table profiling failed") from exc


@app.post("/api/v1/sources/{source_id}/assess/{schema_name}/{table_name}", response_model=SourceAssessment)
def assess_source(
    source_id: str,
    schema_name: str,
    table_name: str,
    request: AssessmentRequest,
    repo: SourceRepository = Depends(get_repository),
    service: PostgresService = Depends(get_postgres),
    principal: Principal = Depends(require_roles("administrator", "developer", "quality")),
):
    try:
        profile = service.profile(repo.get_connection(source_id), schema_name, table_name)
        assessment = intelligence.assess(source_id, profile.model_copy(update={"source_id": source_id}), request)
        return repo.save_assessment(assessment, principal.username)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Source not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PostgresError as exc:
        raise HTTPException(status_code=502, detail="Source assessment failed") from exc


@app.post("/api/v1/assessments/{assessment_id}/decision", status_code=status.HTTP_204_NO_CONTENT)
def decide_recommendation(
    assessment_id: str,
    decision: RecommendationDecision,
    repo: SourceRepository = Depends(get_repository),
    principal: Principal = Depends(require_roles("administrator", "developer")),
):
    try:
        repo.decide_assessment(assessment_id, decision.decision, decision.reason, principal.username)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Assessment not found") from exc


@app.get("/api/v1/runtimes/nifi/health")
def nifi_health(client: NiFiClient = Depends(get_nifi), _: Principal = Depends(require_roles("administrator", "operator"))):
    try:
        return client.health()
    except (NiFiError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail="NiFi is unavailable") from exc


@app.post("/api/v1/assessments/{assessment_id}/nifi/generate", response_model=FlowDeployment)
def generate_nifi_flow(
    assessment_id: str,
    repo: SourceRepository = Depends(get_repository),
    principal: Principal = Depends(require_roles("administrator", "developer")),
):
    try:
        assessment = repo.get_assessment(assessment_id)
        spec = nifi_compiler.compile(assessment, repo.next_flow_version(assessment_id))
        return repo.save_generated_flow(assessment_id, spec, principal.username)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Assessment not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/v1/deployments/{deployment_id}/deploy", response_model=FlowDeployment)
def deploy_nifi_flow(
    deployment_id: str,
    repo: SourceRepository = Depends(get_repository),
    client: NiFiClient = Depends(get_nifi),
    principal: Principal = Depends(require_roles("administrator", "developer")),
):
    try:
        deployment = repo.get_deployment(deployment_id)
        assessment = repo.get_assessment(deployment.assessment_id)
        source = repo.get_connection(assessment.source_id)
        secrets = {"JDBC_URL":f"jdbc:postgresql://{source.host}:{source.port}/{source.database}",
                   "DB_USERNAME":source.username, "DB_PASSWORD":source.password.get_secret_value()}
        external_id = client.deploy(deployment.flow_spec, secrets)
        return repo.update_deployment(deployment_id, "deployed", principal.username, external_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Deployment not found") from exc
    except (NiFiError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail="NiFi deployment failed") from exc


@app.post("/api/v1/deployments/{deployment_id}/{action}", response_model=FlowDeployment)
def control_nifi_flow(
    deployment_id: str,
    action: str,
    repo: SourceRepository = Depends(get_repository),
    client: NiFiClient = Depends(get_nifi),
    principal: Principal = Depends(require_roles("administrator", "operator")),
):
    if action not in {"start", "stop"}:
        raise HTTPException(status_code=404, detail="Unknown flow action")
    try:
        deployment = repo.get_deployment(deployment_id)
        if not deployment.external_flow_id:
            raise ValueError("Flow has not been deployed")
        client.set_state(deployment.external_flow_id, "RUNNING" if action == "start" else "STOPPED")
        return repo.update_deployment(deployment_id, "running" if action == "start" else "stopped", principal.username)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Deployment not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (NiFiError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=f"NiFi {action} failed") from exc


@app.get("/api/v1/deployments/{deployment_id}/status", response_model=NiFiStatus)
def nifi_flow_status(
    deployment_id: str,
    repo: SourceRepository = Depends(get_repository),
    client: NiFiClient = Depends(get_nifi),
    _: Principal = Depends(require_roles("administrator", "developer", "operator")),
):
    try:
        deployment = repo.get_deployment(deployment_id)
        if not deployment.external_flow_id:
            raise ValueError("Flow has not been deployed")
        return client.status(deployment.external_flow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Deployment not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (NiFiError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail="NiFi status unavailable") from exc


@app.get("/api/v1/audit", response_model=list[AuditEvent])
def audit_events(repo: SourceRepository = Depends(get_repository), _: Principal = Depends(require_roles("administrator", "governance"))):
    return repo.list_audit()


@app.post("/api/v1/assistant/chat", response_model=AssistantResponse)
def assistant_chat(
    request: AssistantRequest,
    repo: SourceRepository = Depends(get_repository),
    engine: AssistantEngine = Depends(get_assistant),
    principal: Principal = Depends(require_roles("administrator", "developer", "operator", "quality", "governance")),
):
    context = repo.assistant_context(request.assessment_id, request.deployment_id)
    response = engine.answer(request, context)
    return repo.save_assistant_exchange(request, response, principal.username)


@app.post("/api/v1/pipeline-proposals", response_model=PipelineProposal, status_code=status.HTTP_201_CREATED)
def create_pipeline_proposal(
    request: PipelineProposalRequest,
    repo: SourceRepository = Depends(get_repository),
    principal: Principal = Depends(require_roles("administrator", "developer")),
):
    try:
        assessment = repo.get_assessment(request.assessment_id) if request.assessment_id else None
        proposal = proposal_engine.compile(request, assessment, repo.next_proposal_version(request.assessment_id))
        return repo.save_pipeline_proposal(proposal, request.assessment_id, principal.username)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Assessment not found") from exc


@app.get("/api/v1/pipeline-proposals/{proposal_id}", response_model=PipelineProposal)
def get_pipeline_proposal(
    proposal_id: str,
    repo: SourceRepository = Depends(get_repository),
    _: Principal = Depends(require_roles("administrator", "developer", "operator", "quality", "governance")),
):
    try:
        return repo.get_pipeline_proposal(proposal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Pipeline proposal not found") from exc


@app.put("/api/v1/pipeline-proposals/{proposal_id}", response_model=PipelineProposal, status_code=status.HTTP_201_CREATED)
def revise_pipeline_proposal(
    proposal_id: str,
    patch: PipelineProposalPatch,
    repo: SourceRepository = Depends(get_repository),
    principal: Principal = Depends(require_roles("administrator", "developer")),
):
    try:
        current = repo.get_pipeline_proposal(proposal_id)
        assessment_id = repo.get_proposal_assessment_id(proposal_id)
        revised = proposal_engine.revise(current, patch, repo.next_proposal_version(assessment_id))
        return repo.save_proposal_revision(revised, assessment_id, principal.username)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Pipeline proposal not found") from exc


@app.post("/api/v1/pipeline-proposals/{proposal_id}/validate", response_model=ProposalValidation)
def validate_pipeline_proposal(
    proposal_id: str,
    repo: SourceRepository = Depends(get_repository),
    principal: Principal = Depends(require_roles("administrator", "developer", "quality")),
):
    try:
        proposal = repo.get_pipeline_proposal(proposal_id)
        previous = repo.get_pipeline_proposal(proposal.parent_proposal_id) if proposal.parent_proposal_id else None
        result = proposal_engine.validate(proposal, previous)
        repo.audit(principal.username, "proposal.validated", "pipeline_proposal", proposal_id, "success" if result.valid else "blocked")
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Pipeline proposal not found") from exc


@app.post("/api/v1/pipeline-proposals/{proposal_id}/decision", response_model=ProposalApprovalResult)
def decide_pipeline_proposal(
    proposal_id: str,
    decision: ProposalDecision,
    repo: SourceRepository = Depends(get_repository),
    principal: Principal = Depends(require_roles("administrator", "developer")),
):
    try:
        proposal = repo.get_pipeline_proposal(proposal_id)
        previous = repo.get_pipeline_proposal(proposal.parent_proposal_id) if proposal.parent_proposal_id else None
        validation = proposal_engine.validate(proposal, previous)
        if decision.decision == "approved" and not validation.valid:
            raise ValueError("Proposal has validation blockers")
        spec = None
        note = None
        assessment_id = None
        if decision.decision == "approved":
            if proposal.runtime in COMPILABLE_RUNTIMES:
                assessment_id = repo.get_proposal_assessment_id(proposal_id)
                if not assessment_id:
                    raise ValueError("An evidence-based source assessment is required before NiFi compilation")
                assessment = repo.get_assessment(assessment_id)
                if assessment.pipeline_draft.status != "approved":
                    raise ValueError("The source assessment must be approved by a human before compilation")
                draft = assessment.pipeline_draft.model_copy(update={
                    "load_strategy": proposal.load_strategy, "business_key": proposal.business_key,
                    "watermark_column": proposal.watermark_column, "target_pattern": proposal.target_pattern,
                    "quality_gates": proposal.quality_gates,
                })
                compiled_assessment = assessment.model_copy(update={"pipeline_draft": draft, "recommended_runtime": proposal.runtime})
                spec = nifi_compiler.compile(compiled_assessment, repo.next_flow_version(assessment_id))
            else:
                note = RUNTIME_ADAPTER_NOTE.format(runtime=proposal.runtime)
        approved = repo.decide_pipeline_proposal(proposal_id, decision.decision, decision.reason, principal.username)
        deployment = repo.save_generated_flow(assessment_id, spec, principal.username) if spec is not None else None
        return ProposalApprovalResult(
            proposal=approved, validation=validation, deployment=deployment,
            compiled=deployment is not None, compilation_note=note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Pipeline proposal not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

from typing import Literal

from pydantic import BaseModel, Field, SecretStr


class PostgresConnection(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=100)
    username: str = Field(min_length=1, max_length=100)
    password: SecretStr
    sslmode: Literal["disable", "allow", "prefer", "require", "verify-ca", "verify-full"] = "prefer"


class ConnectionTestResult(BaseModel):
    ok: bool
    database: str
    server_version: str
    latency_ms: float


class RegisteredSource(BaseModel):
    source_id: str
    name: str
    engine: Literal["postgresql"] = "postgresql"
    host: str
    database: str
    status: Literal["connected", "error"] = "connected"


class DataObject(BaseModel):
    schema_name: str
    object_name: str
    object_type: Literal["table", "view"]
    estimated_rows: int | None = None


class ColumnProfile(BaseModel):
    name: str
    data_type: str
    nullable: bool
    sampled_rows: int
    null_count: int
    distinct_count: int
    completeness: float
    uniqueness: float


class TableProfile(BaseModel):
    source_id: str
    schema_name: str
    table_name: str
    sampled_rows: int
    quality_score: float
    columns: list[ColumnProfile]
    recommendations: list[str]


class AuditEvent(BaseModel):
    event_id: str
    actor: str
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    created_at: str


class AssessmentRequest(BaseModel):
    desired_latency: Literal["daily", "hourly", "near_real_time"] = "daily"
    transformation_complexity: Literal["low", "medium", "high"] = "medium"
    prefer_visual_design: bool = True
    packaged_connector_available: bool = True


class RuntimeScore(BaseModel):
    runtime: Literal["nifi", "airbyte", "dlt", "kafka_debezium"]
    score: int
    evidence: list[str]
    risks: list[str]


class PipelineDraft(BaseModel):
    load_strategy: Literal["full", "incremental", "cdc"]
    business_key: str | None
    watermark_column: str | None
    source_object: str
    target_pattern: str
    quality_gates: list[str]
    status: Literal["draft", "approved", "rejected"] = "draft"


class SourceAssessment(BaseModel):
    assessment_id: str
    source_id: str
    schema_name: str
    table_name: str
    quality_score: float
    pii_columns: list[str]
    business_key_candidates: list[str]
    watermark_candidates: list[str]
    recommended_runtime: str
    confidence: int
    runtime_scores: list[RuntimeScore]
    pipeline_draft: PipelineDraft
    summary: str


class RecommendationDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str | None = Field(default=None, max_length=500)


class ProcessorSpec(BaseModel):
    key: str
    name: str
    processor_type: str
    properties: dict[str, str]
    auto_terminated_relationships: list[str] = []


class ConnectionSpec(BaseModel):
    source_key: str
    destination_key: str
    relationships: list[str]
    back_pressure_objects: int = 10_000
    back_pressure_size: str = "1 GB"


class NiFiFlowSpec(BaseModel):
    flow_name: str
    version: int
    assessment_id: str
    parameters: dict[str, str]
    sensitive_parameter_names: list[str]
    processors: list[ProcessorSpec]
    connections: list[ConnectionSpec]
    retry_count: int = 3
    quarantine_enabled: bool = True


class FlowDeployment(BaseModel):
    deployment_id: str
    assessment_id: str
    runtime: Literal["nifi"] = "nifi"
    version: int
    external_flow_id: str | None
    status: Literal["generated", "deployed", "running", "stopped", "failed"]
    flow_spec: NiFiFlowSpec


class NiFiStatus(BaseModel):
    flow_id: str
    run_status: str
    queued_count: int
    queued_bytes: int
    stopped_processors: int
    invalid_processors: int
    back_pressure_warning: bool


class AssistantRequest(BaseModel):
    message: str = Field(min_length=2, max_length=2000)
    conversation_id: str | None = None
    assessment_id: str | None = None
    deployment_id: str | None = None


class AssistantToolEvidence(BaseModel):
    tool: str
    summary: str


class AssistantResponse(BaseModel):
    conversation_id: str
    answer: str
    mode: Literal["read_only"] = "read_only"
    model: str
    tools_used: list[AssistantToolEvidence]
    suggestions: list[str]


class PipelineProposalRequest(BaseModel):
    requirement: str = Field(min_length=10, max_length=3000)
    assessment_id: str | None = None


class ColumnMapping(BaseModel):
    source: str
    target: str
    transformation: str = "direct"


class PipelineProposal(BaseModel):
    proposal_id: str
    version: int
    requirement: str
    status: Literal["draft", "approved", "rejected"] = "draft"
    runtime: Literal["nifi", "airbyte", "dlt", "kafka_debezium"]
    source_object: str
    target_pattern: str
    load_strategy: Literal["full", "incremental", "cdc"]
    schedule: str
    business_key: str | None
    watermark_column: str | None
    mappings: list[ColumnMapping]
    quality_gates: list[str]
    transformations: list[str]
    assumptions: list[str]
    risks: list[str]
    confidence: int
    explanation: str
    execution_allowed: Literal[False] = False
    parent_proposal_id: str | None = None


class PipelineProposalPatch(BaseModel):
    target_pattern: str | None = Field(default=None, min_length=3, max_length=500)
    schedule: str | None = Field(default=None, min_length=1, max_length=100)
    business_key: str | None = None
    watermark_column: str | None = None
    mappings: list[ColumnMapping] | None = None
    quality_gates: list[str] | None = None
    transformations: list[str] | None = None


class ProposalValidation(BaseModel):
    proposal_id: str
    valid: bool
    score: int
    blockers: list[str]
    warnings: list[str]
    changes_from_previous: list[str]


class ProposalDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str | None = Field(default=None, max_length=500)


class ProposalApprovalResult(BaseModel):
    proposal: PipelineProposal
    validation: ProposalValidation
    deployment: FlowDeployment | None = None
    compiled: bool = False
    compilation_note: str | None = None

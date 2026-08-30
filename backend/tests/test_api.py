from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app, get_nifi, get_postgres, get_repository
from app.models import ColumnProfile, ConnectionTestResult, FlowDeployment, NiFiStatus, RegisteredSource, TableProfile


class FakePostgres:
    def test(self, connection):
        return ConnectionTestResult(ok=True, database=connection.database, server_version="PostgreSQL 16 test", latency_ms=4.2)

    def discover(self, _connection):
        return [{"schema_name": "public", "object_name": "customers", "object_type": "table", "estimated_rows": 3}]

    def profile(self, _connection, schema_name, table_name):
        return TableProfile(source_id="", schema_name=schema_name, table_name=table_name, sampled_rows=100,
            quality_score=98.5, recommendations=["No blocking issues"], columns=[
                ColumnProfile(name="customer_id", data_type="bigint", nullable=False, sampled_rows=100, null_count=0, distinct_count=100, completeness=100, uniqueness=100),
                ColumnProfile(name="mobile_number", data_type="varchar", nullable=True, sampled_rows=100, null_count=3, distinct_count=90, completeness=97, uniqueness=92.78),
                ColumnProfile(name="updated_at", data_type="timestamp with time zone", nullable=False, sampled_rows=100, null_count=0, distinct_count=100, completeness=100, uniqueness=100),
            ])


class FakeRepository:
    def __init__(self):
        self.source = None
        self.proposals = {}

    def create(self, connection, actor):
        self.source = RegisteredSource(source_id="source-1", name=connection.name, host=connection.host, database=connection.database)
        return self.source

    def get_connection(self, _source_id):
        from app.models import PostgresConnection
        return PostgresConnection(**payload())

    def list_sources(self):
        return [self.source] if self.source else []

    def save_assessment(self, assessment, _actor):
        self.assessment = assessment
        return assessment

    def decide_assessment(self, assessment_id, decision, reason, actor):
        self.last_decision = (assessment_id, decision, reason, actor)
        if getattr(self, "assessment", None):
            self.assessment = self.assessment.model_copy(update={"pipeline_draft": self.assessment.pipeline_draft.model_copy(update={"status": decision})})

    def get_assessment(self, _assessment_id):
        return self.assessment

    def next_flow_version(self, _assessment_id):
        return 1

    def save_generated_flow(self, assessment_id, spec, _actor):
        self.deployment = FlowDeployment(deployment_id="deployment-1", assessment_id=assessment_id, version=1,
            external_flow_id=None, status="generated", flow_spec=spec)
        return self.deployment

    def get_deployment(self, _deployment_id):
        return self.deployment

    def update_deployment(self, _deployment_id, status, _actor, external_flow_id=None):
        self.deployment = self.deployment.model_copy(update={"status": status, "external_flow_id": external_flow_id or self.deployment.external_flow_id})
        return self.deployment

    def assistant_context(self, assessment_id=None, deployment_id=None):
        assessment = getattr(self, "assessment", None)
        deployment = getattr(self, "deployment", None)
        payload = assessment.model_dump() if assessment else None
        flow = {"version": deployment.version, "status": deployment.status} if deployment else None
        return {"source_count": 1 if self.source else 0, "deployment_count": 1 if deployment else 0,
                "latest_assessment": payload, "latest_deployment": flow,
                "assessment_summary": f"public.customers quality {payload['quality_score']}/100" if payload else None,
                "deployment_summary": f"NiFi v{flow['version']} is {flow['status']}" if flow else None}

    def save_assistant_exchange(self, request, response, actor):
        self.last_assistant_actor = actor
        return response.model_copy(update={"conversation_id": request.conversation_id or "conversation-1"})

    def next_proposal_version(self):
        return len(self.proposals) + 1

    def save_pipeline_proposal(self, proposal, assessment_id, actor):
        self.proposal = proposal
        self.proposal_assessment_id = assessment_id
        self.proposals[proposal.proposal_id] = proposal
        return proposal

    def get_pipeline_proposal(self, proposal_id):
        return self.proposals[proposal_id]

    def get_proposal_assessment_id(self, _proposal_id):
        return self.proposal_assessment_id

    def save_proposal_revision(self, proposal, assessment_id, actor):
        return self.save_pipeline_proposal(proposal, assessment_id, actor)

    def decide_pipeline_proposal(self, proposal_id, decision, reason, actor):
        self.proposal = self.proposals[proposal_id].model_copy(update={"status": decision})
        self.proposals[proposal_id] = self.proposal
        return self.proposal

    def audit(self, actor, action, resource_type, resource_id, outcome):
        self.last_audit = (actor, action, resource_type, resource_id, outcome)


class FakeNiFi:
    def health(self):
        return {"status": "healthy", "heap": "12%"}

    def deploy(self, spec, secrets):
        assert secrets["DB_PASSWORD"] == "secret"
        assert all("secret" not in str(processor.properties) for processor in spec.processors)
        return "nifi-group-1"

    def set_state(self, flow_id, state):
        self.last_state = (flow_id, state)

    def status(self, flow_id):
        return NiFiStatus(flow_id=flow_id, run_status="Running", queued_count=12, queued_bytes=2048,
                          stopped_processors=0, invalid_processors=0, back_pressure_warning=False)


fake_repo = FakeRepository()


def payload():
    return {"name": "CRM Production", "host": "postgres.internal", "port": 5432, "database": "customer_360",
            "username": "tigond_reader", "password": "secret", "sslmode": "require"}


def setup_function():
    app.dependency_overrides[get_settings] = lambda: Settings(auth_disabled=True)
    app.dependency_overrides[get_postgres] = lambda: FakePostgres()
    app.dependency_overrides[get_repository] = lambda: fake_repo
    app.dependency_overrides[get_nifi] = lambda: FakeNiFi()


def teardown_function():
    app.dependency_overrides.clear()


def test_health():
    assert TestClient(app).get("/health").json()["status"] == "healthy"


def test_connection_contract():
    response = TestClient(app).post("/api/v1/sources/test", json=payload())
    assert response.status_code == 200
    assert response.json()["database"] == "customer_360"


def test_registration_never_returns_password():
    response = TestClient(app).post("/api/v1/sources", json=payload())
    assert response.status_code == 201
    assert "password" not in response.json()
    assert response.json()["engine"] == "postgresql"


def test_discovery_contract():
    response = TestClient(app).get("/api/v1/sources/source-1/objects")
    assert response.status_code == 200
    assert response.json()[0]["object_name"] == "customers"


def test_authentication_required_when_enabled():
    app.dependency_overrides[get_settings] = lambda: Settings(auth_disabled=False)
    response = TestClient(app).get("/api/v1/sources")
    assert response.status_code == 401


def test_explainable_assessment_and_pipeline_draft():
    TestClient(app).post("/api/v1/sources", json=payload())
    response = TestClient(app).post("/api/v1/sources/source-1/assess/public/customers", json={
        "desired_latency": "daily", "transformation_complexity": "high",
        "prefer_visual_design": True, "packaged_connector_available": True,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["recommended_runtime"] == "nifi"
    assert body["pipeline_draft"]["load_strategy"] == "incremental"
    assert "mobile_number" in body["pii_columns"]
    assert body["runtime_scores"][0]["evidence"]


def test_human_decision_is_recorded_without_execution():
    response = TestClient(app).post("/api/v1/assessments/assessment-1/decision", json={"decision": "approved", "reason": "Evidence accepted"})
    assert response.status_code == 204
    assert fake_repo.last_decision[1] == "approved"


def test_near_real_time_requirement_selects_cdc_runtime():
    TestClient(app).post("/api/v1/sources", json=payload())
    response = TestClient(app).post("/api/v1/sources/source-1/assess/public/customers", json={
        "desired_latency": "near_real_time", "transformation_complexity": "medium",
        "prefer_visual_design": True, "packaged_connector_available": True,
    })
    assert response.status_code == 200
    assert response.json()["recommended_runtime"] == "kafka_debezium"
    assert response.json()["pipeline_draft"]["load_strategy"] == "cdc"


def test_approved_draft_generates_deploys_and_starts_nifi_flow():
    TestClient(app).post("/api/v1/sources", json=payload())
    assessment = TestClient(app).post("/api/v1/sources/source-1/assess/public/customers", json={
        "desired_latency": "daily", "transformation_complexity": "high",
        "prefer_visual_design": True, "packaged_connector_available": True,
    }).json()
    TestClient(app).post(f"/api/v1/assessments/{assessment['assessment_id']}/decision", json={"decision":"approved"})
    generated = TestClient(app).post(f"/api/v1/assessments/{assessment['assessment_id']}/nifi/generate")
    assert generated.status_code == 200
    assert generated.json()["flow_spec"]["quarantine_enabled"] is True
    assert generated.json()["flow_spec"]["parameters"]["DB_PASSWORD"] == ""

    deployed = TestClient(app).post("/api/v1/deployments/deployment-1/deploy")
    assert deployed.status_code == 200
    assert deployed.json()["external_flow_id"] == "nifi-group-1"
    started = TestClient(app).post("/api/v1/deployments/deployment-1/start")
    assert started.status_code == 200
    assert started.json()["status"] == "running"
    status = TestClient(app).get("/api/v1/deployments/deployment-1/status")
    assert status.status_code == 200
    assert status.json()["back_pressure_warning"] is False


def test_assistant_is_grounded_read_only_and_auditable():
    response = TestClient(app).post("/api/v1/assistant/chat", json={"message":"Why was NiFi selected?"})
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "read_only"
    assert body["conversation_id"] == "conversation-1"
    assert any(item["tool"] == "platform.summary" for item in body["tools_used"])
    assert "approval" in body["answer"].lower()


def test_natural_language_requirement_creates_non_executable_proposal():
    TestClient(app).post("/api/v1/sources", json=payload())
    assessment_id = TestClient(app).post("/api/v1/sources/source-1/assess/public/customers", json={
        "desired_latency":"daily", "transformation_complexity":"high",
        "prefer_visual_design":True, "packaged_connector_available":True,
    }).json()["assessment_id"]
    response = TestClient(app).post("/api/v1/pipeline-proposals", json={
        "requirement":"Ingest customers incrementally every hour, normalize mobile numbers and quarantine invalid records.",
        "assessment_id": assessment_id,
    })
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["execution_allowed"] is False
    assert body["load_strategy"] == "incremental"
    assert body["schedule"] == "0 * * * *"
    assert any(item["transformation"] == "normalize_e164" for item in body["mappings"])

    fetched = TestClient(app).get(f"/api/v1/pipeline-proposals/{body['proposal_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["proposal_id"] == body["proposal_id"]

    revised = TestClient(app).put(f"/api/v1/pipeline-proposals/{body['proposal_id']}", json={
        "schedule":"0 */2 * * *", "quality_gates":["completeness >= 98%", "route invalid records to quarantine"]
    })
    assert revised.status_code == 201
    assert revised.json()["parent_proposal_id"] == body["proposal_id"]
    validation = TestClient(app).post(f"/api/v1/pipeline-proposals/{revised.json()['proposal_id']}/validate")
    assert validation.status_code == 200
    assert validation.json()["valid"] is True
    assert validation.json()["changes_from_previous"]

    approved = TestClient(app).post(f"/api/v1/pipeline-proposals/{revised.json()['proposal_id']}/decision", json={"decision":"approved"})
    assert approved.status_code == 200
    assert approved.json()["proposal"]["status"] == "approved"
    assert approved.json()["deployment"]["status"] == "generated"

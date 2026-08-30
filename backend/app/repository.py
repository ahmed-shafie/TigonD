import json
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from .models import AssistantRequest, AssistantResponse, AuditEvent, FlowDeployment, NiFiFlowSpec, PipelineProposal, PostgresConnection, RegisteredSource, SourceAssessment
from .vault import MemorySecretStore, VaultSecretStore


class SourceRepository:
    def __init__(self, database_url: str, secrets: VaultSecretStore | MemorySecretStore):
        self.database_url = database_url
        self.secrets = secrets

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def create(self, connection: PostgresConnection, actor: str) -> RegisteredSource:
        source_id = str(uuid4())
        secret_path = self.secrets.put_source_password(source_id, connection.password.get_secret_value())
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute(
                """INSERT INTO sources(id, name, engine, host, port, database_name, username, sslmode, secret_path, status, created_by)
                   VALUES (%s, %s, 'postgresql', %s, %s, %s, %s, %s, %s, 'connected', %s)""",
                (source_id, connection.name, connection.host, connection.port, connection.database,
                 connection.username, connection.sslmode, secret_path, actor),
            )
            self._audit(cursor, actor, "source.created", "source", source_id, "success")
        return RegisteredSource(source_id=source_id, name=connection.name, host=connection.host, database=connection.database)

    def get_connection(self, source_id: str) -> PostgresConnection:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT * FROM sources WHERE id = %s", (source_id,))
            row = cursor.fetchone()
        if row is None:
            raise KeyError(source_id)
        return PostgresConnection(
            name=row["name"], host=row["host"], port=row["port"], database=row["database_name"],
            username=row["username"], password=self.secrets.get_source_password(row["secret_path"]), sslmode=row["sslmode"],
        )

    def list_sources(self) -> list[RegisteredSource]:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT id AS source_id, name, engine, host, database_name AS database, status FROM sources ORDER BY created_at DESC")
            return [RegisteredSource(**row) for row in cursor.fetchall()]

    def audit(self, actor: str, action: str, resource_type: str, resource_id: str | None, outcome: str) -> None:
        with self.connect() as db, db.cursor() as cursor:
            self._audit(cursor, actor, action, resource_type, resource_id, outcome)

    def list_audit(self, limit: int = 100) -> list[AuditEvent]:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT id AS event_id, actor, action, resource_type, resource_id, outcome, created_at::text FROM audit_events ORDER BY created_at DESC LIMIT %s", (limit,))
            return [AuditEvent(**row) for row in cursor.fetchall()]

    def save_assessment(self, assessment: SourceAssessment, actor: str) -> SourceAssessment:
        payload = assessment.model_dump_json()
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute(
                """INSERT INTO source_assessments(id, source_id, schema_name, table_name, recommended_runtime, confidence, status, payload, created_by)
                   VALUES (%s, %s, %s, %s, %s, %s, 'draft', %s::jsonb, %s)""",
                (assessment.assessment_id, assessment.source_id, assessment.schema_name, assessment.table_name,
                 assessment.recommended_runtime, assessment.confidence, payload, actor),
            )
            self._audit(cursor, actor, "assessment.created", "assessment", assessment.assessment_id, "success")
        return assessment

    def decide_assessment(self, assessment_id: str, decision: str, reason: str | None, actor: str) -> None:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute(
                "UPDATE source_assessments SET status=%s, decision_reason=%s, decided_by=%s, decided_at=CURRENT_TIMESTAMP WHERE id=%s",
                (decision, reason, actor, assessment_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(assessment_id)
            self._audit(cursor, actor, f"assessment.{decision}", "assessment", assessment_id, "success")

    def get_assessment(self, assessment_id: str) -> SourceAssessment:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT payload, status FROM source_assessments WHERE id=%s", (assessment_id,))
            row = cursor.fetchone()
        if row is None:
            raise KeyError(assessment_id)
        payload = row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"])
        payload["pipeline_draft"]["status"] = row["status"]
        return SourceAssessment.model_validate(payload)

    def next_flow_version(self, assessment_id: str) -> int:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT COALESCE(MAX(version), 0) + 1 AS version FROM flow_deployments WHERE assessment_id=%s", (assessment_id,))
            return int(cursor.fetchone()["version"])

    def save_generated_flow(self, assessment_id: str, spec: NiFiFlowSpec, actor: str) -> FlowDeployment:
        deployment_id = str(uuid4())
        safe_payload = spec.model_dump()
        for name in spec.sensitive_parameter_names:
            safe_payload["parameters"][name] = ""
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("""INSERT INTO flow_deployments(id, assessment_id, runtime, version, status, flow_spec, created_by)
                              VALUES (%s,%s,'nifi',%s,'generated',%s::jsonb,%s)""",
                           (deployment_id, assessment_id, spec.version, json.dumps(safe_payload), actor))
            self._audit(cursor, actor, "nifi.flow.generated", "deployment", deployment_id, "success")
        return FlowDeployment(deployment_id=deployment_id, assessment_id=assessment_id, version=spec.version,
                              external_flow_id=None, status="generated", flow_spec=NiFiFlowSpec.model_validate(safe_payload))

    def get_deployment(self, deployment_id: str) -> FlowDeployment:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT * FROM flow_deployments WHERE id=%s", (deployment_id,))
            row = cursor.fetchone()
        if row is None:
            raise KeyError(deployment_id)
        payload = row["flow_spec"] if isinstance(row["flow_spec"], dict) else json.loads(row["flow_spec"])
        return FlowDeployment(deployment_id=row["id"], assessment_id=row["assessment_id"], version=row["version"],
                              external_flow_id=row["external_flow_id"], status=row["status"], flow_spec=NiFiFlowSpec.model_validate(payload))

    def update_deployment(self, deployment_id: str, status: str, actor: str, external_flow_id: str | None = None) -> FlowDeployment:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("UPDATE flow_deployments SET status=%s, external_flow_id=COALESCE(%s,external_flow_id), updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                           (status, external_flow_id, deployment_id))
            if cursor.rowcount == 0:
                raise KeyError(deployment_id)
            self._audit(cursor, actor, f"nifi.flow.{status}", "deployment", deployment_id, "success")
        return self.get_deployment(deployment_id)

    def assistant_context(self, assessment_id: str | None = None, deployment_id: str | None = None) -> dict:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM sources")
            source_count = int(cursor.fetchone()["count"])
            cursor.execute("SELECT COUNT(*) AS count FROM flow_deployments")
            deployment_count = int(cursor.fetchone()["count"])
            if assessment_id:
                cursor.execute("SELECT payload FROM source_assessments WHERE id=%s", (assessment_id,))
            else:
                cursor.execute("SELECT payload FROM source_assessments ORDER BY created_at DESC LIMIT 1")
            assessment_row = cursor.fetchone()
            if deployment_id:
                cursor.execute("SELECT version,status FROM flow_deployments WHERE id=%s", (deployment_id,))
            else:
                cursor.execute("SELECT version,status FROM flow_deployments ORDER BY updated_at DESC LIMIT 1")
            deployment_row = cursor.fetchone()
        assessment = None
        if assessment_row:
            assessment = assessment_row["payload"] if isinstance(assessment_row["payload"], dict) else json.loads(assessment_row["payload"])
        deployment = dict(deployment_row) if deployment_row else None
        return {
            "source_count": source_count, "deployment_count": deployment_count,
            "latest_assessment": assessment, "latest_deployment": deployment,
            "assessment_summary": (f"{assessment['schema_name']}.{assessment['table_name']} quality {assessment['quality_score']}/100" if assessment else None),
            "deployment_summary": (f"NiFi v{deployment['version']} is {deployment['status']}" if deployment else None),
        }

    def save_assistant_exchange(self, request: AssistantRequest, response: AssistantResponse, actor: str) -> AssistantResponse:
        conversation_id = request.conversation_id or str(uuid4())
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("""INSERT INTO assistant_messages(id,conversation_id,actor,role,content,model,tools_used)
                              VALUES (%s,%s,%s,'user',%s,NULL,'[]'::jsonb),
                                     (%s,%s,%s,'assistant',%s,%s,%s::jsonb)""",
                           (str(uuid4()), conversation_id, actor, request.message,
                            str(uuid4()), conversation_id, actor, response.answer, response.model,
                            json.dumps([item.model_dump() for item in response.tools_used])))
            self._audit(cursor, actor, "assistant.read", "conversation", conversation_id, "success")
        return response.model_copy(update={"conversation_id": conversation_id})

    def next_proposal_version(self) -> int:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT COALESCE(MAX(version),0)+1 AS version FROM pipeline_proposals")
            return int(cursor.fetchone()["version"])

    def save_pipeline_proposal(self, proposal: PipelineProposal, assessment_id: str | None, actor: str) -> PipelineProposal:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("""INSERT INTO pipeline_proposals(id,assessment_id,version,status,requirement,spec,created_by)
                              VALUES (%s,%s,%s,'draft',%s,%s::jsonb,%s)""",
                           (proposal.proposal_id, assessment_id, proposal.version, proposal.requirement,
                            proposal.model_dump_json(), actor))
            self._audit(cursor, actor, "proposal.generated", "pipeline_proposal", proposal.proposal_id, "success")
        return proposal

    def get_pipeline_proposal(self, proposal_id: str) -> PipelineProposal:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT spec,status FROM pipeline_proposals WHERE id=%s", (proposal_id,))
            row = cursor.fetchone()
        if row is None:
            raise KeyError(proposal_id)
        payload = row["spec"] if isinstance(row["spec"], dict) else json.loads(row["spec"])
        payload["status"] = row["status"]
        return PipelineProposal.model_validate(payload)

    def get_proposal_assessment_id(self, proposal_id: str) -> str | None:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT assessment_id FROM pipeline_proposals WHERE id=%s", (proposal_id,))
            row = cursor.fetchone()
        if row is None:
            raise KeyError(proposal_id)
        return row["assessment_id"]

    def save_proposal_revision(self, proposal: PipelineProposal, assessment_id: str | None, actor: str) -> PipelineProposal:
        return self.save_pipeline_proposal(proposal, assessment_id, actor)

    def decide_pipeline_proposal(self, proposal_id: str, decision: str, reason: str | None, actor: str) -> PipelineProposal:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("UPDATE pipeline_proposals SET status=%s WHERE id=%s", (decision, proposal_id))
            if cursor.rowcount == 0:
                raise KeyError(proposal_id)
            self._audit(cursor, actor, f"proposal.{decision}", "pipeline_proposal", proposal_id, "success")
        return self.get_pipeline_proposal(proposal_id)

    @staticmethod
    def _audit(cursor, actor: str, action: str, resource_type: str, resource_id: str | None, outcome: str) -> None:
        cursor.execute("INSERT INTO audit_events(id, actor, action, resource_type, resource_id, outcome) VALUES (%s, %s, %s, %s, %s, %s)",
                       (str(uuid4()), actor, action, resource_type, resource_id, outcome))

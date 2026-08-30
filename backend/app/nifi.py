from typing import Any

import httpx

from .models import ConnectionSpec, NiFiFlowSpec, NiFiStatus, PipelineDraft, ProcessorSpec, SourceAssessment


class NiFiError(RuntimeError):
    pass


class NiFiFlowCompiler:
    def compile(self, assessment: SourceAssessment, version: int) -> NiFiFlowSpec:
        if assessment.pipeline_draft.status != "approved":
            raise ValueError("Only approved pipeline drafts can be generated")
        if assessment.recommended_runtime != "nifi":
            raise ValueError("Assessment does not recommend NiFi")
        draft: PipelineDraft = assessment.pipeline_draft
        query = "SELECT * FROM ${SOURCE_SCHEMA}.${SOURCE_TABLE}"
        processors = [
            ProcessorSpec(key="query", name="Read PostgreSQL incrementally", processor_type="org.apache.nifi.processors.standard.QueryDatabaseTableRecord",
                properties={"Database Connection Pooling Service":"${DBCP_SERVICE}", "Table Name":"${SOURCE_SCHEMA}.${SOURCE_TABLE}", "Maximum-value Columns":draft.watermark_column or "", "Fetch Size":"10000"}),
            ProcessorSpec(key="validate", name="Validate records", processor_type="org.apache.nifi.processors.standard.ValidateRecord",
                properties={"Record Reader":"${RECORD_READER}", "Schema Access Strategy":"Use 'Schema Text' Property"}),
            ProcessorSpec(key="convert", name="Convert to Parquet", processor_type="org.apache.nifi.processors.standard.ConvertRecord",
                properties={"Record Reader":"${RECORD_READER}", "Record Writer":"${PARQUET_WRITER}"}),
            ProcessorSpec(key="target", name="Write bronze data", processor_type="org.apache.nifi.processors.standard.PutFile",
                properties={"Directory":"${TARGET_PATH}", "Conflict Resolution Strategy":"replace"}, auto_terminated_relationships=["success", "failure"]),
            ProcessorSpec(key="quarantine", name="Quarantine invalid records", processor_type="org.apache.nifi.processors.standard.PutFile",
                properties={"Directory":"${QUARANTINE_PATH}", "Conflict Resolution Strategy":"replace"}, auto_terminated_relationships=["success", "failure"]),
        ]
        connections = [
            ConnectionSpec(source_key="query", destination_key="validate", relationships=["success"]),
            ConnectionSpec(source_key="validate", destination_key="convert", relationships=["valid"]),
            ConnectionSpec(source_key="validate", destination_key="quarantine", relationships=["invalid", "failure"]),
            ConnectionSpec(source_key="convert", destination_key="target", relationships=["success"]),
        ]
        return NiFiFlowSpec(
            flow_name=f"TigonD {assessment.schema_name}.{assessment.table_name}", version=version,
            assessment_id=assessment.assessment_id,
            parameters={"SOURCE_SCHEMA":assessment.schema_name, "SOURCE_TABLE":assessment.table_name,
                        "TARGET_PATH":f"/data/bronze/{assessment.schema_name}/{assessment.table_name}",
                        "QUARANTINE_PATH":f"/data/quarantine/{assessment.schema_name}/{assessment.table_name}",
                        "JDBC_URL":"", "DB_USERNAME":"", "DB_PASSWORD":"", "DBCP_SERVICE":"", "RECORD_READER":"", "PARQUET_WRITER":""},
            sensitive_parameter_names=["DB_PASSWORD"], processors=processors, connections=connections,
        )


class NiFiClient:
    def __init__(self, base_url: str, username: str = "", password: str = "", verify_ssl: bool = False, transport=None):
        auth = (username, password) if username else None
        self.client = httpx.Client(base_url=base_url.rstrip("/"), auth=auth, verify=verify_ssl, timeout=20, transport=transport, trust_env=False)

    def health(self) -> dict[str, Any]:
        response = self.client.get("/system-diagnostics")
        self._raise(response)
        diagnostics = response.json().get("systemDiagnostics", {})
        return {"status":"healthy", "heap":diagnostics.get("aggregateSnapshot", {}).get("heapUtilization", "unknown")}

    def deploy(self, spec: NiFiFlowSpec, secrets: dict[str, str]) -> str:
        root = self.client.get("/flow/process-groups/root")
        self._raise(root)
        root_id = root.json()["processGroupFlow"]["id"]
        group = self.client.post(f"/process-groups/{root_id}/process-groups", json={"revision":{"version":0}, "component":{"name":spec.flow_name, "position":{"x":100,"y":100}}})
        self._raise(group)
        group_id = group.json()["id"]
        parameter_context_id = self._create_parameter_context(spec, secrets)
        self._attach_parameter_context(group_id, parameter_context_id)
        services = self._create_controller_services(group_id)
        processor_ids: dict[str, str] = {}
        for index, processor in enumerate(spec.processors):
            properties = {key: services.get(value, value) for key, value in processor.properties.items()}
            created = self.client.post(f"/process-groups/{group_id}/processors", json={
                "revision":{"version":0}, "component":{"name":processor.name, "type":processor.processor_type,
                "position":{"x":100+(index%3)*360,"y":100+(index//3)*240}, "config":{"properties":properties,
                "autoTerminatedRelationships":processor.auto_terminated_relationships, "schedulingPeriod":"0 sec", "concurrentlySchedulableTaskCount":1}}
            })
            self._raise(created); processor_ids[processor.key] = created.json()["id"]
        for connection in spec.connections:
            self._create_connection(group_id, connection, processor_ids)
        return group_id

    def _create_controller_services(self, group_id: str) -> dict[str, str]:
        definitions = {
            "${DBCP_SERVICE}": ("PostgreSQL Pool", "org.apache.nifi.dbcp.DBCPConnectionPool", {
                "Database Connection URL":"${JDBC_URL}", "Database Driver Class Name":"org.postgresql.Driver",
                "Database User":"${DB_USERNAME}", "Password":"${DB_PASSWORD}"}),
            "${RECORD_READER}": ("JSON Record Reader", "org.apache.nifi.json.JsonTreeReader", {"Schema Access Strategy":"Infer Schema"}),
            "${PARQUET_WRITER}": ("Parquet Record Writer", "org.apache.nifi.parquet.ParquetRecordSetWriter", {"Schema Write Strategy":"Do Not Write Schema"}),
        }
        result: dict[str, str] = {}
        for placeholder, (name, service_type, properties) in definitions.items():
            response = self.client.post(f"/process-groups/{group_id}/controller-services", json={
                "revision":{"version":0}, "component":{"name":name,"type":service_type,"properties":properties}})
            self._raise(response)
            service_id = response.json()["id"]
            enabled = self.client.put(f"/controller-services/{service_id}/run-status", json={"revision":{"version":0},"state":"ENABLED"})
            self._raise(enabled); result[placeholder] = service_id
        return result

    def set_state(self, flow_id: str, state: str) -> None:
        response = self.client.put(f"/flow/process-groups/{flow_id}", json={"id":flow_id, "state":state})
        self._raise(response)

    def status(self, flow_id: str) -> NiFiStatus:
        response = self.client.get(f"/flow/process-groups/{flow_id}/status")
        self._raise(response)
        snapshot = response.json()["processGroupStatus"]["aggregateSnapshot"]
        queued_count = int(snapshot.get("flowFilesQueued", 0))
        queued_bytes = int(snapshot.get("bytesQueued", 0))
        return NiFiStatus(flow_id=flow_id, run_status=snapshot.get("runStatus", "Unknown"), queued_count=queued_count,
            queued_bytes=queued_bytes, stopped_processors=int(snapshot.get("stoppedCount", 0)),
            invalid_processors=int(snapshot.get("invalidCount", 0)), back_pressure_warning=queued_count >= 9000 or queued_bytes >= 900_000_000)

    def _create_parameter_context(self, spec: NiFiFlowSpec, secrets: dict[str, str]) -> str:
        parameters=[]
        for name, value in spec.parameters.items():
            actual = secrets.get(name, value)
            parameters.append({"parameter":{"name":name,"value":actual,"sensitive":name in spec.sensitive_parameter_names}})
        response=self.client.post("/parameter-contexts", json={"revision":{"version":0},"component":{"name":f"{spec.flow_name} v{spec.version}","parameters":parameters}})
        self._raise(response); return response.json()["id"]

    def _attach_parameter_context(self, group_id: str, context_id: str) -> None:
        response=self.client.put(f"/process-groups/{group_id}/parameter-context", json={"revision":{"version":0},"id":group_id,"component":{"id":group_id,"parameterContext":{"id":context_id}}})
        self._raise(response)

    def _create_connection(self, group_id: str, connection: ConnectionSpec, ids: dict[str, str]) -> None:
        response=self.client.post(f"/process-groups/{group_id}/connections", json={"revision":{"version":0},"component":{
            "source":{"id":ids[connection.source_key],"groupId":group_id,"type":"PROCESSOR"},
            "destination":{"id":ids[connection.destination_key],"groupId":group_id,"type":"PROCESSOR"},
            "selectedRelationships":connection.relationships,"backPressureObjectThreshold":connection.back_pressure_objects,
            "backPressureDataSizeThreshold":connection.back_pressure_size,"flowFileExpiration":"0 sec"}})
        self._raise(response)

    @staticmethod
    def _raise(response: httpx.Response) -> None:
        if response.is_error:
            raise NiFiError(f"NiFi API returned {response.status_code}: {response.text[:300]}")

import httpx

from app.models import PipelineDraft, SourceAssessment
from app.nifi import NiFiClient, NiFiFlowCompiler


def approved_assessment():
    return SourceAssessment(
        assessment_id="assessment-1", source_id="source-1", schema_name="public", table_name="customers",
        quality_score=96, pii_columns=["mobile_number"], business_key_candidates=["customer_id"],
        watermark_candidates=["updated_at"], recommended_runtime="nifi", confidence=91, runtime_scores=[],
        pipeline_draft=PipelineDraft(load_strategy="incremental", business_key="customer_id", watermark_column="updated_at",
            source_object="public.customers", target_pattern="bronze/public/customers",
            quality_gates=["completeness >= 95%"], status="approved"), summary="NiFi recommended",
    )


def test_compiler_adds_quarantine_backpressure_and_no_secret_values():
    spec = NiFiFlowCompiler().compile(approved_assessment(), 2)
    assert spec.version == 2
    assert spec.quarantine_enabled is True
    assert any(connection.destination_key == "quarantine" for connection in spec.connections)
    assert all(connection.back_pressure_objects == 10_000 for connection in spec.connections)
    assert spec.parameters["DB_PASSWORD"] == ""


def test_status_flags_back_pressure_from_nifi_rest_snapshot():
    def handler(request: httpx.Request):
        assert request.url.path.endswith("/flow/process-groups/group-1/status")
        return httpx.Response(200, json={"processGroupStatus":{"aggregateSnapshot":{
            "runStatus":"Running", "flowFilesQueued":"9500", "bytesQueued":"1000000",
            "stoppedCount":0, "invalidCount":0,
        }}})

    client = NiFiClient("http://nifi/nifi-api", transport=httpx.MockTransport(handler))
    status = client.status("group-1")
    assert status.run_status == "Running"
    assert status.back_pressure_warning is True

from uuid import uuid4

from .models import AssessmentRequest, PipelineDraft, RuntimeScore, SourceAssessment, TableProfile


PII_TERMS = {"name", "email", "phone", "mobile", "address", "passport", "national_id", "iban", "account"}
KEY_TERMS = {"id", "key", "code", "number"}
WATERMARK_TERMS = {"updated_at", "modified_at", "last_updated", "change_timestamp", "created_at"}


class IntelligenceEngine:
    """Explainable CPU-only scoring. Every point is traceable to evidence."""

    def assess(self, source_id: str, profile: TableProfile, request: AssessmentRequest) -> SourceAssessment:
        names = [column.name.lower() for column in profile.columns]
        pii = [column.name for column in profile.columns if any(term in column.name.lower() for term in PII_TERMS)]
        business_keys = [column.name for column in profile.columns if column.uniqueness >= 98 and any(term in column.name.lower() for term in KEY_TERMS)]
        watermarks = [column.name for column in profile.columns if column.name.lower() in WATERMARK_TERMS or "timestamp" in column.data_type.lower()]

        load_strategy = "cdc" if request.desired_latency == "near_real_time" else "incremental" if watermarks else "full"
        scores = self._runtime_scores(request, bool(watermarks), profile.sampled_rows, bool(pii))
        scores.sort(key=lambda item: item.score, reverse=True)
        winner = scores[0]
        confidence = min(98, max(55, winner.score - scores[1].score + 70))
        quality_gates = ["completeness >= 95%", "schema drift blocked"]
        if business_keys:
            quality_gates.append(f"{business_keys[0]} must be unique")
        if pii:
            quality_gates.append("PII fields masked outside approved zones")

        draft = PipelineDraft(
            load_strategy=load_strategy,
            business_key=business_keys[0] if business_keys else None,
            watermark_column=watermarks[0] if watermarks else None,
            source_object=f"{profile.schema_name}.{profile.table_name}",
            target_pattern=f"bronze/{profile.schema_name}/{profile.table_name}",
            quality_gates=quality_gates,
        )
        summary = (
            f"{winner.runtime} is recommended with {confidence}% confidence for a {load_strategy} load. "
            f"Assessment used {profile.sampled_rows} sampled rows, {len(names)} columns, and {len(pii)} PII candidates."
        )
        return SourceAssessment(
            assessment_id=str(uuid4()), source_id=source_id, schema_name=profile.schema_name,
            table_name=profile.table_name, quality_score=profile.quality_score, pii_columns=pii,
            business_key_candidates=business_keys, watermark_candidates=watermarks,
            recommended_runtime=winner.runtime, confidence=confidence, runtime_scores=scores,
            pipeline_draft=draft, summary=summary,
        )

    @staticmethod
    def _runtime_scores(request: AssessmentRequest, has_watermark: bool, sampled_rows: int, has_pii: bool) -> list[RuntimeScore]:
        values = {"nifi": 55, "airbyte": 52, "dlt": 48, "kafka_debezium": 35}
        evidence = {name: [] for name in values}
        risks = {name: [] for name in values}

        if request.prefer_visual_design:
            values["nifi"] += 20; evidence["nifi"].append("Visual pipeline design requested")
            values["dlt"] -= 5; risks["dlt"].append("Code-first maintenance model")
        if request.packaged_connector_available:
            values["airbyte"] += 18; evidence["airbyte"].append("Packaged connector is available")
        if request.transformation_complexity == "high":
            values["nifi"] += 12; values["dlt"] += 10
            evidence["nifi"].append("High transformation and routing complexity")
            evidence["dlt"].append("Custom Python transformations are suitable")
        elif request.transformation_complexity == "low":
            values["airbyte"] += 8; evidence["airbyte"].append("Low transformation complexity")
        if request.desired_latency == "near_real_time":
            values["kafka_debezium"] += 65; evidence["kafka_debezium"].append("Near-real-time CDC latency required")
            values["nifi"] -= 20; values["airbyte"] -= 20; values["dlt"] -= 15
            risks["nifi"].append("Flow-based polling is less suitable than log-based CDC")
            risks["airbyte"].append("Batch connector latency may miss the target")
            risks["dlt"].append("Custom polling adds operational latency risk")
        elif request.desired_latency == "hourly":
            values["nifi"] += 8; values["airbyte"] += 8
        else:
            values["nifi"] += 10; values["airbyte"] += 10
            risks["kafka_debezium"].append("Streaming infrastructure is unnecessary for daily latency")
        if has_watermark:
            values["nifi"] += 8; values["dlt"] += 8
            evidence["nifi"].append("Incremental watermark column detected")
            evidence["dlt"].append("Incremental state can use the detected watermark")
        if sampled_rows == 0:
            for name in values: risks[name].append("No data rows were available for profiling")
        if has_pii:
            values["nifi"] += 5; evidence["nifi"].append("PII routing and quarantine controls are required")

        return [RuntimeScore(runtime=name, score=max(0, min(100, score)), evidence=evidence[name] or ["Compatible with the source"], risks=risks[name]) for name, score in values.items()]

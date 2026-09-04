"""Durable storage for incident diagnoses, memory and recommendation feedback."""
import json
from threading import Lock

import psycopg
from psycopg.rows import dict_row

from ..models import IncidentDiagnosis, MemoryRecord, RecommendationFeedback

MEMORY_LIMIT = 200


class PostgresIntelligenceStore:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def add_incident(self, diagnosis: IncidentDiagnosis) -> None:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute(
                """INSERT INTO incidents(id, deployment_id, category, severity, status, payload)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (diagnosis.incident_id, diagnosis.deployment_id, diagnosis.category,
                 diagnosis.severity, diagnosis.status, json.dumps(diagnosis.model_dump())),
            )

    def incidents_for_deployment(self, deployment_id: str) -> list[IncidentDiagnosis]:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT payload FROM incidents WHERE deployment_id = %s ORDER BY created_at",
                (deployment_id,),
            )
            return [IncidentDiagnosis(**row["payload"]) for row in cursor.fetchall()]

    def open_incidents(self) -> list[IncidentDiagnosis]:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT payload FROM incidents WHERE status = 'open' ORDER BY created_at")
            return [IncidentDiagnosis(**row["payload"]) for row in cursor.fetchall()]

    def add_memory(self, record: MemoryRecord) -> None:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO intelligence_memory(id, scope, subject_id, fact, source) VALUES (%s, %s, %s, %s, %s)",
                (record.memory_id, record.scope, record.subject_id, record.fact, record.source),
            )

    def search_memory(self, terms: list[str], scope: str | None) -> list[MemoryRecord]:
        """Postgres filters candidate rows; the caller ranks them by term overlap."""
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute(
                """SELECT id AS memory_id, scope, subject_id, fact, source, created_at::text
                     FROM intelligence_memory
                    WHERE (%s::text IS NULL OR scope = %s)
                      AND (cardinality(%s::text[]) = 0
                           OR EXISTS (SELECT 1 FROM unnest(%s::text[]) AS term
                                       WHERE subject_id ILIKE '%%' || term || '%%'
                                          OR fact ILIKE '%%' || term || '%%'
                                          OR source ILIKE '%%' || term || '%%'))
                 ORDER BY created_at DESC
                    LIMIT %s""",
                (scope, scope, terms, terms, MEMORY_LIMIT),
            )
            return [MemoryRecord(**row) for row in cursor.fetchall()]

    def add_feedback(self, item: RecommendationFeedback) -> None:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute(
                """INSERT INTO recommendation_feedback(id, recommendation_id, accepted, outcome, notes)
                   VALUES (gen_random_uuid()::text, %s, %s, %s, %s)""",
                (item.recommendation_id, item.accepted, item.outcome, item.notes),
            )

    def feedback_totals(self) -> tuple[int, int, int]:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute(
                """SELECT COUNT(*) AS total,
                          COUNT(*) FILTER (WHERE accepted) AS accepted,
                          COUNT(*) FILTER (WHERE outcome = 'successful') AS successful
                     FROM recommendation_feedback"""
            )
            row = cursor.fetchone()
        return row["total"], row["accepted"], row["successful"]


class InMemoryIntelligenceStore:
    def __init__(self):
        self._incidents: list[IncidentDiagnosis] = []
        self._memory: list[MemoryRecord] = []
        self._feedback: list[RecommendationFeedback] = []
        self._lock = Lock()

    def add_incident(self, diagnosis: IncidentDiagnosis) -> None:
        with self._lock:
            self._incidents.append(diagnosis)

    def incidents_for_deployment(self, deployment_id: str) -> list[IncidentDiagnosis]:
        return [item for item in self._incidents if item.deployment_id == deployment_id]

    def open_incidents(self) -> list[IncidentDiagnosis]:
        return [item for item in self._incidents if item.status == "open"]

    def add_memory(self, record: MemoryRecord) -> None:
        with self._lock:
            self._memory.append(record)

    def search_memory(self, terms: list[str], scope: str | None) -> list[MemoryRecord]:
        candidates = [item for item in self._memory if scope is None or item.scope == scope]
        if not terms:
            return candidates[-MEMORY_LIMIT:]
        return [
            item for item in candidates[-MEMORY_LIMIT:]
            if any(term in f"{item.subject_id} {item.fact} {item.source}".lower() for term in terms)
        ]

    def add_feedback(self, item: RecommendationFeedback) -> None:
        with self._lock:
            self._feedback.append(item)

    def feedback_totals(self) -> tuple[int, int, int]:
        return (
            len(self._feedback),
            sum(item.accepted for item in self._feedback),
            sum(item.outcome == "successful" for item in self._feedback),
        )

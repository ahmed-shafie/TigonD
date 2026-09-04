"""Durable storage for approval-controlled operational actions."""
import json
from datetime import datetime
from threading import Lock

import psycopg
from psycopg.rows import dict_row

from ..models import OperationalAction

COLUMNS = "id, deployment_id, action, status, payload, token_hash, idempotency_key, expires_at"


class PostgresOperationalActionStore:
    """Every transition is a conditional UPDATE so concurrent workers cannot both win."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def insert(self, action: OperationalAction) -> None:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO operational_actions({COLUMNS}) VALUES (%s, %s, %s, %s, %s, NULL, NULL, %s)",
                (action.action_id, action.deployment_id, action.action, action.status,
                 json.dumps(action.model_dump()), datetime.fromisoformat(action.approval_expires_at)),
            )

    def get(self, action_id: str) -> OperationalAction | None:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT payload FROM operational_actions WHERE id = %s", (action_id,))
            row = cursor.fetchone()
        return OperationalAction(**row["payload"]) if row else None

    def find_by_idempotency_key(self, idempotency_key: str) -> OperationalAction | None:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT payload FROM operational_actions WHERE idempotency_key = %s", (idempotency_key,))
            row = cursor.fetchone()
        return OperationalAction(**row["payload"]) if row else None

    def token_hash(self, action_id: str) -> str | None:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT token_hash FROM operational_actions WHERE id = %s", (action_id,))
            row = cursor.fetchone()
        return row["token_hash"] if row else None

    def update(
        self,
        action: OperationalAction,
        expected_status: str,
        token_hash: str | None = None,
        idempotency_key: str | None = None,
    ) -> OperationalAction | None:
        with self.connect() as db, db.cursor() as cursor:
            cursor.execute(
                """UPDATE operational_actions
                      SET status = %s, payload = %s, token_hash = %s,
                          idempotency_key = COALESCE(%s, idempotency_key)
                    WHERE id = %s AND status = %s
                RETURNING payload""",
                (action.status, json.dumps(action.model_dump()), token_hash, idempotency_key,
                 action.action_id, expected_status),
            )
            row = cursor.fetchone()
        return OperationalAction(**row["payload"]) if row else None


class InMemoryOperationalActionStore:
    """Single-process store with the same conditional-update contract, used by tests."""

    def __init__(self):
        self._actions: dict[str, OperationalAction] = {}
        self._token_hashes: dict[str, str | None] = {}
        self._idempotency: dict[str, str] = {}
        self._lock = Lock()

    def insert(self, action: OperationalAction) -> None:
        with self._lock:
            self._actions[action.action_id] = action

    def get(self, action_id: str) -> OperationalAction | None:
        return self._actions.get(action_id)

    def find_by_idempotency_key(self, idempotency_key: str) -> OperationalAction | None:
        action_id = self._idempotency.get(idempotency_key)
        return self._actions.get(action_id) if action_id else None

    def token_hash(self, action_id: str) -> str | None:
        return self._token_hashes.get(action_id)

    def update(
        self,
        action: OperationalAction,
        expected_status: str,
        token_hash: str | None = None,
        idempotency_key: str | None = None,
    ) -> OperationalAction | None:
        with self._lock:
            stored = self._actions.get(action.action_id)
            if stored is None or stored.status != expected_status:
                return None
            self._actions[action.action_id] = action
            self._token_hashes[action.action_id] = token_hash
            if idempotency_key:
                self._idempotency[idempotency_key] = action.action_id
            return action

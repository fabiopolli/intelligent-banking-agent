from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from typing import Iterator
from uuid import uuid4

from app.config import settings


@dataclass(frozen=True)
class AuditExecutionContext:
    actor_id: str
    actor_role: str
    customer_id: str
    session_id: str
    trace_id: str


_AUDIT_CONTEXT: ContextVar[AuditExecutionContext | None] = ContextVar(
    "audit_execution_context",
    default=None,
)


@contextmanager
def audit_execution_scope(context: AuditExecutionContext) -> Iterator[None]:
    token = _AUDIT_CONTEXT.set(context)
    try:
        yield
    finally:
        _AUDIT_CONTEXT.reset(token)


class AuditLogService:
    def __init__(self) -> None:
        self._events: list[dict] = []
        self._idempotency_index: dict[str, dict] = {}

    @property
    def uses_postgres(self) -> bool:
        return settings.audit_store.lower() == "postgres"

    def reset(self) -> None:
        self._events = []
        self._idempotency_index = {}

    def append(
        self,
        customer_id: str,
        event_type: str,
        payload: dict,
        *,
        status: str = "executed",
        reason: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        context = _AUDIT_CONTEXT.get()
        event_id = str(uuid4())
        timestamp = datetime.now(UTC).isoformat()
        normalized_payload = deepcopy(payload)
        event = {
            "event_id": event_id,
            "idempotency_key": idempotency_key or event_id,
            "actor_id": context.actor_id if context else customer_id,
            "actor_role": context.actor_role if context else "customer",
            "customer_id": customer_id,
            "session_id": context.session_id if context else None,
            "trace_id": context.trace_id if context else None,
            "event_type": event_type,
            "action": event_type,
            "status": status,
            "reason": reason,
            "amount": normalized_payload.get("amount"),
            "timestamp": timestamp,
            "payload": normalized_payload,
        }
        if self.uses_postgres:
            return self._append_postgres(event)

        existing = self._idempotency_index.get(event["idempotency_key"])
        if existing is not None:
            return deepcopy(existing)
        previous_hash = self._events[-1]["event_hash"] if self._events else None
        event["previous_hash"] = previous_hash
        event["event_hash"] = self._hash_event(event)
        self._events.append(event)
        self._idempotency_index[event["idempotency_key"]] = event
        return self._serialize(event)

    def list_by_customer(self, customer_id: str) -> list[dict]:
        if self.uses_postgres:
            return self._list_postgres(customer_id)
        return [self._serialize(event) for event in self._events if event["customer_id"] == customer_id]

    def verify_integrity(self) -> dict:
        events = self._all_postgres() if self.uses_postgres else deepcopy(self._events)
        previous_hash = None
        for event in events:
            if event.get("previous_hash") != previous_hash or event.get("event_hash") != self._hash_event(event):
                return {"valid": False, "event_count": len(events), "failed_event_id": event.get("event_id")}
            previous_hash = event["event_hash"]
        return {"valid": True, "event_count": len(events), "failed_event_id": None}

    def _append_postgres(self, event: dict) -> dict:
        import psycopg

        with psycopg.connect(settings.database_url) as connection:
            with connection.cursor() as cursor:
                self._ensure_schema(cursor)
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (7241901,))
                cursor.execute(
                    "SELECT event_hash FROM critical_audit_events ORDER BY sequence DESC LIMIT 1"
                )
                previous = cursor.fetchone()
                event["previous_hash"] = previous[0] if previous else None
                event["event_hash"] = self._hash_event(event)
                cursor.execute(
                    """
                    INSERT INTO critical_audit_events (
                        event_id, idempotency_key, actor_id, actor_role, customer_id,
                        session_id, trace_id, event_type, action, status, reason, amount,
                        timestamp, payload, previous_hash, event_hash
                    ) VALUES (
                        %(event_id)s, %(idempotency_key)s, %(actor_id)s, %(actor_role)s,
                        %(customer_id)s, %(session_id)s, %(trace_id)s, %(event_type)s,
                        %(action)s, %(status)s, %(reason)s, %(amount)s, %(timestamp)s,
                        %(payload)s::jsonb, %(previous_hash)s, %(event_hash)s
                    )
                    ON CONFLICT (idempotency_key) DO NOTHING
                    RETURNING sequence
                    """,
                    {**event, "payload": json.dumps(event["payload"], ensure_ascii=False)},
                )
                inserted = cursor.fetchone()
                if inserted is None:
                    cursor.execute(
                        "SELECT * FROM critical_audit_events WHERE idempotency_key = %s",
                        (event["idempotency_key"],),
                    )
                    return self._row_to_event(cursor, cursor.fetchone())
        return self._serialize(event)

    def _list_postgres(self, customer_id: str) -> list[dict]:
        return [event for event in self._all_postgres() if event["customer_id"] == customer_id]

    def _all_postgres(self) -> list[dict]:
        import psycopg

        with psycopg.connect(settings.database_url) as connection:
            with connection.cursor() as cursor:
                self._ensure_schema(cursor)
                cursor.execute("SELECT * FROM critical_audit_events ORDER BY sequence")
                rows = cursor.fetchall()
                return [self._row_to_event(cursor, row) for row in rows]

    def _ensure_schema(self, cursor) -> None:  # noqa: ANN001
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS critical_audit_events (
                sequence BIGSERIAL PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE,
                idempotency_key TEXT NOT NULL UNIQUE,
                actor_id TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                session_id TEXT,
                trace_id TEXT,
                event_type TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT,
                amount DOUBLE PRECISION,
                timestamp TEXT NOT NULL,
                payload JSONB NOT NULL,
                previous_hash TEXT,
                event_hash TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION reject_critical_audit_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'critical_audit_events is append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        cursor.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_trigger WHERE tgname = 'critical_audit_append_only'
                ) THEN
                    CREATE TRIGGER critical_audit_append_only
                    BEFORE UPDATE OR DELETE ON critical_audit_events
                    FOR EACH ROW EXECUTE FUNCTION reject_critical_audit_mutation();
                END IF;
            END
            $$
            """
        )

    @staticmethod
    def _row_to_event(cursor, row) -> dict:  # noqa: ANN001
        event = dict(zip([description.name for description in cursor.description], row))
        event.pop("sequence", None)
        return AuditLogService._serialize(event)

    @staticmethod
    def _serialize(event: dict) -> dict:
        serialized = deepcopy(event)
        serialized["user"] = serialized.get("actor_id") or serialized["customer_id"]
        return serialized

    @staticmethod
    def _hash_event(event: dict) -> str:
        canonical = json.dumps(
            {
                key: event.get(key)
                for key in (
                    "event_id",
                    "idempotency_key",
                    "actor_id",
                    "actor_role",
                    "customer_id",
                    "session_id",
                    "trace_id",
                    "event_type",
                    "action",
                    "status",
                    "reason",
                    "amount",
                    "timestamp",
                    "payload",
                    "previous_hash",
                )
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


audit_log_service = AuditLogService()

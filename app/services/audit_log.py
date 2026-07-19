from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from uuid import uuid4


@dataclass
class AuditEvent:
    event_id: str
    customer_id: str
    event_type: str
    timestamp: str
    payload: dict
    previous_hash: str | None
    event_hash: str


class AuditLogService:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def reset(self) -> None:
        self._events = []

    def append(self, customer_id: str, event_type: str, payload: dict) -> dict:
        previous_hash = self._events[-1].event_hash if self._events else None
        timestamp = datetime.now(UTC).isoformat()
        normalized_payload = deepcopy(payload)
        event_id = str(uuid4())
        event = AuditEvent(
            event_id=event_id,
            customer_id=customer_id,
            event_type=event_type,
            timestamp=timestamp,
            payload=normalized_payload,
            previous_hash=previous_hash,
            event_hash=self._hash_event(
                event_id,
                customer_id,
                event_type,
                timestamp,
                normalized_payload,
                previous_hash,
            ),
        )
        self._events.append(event)
        return self._serialize(event)

    def list_by_customer(self, customer_id: str) -> list[dict]:
        return [self._serialize(event) for event in self._events if event.customer_id == customer_id]

    def _serialize(self, event: AuditEvent) -> dict:
        return {
            "event_id": event.event_id,
            "customer_id": event.customer_id,
            "event_type": event.event_type,
            "timestamp": event.timestamp,
            "payload": deepcopy(event.payload),
            "user": event.customer_id,
            "action": event.event_type,
            "amount": event.payload.get("amount"),
            "previous_hash": event.previous_hash,
            "event_hash": event.event_hash,
        }

    def _hash_event(
        self,
        event_id: str,
        customer_id: str,
        event_type: str,
        timestamp: str,
        payload: dict,
        previous_hash: str | None,
    ) -> str:
        canonical = json.dumps(
            {
                "event_id": event_id,
                "customer_id": customer_id,
                "event_type": event_type,
                "timestamp": timestamp,
                "payload": payload,
                "previous_hash": previous_hash,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


audit_log_service = AuditLogService()

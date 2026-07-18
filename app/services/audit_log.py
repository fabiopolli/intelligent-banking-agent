from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4


@dataclass
class AuditEvent:
    event_id: str
    customer_id: str
    event_type: str
    timestamp: str
    payload: dict


class AuditLogService:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def reset(self) -> None:
        self._events = []

    def append(self, customer_id: str, event_type: str, payload: dict) -> dict:
        event = AuditEvent(
            event_id=str(uuid4()),
            customer_id=customer_id,
            event_type=event_type,
            timestamp=datetime.now(UTC).isoformat(),
            payload=deepcopy(payload),
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
        }


audit_log_service = AuditLogService()

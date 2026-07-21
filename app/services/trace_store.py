from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone


class TraceStore:
    def __init__(self) -> None:
        self._traces: dict[str, list[dict]] = {}

    def record(self, session_id: str, payload: dict) -> None:
        history = self._traces.setdefault(session_id, [])
        history.append(
            {
                "sequence": len(history) + 1,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "trace": deepcopy(payload),
            }
        )

    def get(self, session_id: str) -> dict | None:
        history = self._traces.get(session_id)
        if not history:
            return None
        return deepcopy(history[-1]["trace"])

    def history(self, session_id: str) -> list[dict]:
        return deepcopy(self._traces.get(session_id, []))

    def hitl_summary(self, session_id: str) -> dict:
        events: list[dict] = []
        status = "not_used"
        correlation_id = None
        for record in self._traces.get(session_id, []):
            hitl = record["trace"].get("observability", {}).get("hitl") or {}
            if not hitl:
                continue
            correlation_id = hitl.get("correlation_id") or correlation_id
            status = hitl.get("status") or status
            for event in hitl.get("events") or []:
                events.append(
                    {
                        **deepcopy(event),
                        "correlation_id": hitl.get("correlation_id"),
                        "sequence": record["sequence"],
                        "recorded_at": record["recorded_at"],
                    }
                )
        created_event = next((event for event in events if event.get("type") == "created"), None)
        completed_event = next(
            (event for event in reversed(events) if event.get("type") == "completed"),
            None,
        )
        duration_ms = None
        if created_event and completed_event:
            started_at = datetime.fromisoformat(created_event["recorded_at"])
            completed_at = datetime.fromisoformat(completed_event["recorded_at"])
            duration_ms = max(0, round((completed_at - started_at).total_seconds() * 1000))
        return {
            "encountered": bool(events),
            "status": status,
            "correlation_id": correlation_id,
            "created_count": sum(event.get("type") == "created" for event in events),
            "resumed_count": sum(event.get("type") == "resumed" for event in events),
            "duration_ms": duration_ms,
            "events": events,
        }

    def reset(self) -> None:
        self._traces.clear()


trace_store = TraceStore()

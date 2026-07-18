from __future__ import annotations

from copy import deepcopy


class TraceStore:
    def __init__(self) -> None:
        self._traces: dict[str, dict] = {}

    def record(self, session_id: str, payload: dict) -> None:
        self._traces[session_id] = deepcopy(payload)

    def get(self, session_id: str) -> dict | None:
        trace = self._traces.get(session_id)
        if trace is None:
            return None
        return deepcopy(trace)

    def reset(self) -> None:
        self._traces.clear()


trace_store = TraceStore()

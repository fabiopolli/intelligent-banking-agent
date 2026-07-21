from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

from app.config import settings
from app.services.orchestrator import PendingLimitOperation, PendingPixOperation


class CheckpointStore:
    def __init__(self, storage_path: str | Path | None = None) -> None:
        self._storage_path = Path(storage_path or settings.checkpoint_store_path)

    def save_pending_pix(self, session_id: str, operation: PendingPixOperation) -> None:
        checkpoints = self._read_all()
        checkpoints[session_id] = {
            "type": "pending_pix",
            "customer_id": operation.customer_id,
            "amount": operation.amount,
            "destination_key": operation.destination_key,
            "correlation_id": operation.correlation_id,
        }
        self._write_all(checkpoints)

    def get_pending_pix(self, session_id: str) -> PendingPixOperation | None:
        raw_operation = self._read_all().get(session_id)
        if raw_operation is None or raw_operation.get("type") != "pending_pix":
            return None
        return PendingPixOperation(
            customer_id=str(raw_operation["customer_id"]),
            amount=float(raw_operation["amount"]),
            destination_key=str(raw_operation["destination_key"]),
            correlation_id=self._pix_correlation_id(session_id, raw_operation),
        )

    def consume_pending_pix(self, session_id: str) -> PendingPixOperation | None:
        checkpoints = self._read_all()
        raw_operation = checkpoints.get(session_id)
        if raw_operation is None or raw_operation.get("type") != "pending_pix":
            return None
        checkpoints.pop(session_id)
        self._write_all(checkpoints)
        return PendingPixOperation(
            customer_id=str(raw_operation["customer_id"]),
            amount=float(raw_operation["amount"]),
            destination_key=str(raw_operation["destination_key"]),
            correlation_id=self._pix_correlation_id(session_id, raw_operation),
        )

    @staticmethod
    def _pix_correlation_id(session_id: str, raw_operation: dict) -> str:
        stored = str(raw_operation.get("correlation_id") or "").strip()
        if stored:
            return stored
        legacy_key = (
            f"case-itau:pix:{session_id}:{raw_operation.get('customer_id')}:"
            f"{raw_operation.get('amount')}:{raw_operation.get('destination_key')}"
        )
        return str(uuid5(NAMESPACE_URL, legacy_key))

    def save_pending_limit(self, session_id: str, operation: PendingLimitOperation) -> None:
        checkpoints = self._read_all()
        checkpoints[session_id] = {
            "type": "pending_limit",
            "customer_id": operation.customer_id,
            "requested_limit": operation.requested_limit,
        }
        self._write_all(checkpoints)

    def get_pending_limit(self, session_id: str) -> PendingLimitOperation | None:
        raw_operation = self._read_all().get(session_id)
        if raw_operation is None or raw_operation.get("type") != "pending_limit":
            return None
        return PendingLimitOperation(
            customer_id=str(raw_operation["customer_id"]),
            requested_limit=float(raw_operation["requested_limit"]),
        )

    def consume_pending_limit(self, session_id: str) -> PendingLimitOperation | None:
        checkpoints = self._read_all()
        raw_operation = checkpoints.get(session_id)
        if raw_operation is None or raw_operation.get("type") != "pending_limit":
            return None
        checkpoints.pop(session_id)
        self._write_all(checkpoints)
        return PendingLimitOperation(
            customer_id=str(raw_operation["customer_id"]),
            requested_limit=float(raw_operation["requested_limit"]),
        )

    def save_pix_draft(self, session_id: str, draft: dict[str, str | float]) -> None:
        checkpoints = self._read_all()
        checkpoints[session_id] = {"type": "pix_draft", **draft}
        self._write_all(checkpoints)

    def get_pix_draft(self, session_id: str) -> dict[str, str | float] | None:
        raw_operation = self._read_all().get(session_id)
        if raw_operation is None or raw_operation.get("type") != "pix_draft":
            return None
        return {
            key: value
            for key, value in raw_operation.items()
            if key in {"amount", "destination_key", "recipient_name"}
        }

    def consume_pix_draft(self, session_id: str) -> dict[str, str | float] | None:
        checkpoints = self._read_all()
        raw_operation = checkpoints.get(session_id)
        if raw_operation is None or raw_operation.get("type") != "pix_draft":
            return None
        checkpoints.pop(session_id)
        self._write_all(checkpoints)
        return {
            key: value
            for key, value in raw_operation.items()
            if key in {"amount", "destination_key", "recipient_name"}
        }

    def save_limit_draft(self, session_id: str, draft: dict[str, str | float]) -> None:
        checkpoints = self._read_all()
        checkpoints[session_id] = {"type": "limit_draft", **draft}
        self._write_all(checkpoints)

    def get_limit_draft(self, session_id: str) -> dict[str, str | float] | None:
        raw_operation = self._read_all().get(session_id)
        if raw_operation is None or raw_operation.get("type") != "limit_draft":
            return None
        return {
            key: value
            for key, value in raw_operation.items()
            if key in {"customer_id"}
        }

    def consume_limit_draft(self, session_id: str) -> dict[str, str | float] | None:
        checkpoints = self._read_all()
        raw_operation = checkpoints.get(session_id)
        if raw_operation is None or raw_operation.get("type") != "limit_draft":
            return None
        checkpoints.pop(session_id)
        self._write_all(checkpoints)
        return {
            key: value
            for key, value in raw_operation.items()
            if key in {"customer_id"}
        }

    def save_documental_draft(self, session_id: str, draft: dict[str, str]) -> None:
        checkpoints = self._read_all()
        current = checkpoints.get(session_id)
        if current is not None and current.get("type") != "documental_draft":
            return
        checkpoints[session_id] = {"type": "documental_draft", **draft}
        self._write_all(checkpoints)

    def get_documental_draft(self, session_id: str) -> dict[str, str] | None:
        raw_operation = self._read_all().get(session_id)
        if raw_operation is None or raw_operation.get("type") != "documental_draft":
            return None
        return {
            key: str(value)
            for key, value in raw_operation.items()
            if key in {"last_query"}
        }

    def reset(self) -> None:
        if self._storage_path.exists():
            self._storage_path.unlink()

    def _read_all(self) -> dict[str, dict]:
        if not self._storage_path.exists():
            return {}

        with self._storage_path.open("r", encoding="utf-8") as checkpoint_file:
            loaded = json.load(checkpoint_file)

        if not isinstance(loaded, dict):
            raise ValueError("Checkpoint store invalido.")
        return loaded

    def _write_all(self, checkpoints: dict[str, dict]) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._storage_path.with_suffix(".tmp")
        with temporary_path.open("w", encoding="utf-8") as checkpoint_file:
            json.dump(checkpoints, checkpoint_file, ensure_ascii=False, indent=2, sort_keys=True)
        temporary_path.replace(self._storage_path)


checkpoint_store = CheckpointStore()

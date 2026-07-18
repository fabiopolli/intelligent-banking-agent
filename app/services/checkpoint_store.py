from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.services.orchestrator import PendingPixOperation


class CheckpointStore:
    def __init__(self, storage_path: str | Path | None = None) -> None:
        self._storage_path = Path(storage_path or settings.checkpoint_store_path)

    def save_pending_pix(self, session_id: str, operation: PendingPixOperation) -> None:
        checkpoints = self._read_all()
        checkpoints[session_id] = {
            "customer_id": operation.customer_id,
            "amount": operation.amount,
            "destination_key": operation.destination_key,
        }
        self._write_all(checkpoints)

    def get_pending_pix(self, session_id: str) -> PendingPixOperation | None:
        raw_operation = self._read_all().get(session_id)
        if raw_operation is None:
            return None
        return PendingPixOperation(
            customer_id=str(raw_operation["customer_id"]),
            amount=float(raw_operation["amount"]),
            destination_key=str(raw_operation["destination_key"]),
        )

    def consume_pending_pix(self, session_id: str) -> PendingPixOperation | None:
        checkpoints = self._read_all()
        raw_operation = checkpoints.pop(session_id, None)
        if raw_operation is None:
            return None
        self._write_all(checkpoints)
        return PendingPixOperation(
            customer_id=str(raw_operation["customer_id"]),
            amount=float(raw_operation["amount"]),
            destination_key=str(raw_operation["destination_key"]),
        )

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

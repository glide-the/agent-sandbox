"""Small durable record store for accepted model tasks and idempotency."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any


class IdempotencyConflict(ValueError):
    pass


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class MusicTaskStore:
    _namespace = uuid.UUID("c4a07e68-3647-4c46-8c35-17a1bd576065")

    def __init__(self, root: str, retention_seconds: int = 604800):
        self.root = Path(root).expanduser()
        self.tasks_root = self.root / "tasks"
        self.idempotency_root = self.root / "idempotency"
        self.retention_seconds = int(retention_seconds)
        self._lock = threading.RLock()

    def _ensure(self) -> None:
        self.tasks_root.mkdir(parents=True, exist_ok=True)
        self.idempotency_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _write_atomic(path: Path, value: dict) -> None:
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, path)

    def task_dir(self, task_id: str) -> Path:
        if not re_safe_identifier(task_id):
            raise ValueError("invalid task id")
        return self.tasks_root / task_id

    def create_or_get(
        self,
        *,
        owner_id: str,
        idempotency_key: str,
        task_name: str,
        public_payload: dict,
        execution_profile_digest: str,
    ) -> tuple[dict, bool]:
        if not idempotency_key or len(idempotency_key) > 200:
            raise ValueError(
                "Idempotency-Key is required and must be at most 200 characters"
            )
        self._ensure()
        request_digest = canonical_digest(
            {"task_name": task_name, "payload": public_payload}
        )
        task_id = (
            "music_" + uuid.uuid5(self._namespace, f"{owner_id}\0{idempotency_key}").hex
        )
        index_name = hashlib.sha256(
            f"{owner_id}\0{idempotency_key}".encode("utf-8")
        ).hexdigest()
        index_path = self.idempotency_root / f"{index_name}.json"
        with self._lock:
            if index_path.exists():
                existing = json.loads(index_path.read_text(encoding="utf-8"))
                try:
                    existing_record = self.read(existing["task_id"])
                except KeyError:
                    index_path.unlink()
                else:
                    if existing["request_digest"] != request_digest:
                        raise IdempotencyConflict(
                            "Idempotency-Key was already used for a different request"
                        )
                    return existing_record, False
            task_dir = self.task_dir(task_id)
            task_dir.mkdir(parents=False, exist_ok=False)
            now = time.time()
            record = {
                "task_id": task_id,
                "owner_id": owner_id,
                "task_name": task_name,
                "request_digest": request_digest,
                "execution_profile_digest": execution_profile_digest,
                "idempotency_index": index_name,
                "public_payload": public_payload,
                "created_at": now,
                "updated_at": now,
                "state": {"task_id": task_id, "info": "pending", "finished": False},
            }
            self._write_atomic(task_dir / "task.json", record)
            self._write_atomic(
                index_path,
                {"task_id": task_id, "request_digest": request_digest},
            )
            return record, True

    def read(self, task_id: str) -> dict:
        path = self.task_dir(task_id) / "task.json"
        if not path.is_file():
            raise KeyError(task_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def update_state(self, task_id: str, state: dict) -> dict:
        with self._lock:
            record = self.read(task_id)
            record["state"] = state
            record["updated_at"] = time.time()
            self._write_atomic(self.task_dir(task_id) / "task.json", record)
            return record

    def recover_state(self, task_id: str) -> dict:
        """Return the best durable state without mutating it (safe for GET)."""
        record = self.read(task_id)
        manifest = self.task_dir(task_id) / "result-manifest.json"
        if manifest.is_file() and not record["state"].get("finished"):
            result = json.loads(manifest.read_text(encoding="utf-8"))
            return {
                "task_id": task_id,
                "info": "end" if result.get("delivery_status") == "ready" else "error",
                "finished": True,
                "result": result,
            }
        return record["state"]

    def records(self) -> list[dict]:
        if not self.tasks_root.exists():
            return []
        result = []
        for path in sorted(self.tasks_root.iterdir()):
            if not path.is_dir():
                continue
            try:
                result.append(self.read(path.name))
            except (KeyError, ValueError, json.JSONDecodeError):
                continue
        return result

    def reconcile_startup(self) -> list[dict]:
        """Persist completed manifests and mark abandoned executions interrupted."""
        reconciled = []
        for record in self.records():
            task_id = record["task_id"]
            state = record["state"]
            recovered = self.recover_state(task_id)
            if recovered != state:
                record = self.update_state(task_id, recovered)
            elif not state.get("finished") and state.get("info") != "pending":
                recovered = {
                    "task_id": task_id,
                    "info": "interrupted",
                    "finished": True,
                    "result": {
                        "stage": "interrupted",
                        "outcome": "failed",
                        "model_completed": False,
                        "delivery_status": "failed",
                        "artifacts": [],
                        "error": {
                            "kind": "service_restart",
                            "message": (
                                "task execution was interrupted; it was not resampled"
                            ),
                        },
                    },
                }
                record = self.update_state(task_id, recovered)
            reconciled.append(record)
        return reconciled

    def prune(self, now: float | None = None) -> list[str]:
        now = now or time.time()
        removed: list[str] = []
        if not self.tasks_root.exists():
            return removed
        for path in self.tasks_root.iterdir():
            try:
                record = self.read(path.name)
            except (KeyError, ValueError, json.JSONDecodeError):
                continue
            if (
                record.get("state", {}).get("finished")
                and now - record.get("updated_at", now) > self.retention_seconds
            ):
                import shutil

                shutil.rmtree(path)
                index_name = record.get("idempotency_index")
                if index_name:
                    (self.idempotency_root / f"{index_name}.json").unlink(
                        missing_ok=True
                    )
                removed.append(path.name)
        return removed


def re_safe_identifier(value: str) -> bool:
    return (
        bool(value)
        and len(value) <= 200
        and all(character.isalnum() or character in "_.-" for character in value)
    )

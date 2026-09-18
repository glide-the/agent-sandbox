import hashlib
import json

import pytest
from fastapi import HTTPException

from sandbox.server.music_auth import MusicAuth
from sandbox.server.music_task_store import IdempotencyConflict, MusicTaskStore


def test_auth_uses_token_digest_and_owner(tmp_path):
    token = "test-secret"
    path = tmp_path / "keys.json"
    path.write_text(json.dumps({hashlib.sha256(token.encode()).hexdigest(): "alice"}))
    path.chmod(0o600)
    auth = MusicAuth(str(path))
    assert auth.authenticate_header(f"Bearer {token}") == "alice"
    with pytest.raises(HTTPException) as error:
        auth.authenticate_header("Bearer wrong")
    assert error.value.status_code == 401


def test_auth_disabled_uses_fixed_local_principal():
    auth = MusicAuth(None, required=False, anonymous_principal="local")
    assert auth.authenticate_header(None) == "local"
    assert auth.authenticate_header("Bearer ignored") == "local"


def test_idempotency_returns_same_task_and_conflicts_on_changed_request(tmp_path):
    store = MusicTaskStore(str(tmp_path))
    kwargs = dict(
        owner_id="alice",
        idempotency_key="one",
        task_name="yue2_task",
        public_payload={"operation": "generate"},
        execution_profile_digest="profile",
    )
    first, created = store.create_or_get(**kwargs)
    second, created_again = store.create_or_get(**kwargs)
    assert created is True and created_again is False
    assert first["task_id"] == second["task_id"]
    with pytest.raises(IdempotencyConflict):
        store.create_or_get(**{**kwargs, "public_payload": {"operation": "plan"}})
    with pytest.raises(ValueError):
        store.task_dir("../escape")


def test_get_recovery_is_read_only_and_startup_reconciles(tmp_path):
    store = MusicTaskStore(str(tmp_path))
    record, _ = store.create_or_get(
        owner_id="alice",
        idempotency_key="one",
        task_name="yue2_task",
        public_payload={"operation": "generate"},
        execution_profile_digest="p",
    )
    manifest = store.task_dir(record["task_id"]) / "result-manifest.json"
    manifest.write_text(json.dumps({"delivery_status": "ready", "artifacts": []}))
    before = (store.task_dir(record["task_id"]) / "task.json").read_bytes()
    assert store.recover_state(record["task_id"])["finished"] is True
    assert (store.task_dir(record["task_id"]) / "task.json").read_bytes() == before
    store.reconcile_startup()
    assert store.read(record["task_id"])["state"]["finished"] is True

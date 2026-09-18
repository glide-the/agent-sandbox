import hashlib
import json
from collections import deque

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sandbox.processors.sheetsage2_processor import SheetSage2Processor
from sandbox.processors.yue2_processor import YuE2Processor
from sandbox.server.bootstrap.bootstrap_register import bootstrap_cache
from sandbox.server.servlet.boot.runner_bootstrap import RunnerBootstrapBaseWeb
from sandbox.server.servlet.extract_file import upload_runner_file
from sandbox.server.servlet.runner import (
    result_async,
    result_source_async,
    submit_async,
)
from sandbox.tasks import tasks_cache
from sandbox.tasks.sheetsage2_task import SheetSage2Task
from sandbox.tasks.yue2_task import YuE2Task


def make_client(tmp_path):
    token = "runner-secret"
    keys = tmp_path / "keys.json"
    keys.write_text(json.dumps({hashlib.sha256(token.encode()).hexdigest(): "alice"}))
    keys.chmod(0o600)
    bootstrap = RunnerBootstrapBaseWeb(
        "127.0.0.1",
        0,
        max_ongoing_tasks=1,
        music={
            "data_root": str(tmp_path / "data"),
            "api_keys_file": str(keys),
            "auth_required": True,
        },
        upload={"data_root": str(tmp_path / "data"), "max_input_bytes": 1000},
    )
    bootstrap._QUEUE = deque()
    bootstrap._TASK_DATA = {}
    bootstrap._TASK_STATES = {}
    bootstrap._ONGOING_TASKS = []
    bootstrap_cache["runner_bootstrap_web"] = bootstrap

    yue = YuE2Processor(
        cwd=str(tmp_path),
        environment=str(tmp_path),
        task_root=str(tmp_path),
        model_path=str(tmp_path),
        vae_path=str(tmp_path),
    )
    sheet = SheetSage2Processor(
        cwd=str(tmp_path),
        environment=str(tmp_path),
        task_root=str(tmp_path),
        model_path=str(tmp_path),
        base_model_path=str(tmp_path),
    )
    tasks_cache["yue2_task"] = YuE2Task(yue)
    tasks_cache["sheetsage2_task"] = SheetSage2Task(sheet)

    app = FastAPI()
    app.post("/runner/upload")(upload_runner_file)
    app.post("/runner/submit")(submit_async)
    app.get("/runner/result")(result_async)
    app.get("/runner/result_source")(result_source_async)
    return TestClient(app), {"Authorization": f"Bearer {token}"}, bootstrap


def generate_request(lyrics="hello"):
    return {
        "parameter": {
            "task_name": "yue2_task",
            "reset": False,
            "user_multi_task": False,
        },
        "payload": {
            "code_input": {"userId": "alice", "workflow_id": "wf"},
            "operation": "generate",
            "request": {"style": "pop", "lyrics": lyrics, "seed": 7},
        },
    }


def test_http_upload_submit_idempotency_and_read_only_get(tmp_path):
    client, headers, bootstrap = make_client(tmp_path)
    upload = client.post(
        "/runner/upload",
        headers=headers,
        data={"user_id": "alice"},
        files={"file": ("song.wav", b"wave", "audio/wav")},
    )
    assert upload.status_code == 200
    assert upload.json()["data"]["size_bytes"] == 4

    accepted = client.post(
        "/runner/submit",
        headers={**headers, "Idempotency-Key": "same-key"},
        json=generate_request(),
    )
    assert accepted.status_code == 200
    task_id = accepted.json()["data"]["task_id"]
    assert list(bootstrap.queue) == [task_id]
    duplicate = client.post(
        "/runner/submit",
        headers={**headers, "Idempotency-Key": "same-key"},
        json=generate_request(),
    )
    assert duplicate.json()["data"]["task_id"] == task_id
    assert list(bootstrap.queue) == [task_id]
    conflict = client.post(
        "/runner/submit",
        headers={**headers, "Idempotency-Key": "same-key"},
        json=generate_request("changed"),
    )
    assert conflict.status_code == 409

    task_file = bootstrap.music_store.task_dir(task_id) / "task.json"
    before = task_file.read_bytes()
    status = client.get("/runner/result", headers=headers, params={"task_id": task_id})
    assert status.status_code == 200 and status.json()["data"]["finished"] is False
    assert task_file.read_bytes() == before


def test_music_deployment_rejects_wrong_actor_and_non_music_task(tmp_path):
    client, headers, _ = make_client(tmp_path)
    wrong = generate_request()
    wrong["payload"]["code_input"]["userId"] = "bob"
    response = client.post(
        "/runner/submit",
        headers={**headers, "Idempotency-Key": "one"},
        json=wrong,
    )
    assert response.status_code == 403
    non_music = generate_request()
    non_music["parameter"]["task_name"] = "research_agent_task"
    response = client.post(
        "/runner/submit",
        headers={**headers, "Idempotency-Key": "two"},
        json=non_music,
    )
    assert response.status_code == 403

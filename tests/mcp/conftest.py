import contextlib
import hashlib
import json
from collections import deque

import httpx
import pytest
from fastapi import FastAPI, Request
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from sandbox.processors.sheetsage2_processor import SheetSage2Processor
from sandbox.processors.yue2_processor import YuE2Processor
from sandbox.server.bootstrap.bootstrap_register import bootstrap_cache
from sandbox.server.mcp_api import create_runner_mcp
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


def _build_runner_mcp(tmp_path, *, auth_required: bool):
    token = "runner-secret"
    keys = tmp_path / "keys.json"
    keys.write_text(
        json.dumps({hashlib.sha256(token.encode()).hexdigest(): "alice"}),
        encoding="utf-8",
    )
    keys.chmod(0o600)
    bootstrap = RunnerBootstrapBaseWeb(
        "127.0.0.1",
        0,
        max_ongoing_tasks=1,
        music={
            "data_root": str(tmp_path / "data"),
            "api_keys_file": str(keys) if auth_required else None,
            "auth_required": auth_required,
            "principal": "alice",
        },
        upload={"data_root": str(tmp_path / "data"), "max_input_bytes": 64},
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

    config = {
        "enabled": True,
        "path": "/mcp",
        "public_base_url": "http://testserver",
        "allowed_hosts": ["testserver", "127.0.0.1:11000"],
        "allowed_origins": ["http://testserver", "http://127.0.0.1:11000"],
        "tools": [
            "runner_upload",
            "runner_submit",
            "runner_result",
            "runner_result_source",
        ],
        "upload_capability_path": "/api/uploads/{token}",
        "upload_ttl_seconds": 300,
        "max_request_bytes": 1024,
        "inline_max_bytes": 16,
    }
    integration = create_runner_mcp(
        config=config,
        auth=bootstrap.music_auth,
        max_input_bytes=bootstrap.asset_store.max_input_bytes,
    )
    app = FastAPI()
    app.post("/runner/upload")(upload_runner_file)
    app.post("/runner/submit")(submit_async)
    app.get("/runner/result")(result_async)
    app.get("/runner/result_source")(result_source_async)

    async def receive(token: str, request: Request):
        return await integration.capabilities.receive(token=token, request=request)

    app.put("/api/uploads/{token}")(receive)
    app.mount("/mcp", integration.app)
    return {
        "app": app,
        "integration": integration,
        "bootstrap": bootstrap,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def runner_mcp(tmp_path):
    return _build_runner_mcp(tmp_path, auth_required=True)


@pytest.fixture
def runner_mcp_no_auth(tmp_path):
    return _build_runner_mcp(tmp_path, auth_required=False)


@contextlib.asynccontextmanager
async def mcp_session(fixture, *, authenticated=True):
    headers = fixture["headers"] if authenticated else {}
    transport = httpx.ASGITransport(app=fixture["app"])
    async with fixture["integration"].server.session_manager.run():
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers=headers,
        ) as client:
            async with streamable_http_client(
                "http://testserver/mcp/", http_client=client
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session, client


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


def transcribe_request(asset_id):
    return {
        "parameter": {
            "task_name": "sheetsage2_task",
            "reset": False,
            "user_multi_task": False,
        },
        "payload": {
            "code_input": {"userId": "alice", "workflow_id": "wf"},
            "operation": "transcribe",
            "audio_asset_id": asset_id,
        },
    }

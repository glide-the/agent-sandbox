from urllib.parse import urlparse

import httpx
import pytest
from fastapi import HTTPException

from sandbox.server.upload_capability import UploadCapabilityStore
from tests.mcp.conftest import generate_request, mcp_session


@pytest.mark.asyncio
async def test_m01_transport_requires_authentication(runner_mcp):
    transport = httpx.ASGITransport(app=runner_mcp["app"])
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/mcp/",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_m09_read_retry_never_requeues_task(runner_mcp):
    async with mcp_session(runner_mcp) as (session, _):
        accepted = await session.call_tool(
            "runner_submit", {**generate_request(), "idempotency_key": "read-only"}
        )
        task_id = accepted.structuredContent["data"]["task_id"]
        queued = list(runner_mcp["bootstrap"].queue)
        await session.call_tool("runner_result", {"task_id": task_id})
        await session.call_tool("runner_result", {"task_id": task_id})
    assert list(runner_mcp["bootstrap"].queue) == queued


def test_m11_rejects_untrusted_public_origin_and_tool_set():
    with pytest.raises(ValueError):
        UploadCapabilityStore(public_base_url="file:///tmp/runner")


def test_m04_expired_capability_cannot_be_reused():
    now = [100.0]
    store = UploadCapabilityStore(
        public_base_url="https://runner.example",
        ttl_seconds=1,
        clock=lambda: now[0],
    )
    issued = store.issue(principal="alice", file_path="/tmp/a.wav", client_os="linux")
    token = urlparse(issued["upload_url"]).path.rsplit("/", 1)[-1]
    now[0] = 102.0
    with pytest.raises(HTTPException) as error:
        store.consume(token)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_m04_token_is_consumed_before_invalid_content_length(runner_mcp):
    async with mcp_session(runner_mcp) as (session, client):
        issued = await session.call_tool(
            "runner_upload", {"file_path": "/tmp/a.wav", "client_os": "linux"}
        )
        path = urlparse(issued.structuredContent["data"]["upload_url"]).path
        bad = await client.put(path, content=b"x", headers={"Content-Length": "bad"})
        replay = await client.put(path, content=b"x")
    assert bad.status_code == 400
    assert replay.status_code == 404

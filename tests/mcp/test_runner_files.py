import base64
import hashlib
from urllib.parse import urlparse

import pytest

from tests.mcp.conftest import generate_request, mcp_session, transcribe_request


async def _issue_and_put(session, client, payload=b"wave", path="/tmp/song.wav"):
    issued = await session.call_tool(
        "runner_upload", {"file_path": path, "client_os": "linux"}
    )
    url = issued.structuredContent["data"]["upload_url"]
    uploaded = await client.put(urlparse(url).path, content=payload)
    return issued, uploaded


@pytest.mark.asyncio
async def test_m03_mcp_upload_is_consumable_by_http_submit(runner_mcp):
    async with mcp_session(runner_mcp) as (session, client):
        _, uploaded = await _issue_and_put(session, client)
        asset_id = uploaded.json()["data"]["asset_id"]
        submitted = await client.post(
            "/runner/submit",
            headers={**runner_mcp["headers"], "Idempotency-Key": "cross-entry"},
            json=transcribe_request(asset_id),
        )
        direct = await client.post(
            "/runner/upload",
            data={"user_id": "alice"},
            files={"file": ("direct.wav", b"direct", "audio/wav")},
        )
        direct_asset = direct.json()["data"]["asset_id"]
        via_mcp = await session.call_tool(
            "runner_submit",
            {
                **transcribe_request(direct_asset),
                "idempotency_key": "http-upload-mcp-submit",
            },
        )
    assert submitted.status_code == 200
    assert not via_mcp.isError


@pytest.mark.asyncio
async def test_m04_capability_is_single_use_and_oversize_leaves_no_asset(runner_mcp):
    async with mcp_session(runner_mcp) as (session, client):
        issued, first = await _issue_and_put(session, client)
        path = urlparse(issued.structuredContent["data"]["upload_url"]).path
        second = await client.put(path, content=b"again")
        assert first.status_code == 200
        assert second.status_code == 404

        issued = await session.call_tool(
            "runner_upload", {"file_path": "/tmp/large.wav", "client_os": "linux"}
        )
        path = urlparse(issued.structuredContent["data"]["upload_url"]).path
        too_large = await client.put(path, content=b"x" * 65)
        replay = await client.put(path, content=b"ok")
    assert too_large.status_code == 413
    assert replay.status_code == 404


@pytest.mark.asyncio
async def test_m05_path_is_metadata_only_and_traversal_is_rejected(runner_mcp):
    async with mcp_session(runner_mcp) as (session, _):
        missing = await session.call_tool(
            "runner_upload",
            {"file_path": "/does/not/exist/score.abc", "client_os": "linux"},
        )
        traversed = await session.call_tool(
            "runner_upload",
            {"file_path": "/tmp/../secret.abc", "client_os": "linux"},
        )
    assert not missing.isError
    assert missing.structuredContent["data"]["filename"] == "score.abc"
    assert traversed.isError


def _publish_artifact(runner_mcp, task_id, content):
    bootstrap = runner_mcp["bootstrap"]
    task_dir = bootstrap.music_store.task_dir(task_id)
    path = task_dir / "result.abc"
    path.write_bytes(content)
    state = bootstrap.music_store.recover_state(task_id)
    state.update(
        {
            "info": "end",
            "finished": True,
            "result": {
                "delivery_status": "ready",
                "artifacts": [
                    {
                        "result_source_name": "score",
                        "filename": "result.abc",
                        "relative_path": "result.abc",
                        "media_type": "text/vnd.abc",
                        "size_bytes": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                ],
            },
        }
    )
    bootstrap.music_store.update_state(task_id, state)


@pytest.mark.asyncio
async def test_m07_inline_is_lossless_and_m08_large_file_links(runner_mcp):
    async with mcp_session(runner_mcp) as (session, client):
        accepted = await session.call_tool(
            "runner_submit", {**generate_request(), "idempotency_key": "artifact"}
        )
        task_id = accepted.structuredContent["data"]["task_id"]
        small = b"X:1\nK:C\nC|\n"
        _publish_artifact(runner_mcp, task_id, small)
        inline = await session.call_tool(
            "runner_result_source",
            {"task_id": task_id, "result_source_name": "score", "mode": "inline"},
        )
        assert (
            base64.b64decode(inline.structuredContent["data"]["content_base64"])
            == small
        )

        large = b"X" * 17
        _publish_artifact(runner_mcp, task_id, large)
        linked = await session.call_tool(
            "runner_result_source",
            {"task_id": task_id, "result_source_name": "score", "mode": "auto"},
        )
        downloaded = await client.get(linked.structuredContent["data"]["url"])
    assert linked.structuredContent["data"]["delivery"] == "link"
    assert linked.structuredContent["data"]["requires_auth"] is True
    assert any(block.type == "resource_link" for block in linked.content)
    assert downloaded.content == large

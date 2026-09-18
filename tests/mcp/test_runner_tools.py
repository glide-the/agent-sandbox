import pytest

from tests.mcp.conftest import generate_request, mcp_session


@pytest.mark.asyncio
async def test_m01_lists_only_four_runner_tools(runner_mcp):
    async with mcp_session(runner_mcp) as (session, _):
        result = await session.list_tools()
    assert {tool.name for tool in result.tools} == {
        "runner_upload",
        "runner_submit",
        "runner_result",
        "runner_result_source",
    }


@pytest.mark.asyncio
async def test_m02_http_and_mcp_share_idempotent_task(runner_mcp):
    request = generate_request()
    async with mcp_session(runner_mcp) as (session, client):
        http = await client.post(
            "/runner/submit",
            headers={**runner_mcp["headers"], "Idempotency-Key": "shared"},
            json=request,
        )
        mcp = await session.call_tool(
            "runner_submit", {**request, "idempotency_key": "shared"}
        )
    assert not mcp.isError
    assert mcp.structuredContent["data"]["task_id"] == http.json()["data"]["task_id"]
    assert len(runner_mcp["bootstrap"].queue) == 1


@pytest.mark.asyncio
async def test_m06_and_m10_authorization_and_task_error_semantics(runner_mcp):
    async with mcp_session(runner_mcp) as (session, _):
        bad = generate_request()
        bad["payload"]["code_input"]["userId"] = "bob"
        denied = await session.call_tool("runner_submit", bad)
        assert denied.isError
        assert denied.structuredContent["code"] == 403

        accepted = await session.call_tool(
            "runner_submit", {**generate_request(), "idempotency_key": "failed-task"}
        )
        task_id = accepted.structuredContent["data"]["task_id"]
        state = runner_mcp["bootstrap"].music_store.recover_state(task_id)
        state.update({"info": "error", "finished": True})
        runner_mcp["bootstrap"].music_store.update_state(task_id, state)
        queried = await session.call_tool("runner_result", {"task_id": task_id})
    assert not queried.isError
    assert queried.structuredContent["data"]["info"] == "error"

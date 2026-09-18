"""Protocol-neutral Runner operations shared by HTTP and MCP adapters."""

from __future__ import annotations

from fastapi import UploadFile

from sandbox.server.bootstrap.bootstrap_register import get_bootstrap
from sandbox.server.model.flow_data import PayLoad
from sandbox.server.model.result import TaskRunnerResponse
from sandbox.server.servlet.runner import (
    get_task_result,
    open_task_resource,
    submit_for_principal,
)


async def upload_input(*, principal: str, upload: UploadFile) -> TaskRunnerResponse:
    bootstrap = get_bootstrap("runner_bootstrap_web")
    if bootstrap.asset_store is None:
        raise RuntimeError("runner uploads are not configured")
    metadata = await bootstrap.asset_store.register_uploaded_asset(
        owner_id=principal,
        upload=upload,
    )
    return TaskRunnerResponse(
        code=200,
        msg="输入准备完成",
        data={
            "asset_id": metadata["asset_id"],
            "size_bytes": metadata["size_bytes"],
            "sha256": metadata["sha256"],
        },
    )


async def submit_task(
    *, principal: str, parameter: dict, payload: dict, idempotency_key: str | None
):
    request = PayLoad.model_validate({"parameter": parameter, "payload": payload})
    return await submit_for_principal(
        payload=request,
        idempotency_key=idempotency_key,
        principal=principal,
    )


def read_task(*, principal: str, task_id: str):
    return get_task_result(task_id=task_id, principal=principal)


def read_task_resource(*, principal: str, task_id: str, result_source_name: str):
    return open_task_resource(
        task_id=task_id,
        result_source_name=result_source_name,
        principal=principal,
    )

"""Shared lifecycle helpers for the two independently bound music tasks."""

from __future__ import annotations

from sandbox.server.bootstrap.bootstrap_register import get_bootstrap
from sandbox.server.model.music import ResourceRef


def _music_services():
    bootstrap = get_bootstrap("runner_bootstrap_web")
    if not bootstrap.music_store or not bootstrap.asset_store:
        raise RuntimeError("music services are not configured")
    return bootstrap.music_store, bootstrap.asset_store


def resolve_resource(reference: ResourceRef, owner_id: str) -> str:
    task_store, asset_store = _music_services()
    if reference.asset_id:
        return str(
            asset_store.resolve_uploaded_asset(
                owner_id=owner_id, asset_id=reference.asset_id
            )
        )
    record = task_store.read(reference.task_id)
    if record["owner_id"] != owner_id:
        raise PermissionError("task output belongs to another principal")
    state = task_store.recover_state(reference.task_id)
    result = state.get("result") or {}
    artifact = next(
        (
            item
            for item in result.get("artifacts", [])
            if item.get("result_source_name") == reference.result_source_name
        ),
        None,
    )
    if artifact is None:
        raise KeyError(reference.result_source_name)
    task_dir = task_store.task_dir(reference.task_id).resolve(strict=True)
    candidate = task_dir / artifact["relative_path"]
    if candidate.is_symlink():
        raise PermissionError("task output escaped its task directory")
    path = candidate.resolve(strict=True)
    if task_dir not in path.parents:
        raise PermissionError("task output escaped its task directory")
    return str(path)


def resolve_decode_source(source_task_id: str, owner_id: str) -> str:
    task_store, _ = _music_services()
    record = task_store.read(source_task_id)
    if record["owner_id"] != owner_id:
        raise PermissionError("source task belongs to another principal")
    state = task_store.recover_state(source_task_id)
    result = state.get("result") or {}
    if result.get("delivery_status") != "ready":
        raise ValueError("source task does not have a complete published result")
    native = task_store.task_dir(source_task_id) / "artifacts" / "native"
    return str(native.resolve(strict=True))


async def save_music_result(task, runner, result: dict) -> None:
    await task.report_progress(
        task_id=runner.task_id,
        runner_stat="save_music_result",
        state="save_write",
        finished=False,
        result=result,
    )
    if result.get("delivery_status") == "failed" or result.get("outcome") in {
        "failed",
        "partial",
    }:
        raise RuntimeError("music task completed with a non-success terminal outcome")

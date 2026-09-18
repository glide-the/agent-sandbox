import copy
import hashlib
import logging
import mimetypes
import os
import time
from pathlib import Path

from fastapi import Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import ValidationError

from sandbox.common.registry import registry
from sandbox.server.bootstrap.bootstrap_register import get_bootstrap
from sandbox.server.model.flow_data import PayLoad
from sandbox.server.model.music import (
    MusicListenSubmission,
    MusicScoreSubmission,
    ResourceRef,
    SheetSage2Submission,
    YuE2Submission,
    parse_music_submission,
)
from sandbox.server.model.result import (
    BaseResponse,
    RunnerState,
    TaskInfoResponse,
    TaskRunnerResponse,
    TaskVoiceFlowInfo,
)
from sandbox.server.music_auth import authorize_music_resource
from sandbox.server.music_task_store import IdempotencyConflict, canonical_digest
from sandbox.tasks import get_task
from sandbox.tasks.exceptions import TaskRejectedError

logger = logging.getLogger("server_runner")
MUSIC_TASKS = {
    "yue2_task",
    "sheetsage2_task",
    "music_score_task",
    "music_listen_task",
}


def constant_compare(a, b):
    if isinstance(a, str):
        a = a.encode("utf-8")
    if isinstance(b, str):
        b = b.encode("utf-8")
    if not isinstance(a, bytes) or not isinstance(b, bytes) or len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= x ^ y
    return result == 0


def _music_record(bootstrap, task_id: str) -> dict | None:
    if bootstrap.music_store is None:
        return None
    try:
        return bootstrap.music_store.read(task_id)
    except KeyError:
        return None


def _execution_profile(task_name: str) -> str:
    task = get_task(task_name)
    processor = getattr(task, "processor", None)
    fields = (
        "environment",
        "cwd",
        "model_path",
        "vae_path",
        "base_model_path",
        "device",
        "dtype",
        "offline",
    )
    return canonical_digest(
        {
            "task_name": task_name,
            "task_class": (
                f"{task.__class__.__module__}.{task.__class__.__qualname__}"
            ),
            "processor_class": (
                f"{processor.__class__.__module__}.{processor.__class__.__qualname__}"
                if processor is not None
                else None
            ),
            "binding": {
                field: getattr(processor, field)
                for field in fields
                if processor is not None and hasattr(processor, field)
            },
        }
    )


def _iter_resource_refs(submission):
    if isinstance(submission, SheetSage2Submission):
        yield ResourceRef(asset_id=submission.audio_asset_id)
        return
    if isinstance(submission, MusicListenSubmission):
        return
    if isinstance(submission, MusicScoreSubmission):
        yield submission.check.source
        if submission.check.after:
            yield submission.check.after
        return
    if submission.abc_source:
        yield submission.abc_source
    if submission.check:
        yield submission.check.source
        if submission.check.after:
            yield submission.check.after


def _validate_resource_ref(bootstrap, owner_id: str, reference: ResourceRef) -> None:
    if reference.asset_id:
        bootstrap.asset_store.resolve_uploaded_asset(
            owner_id=owner_id, asset_id=reference.asset_id
        )
        return
    record = bootstrap.music_store.read(reference.task_id)
    authorize_music_resource(record["owner_id"], owner_id)
    state = bootstrap.music_store.recover_state(reference.task_id)
    result = state.get("result") or {}
    artifact = next(
        (
            item
            for item in result.get("artifacts", [])
            if item.get("result_source_name") == reference.result_source_name
        ),
        None,
    )
    if result.get("delivery_status") != "ready" or artifact is None:
        raise KeyError(reference.result_source_name)


def _validate_music_resources(bootstrap, owner_id: str, submission) -> None:
    for reference in _iter_resource_refs(submission):
        _validate_resource_ref(bootstrap, owner_id, reference)
    if isinstance(submission, YuE2Submission) and submission.source_task_id:
        record = bootstrap.music_store.read(submission.source_task_id)
        authorize_music_resource(record["owner_id"], owner_id)
        source_state = bootstrap.music_store.recover_state(submission.source_task_id)
        if (source_state.get("result") or {}).get("delivery_status") != "ready":
            raise ValueError("decode source task is not ready")
    if isinstance(submission, MusicListenSubmission):
        for task_id in submission.source_task_ids:
            record = bootstrap.music_store.read(task_id)
            authorize_music_resource(record["owner_id"], owner_id)
            source_state = bootstrap.music_store.recover_state(task_id)
            if (source_state.get("result") or {}).get("delivery_status") != "ready":
                raise ValueError(f"listening source task is not ready: {task_id}")


def _public_music_state(state: dict) -> dict:
    projected = copy.deepcopy(state)
    result = projected.get("result")
    if not isinstance(result, dict):
        return projected
    source_names = {
        item.get("result_source_name")
        for item in result.get("artifacts", [])
        if isinstance(item, dict)
    }
    for source_name in source_names:
        if source_name:
            result.pop(source_name, None)
    result["artifacts"] = [
        {
            key: item[key]
            for key in (
                "result_source_name",
                "filename",
                "media_type",
                "size_bytes",
                "sha256",
            )
            if key in item
        }
        for item in result.get("artifacts", [])
        if isinstance(item, dict)
    ]
    return projected


async def submit_async(
    request: Request,
    payload: PayLoad,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Add a task to the existing queue; music tasks get durable identity first."""
    return await submit_for_principal(
        payload=payload,
        idempotency_key=idempotency_key,
        request=request,
    )


async def submit_for_principal(
    *,
    payload: PayLoad,
    idempotency_key: str | None = None,
    principal: str | None = None,
    request: Request | None = None,
):
    """Protocol-neutral submit implementation shared by HTTP and MCP."""
    bootstrap = get_bootstrap("runner_bootstrap_web")
    task_name = payload.parameter.task_name
    if bootstrap.music_auth is not None and task_name not in MUSIC_TASKS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="this deployment only accepts approved music task types",
        )
    task = registry.get_task_class(task_name)
    now = time.time()
    payload.created_at = now
    payload.requested_at = now

    if task_name in MUSIC_TASKS:
        if payload.parameter.reset:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="music tasks require parameter.reset=false",
            )
        if (
            not bootstrap.music_auth
            or not bootstrap.music_store
            or not bootstrap.asset_store
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="music task services are not configured",
            )
        if principal is None:
            if request is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="missing authenticated principal",
                )
            principal = bootstrap.music_auth.authenticate_request(request)
        public_payload = copy.deepcopy(payload.payload)
        if "_service" in public_payload:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="_service is reserved for the server",
            )
        try:
            submission = parse_music_submission(task_name, public_payload)
            authorize_music_resource(submission.code_input.userId, principal)
            _validate_music_resources(bootstrap, principal, submission)
            record, created = bootstrap.music_store.create_or_get(
                owner_id=principal,
                idempotency_key=idempotency_key,
                task_name=task_name,
                public_payload=public_payload,
                execution_profile_digest=_execution_profile(task_name),
            )
        except IdempotencyConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
        except (ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"referenced resource does not exist: {exc}",
            )
        except (PermissionError, OSError) as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

        task_id = record["task_id"]
        if not created:
            return TaskRunnerResponse(
                code=200,
                msg="提交任务成功",
                data=_public_music_state(bootstrap.music_store.recover_state(task_id)),
            )
        public_payload["_service"] = {
            "task_id": task_id,
            "owner_id": principal,
            "request_digest": record["request_digest"],
            "execution_profile_digest": record["execution_profile_digest"],
        }
        payload.payload = public_payload
        runner = task.prepare(payload=payload)
        if runner.task_id != task_id:
            raise RuntimeError("music task prepare changed its durable task identity")
        task_state = record["state"]
        bootstrap.task_data[task_id] = payload
        bootstrap.task_states[task_id] = task_state
        bootstrap.queue.append(task_id)
        bootstrap.update_user_task_index(principal, task_id, finished=False)
        logger.info("New music submit task %s", task_id)
        return TaskRunnerResponse(code=200, msg="提交任务成功", data=task_state)

    try:
        runner = task.prepare(payload=payload)
    except TaskRejectedError as exc:
        task_state = (
            bootstrap.task_states[exc.running_task_ids.pop()]
            if exc.running_task_ids
            else {}
        )
        return TaskRunnerResponse(code=409, msg=str(exc), data=task_state)
    task_id = runner.task_id
    if (
        task_id not in bootstrap.task_data
        or task_id not in bootstrap.task_states
        or payload.parameter.reset
    ):
        task_state = {"task_id": task_id, "info": "pending", "finished": False}
        logger.info("New `submit` task %s", task_id)
        bootstrap.task_data[task_id] = payload
        bootstrap.queue.append(task_id)
        bootstrap.task_states[task_id] = task_state
        user_id = bootstrap.extract_user_id(payload)
        if user_id:
            bootstrap.update_user_task_index(user_id, task_id, finished=False)
    else:
        task_state = bootstrap.task_states[task_id]
    return TaskRunnerResponse(code=200, msg="提交任务成功", data=task_state)


async def get_task_async(nonce: str = Query(..., examples=["samples"])):
    bootstrap = get_bootstrap("runner_bootstrap_web")
    if constant_compare(nonce, bootstrap.nonce):
        if len(bootstrap.ongoing_tasks) < bootstrap.max_ongoing_tasks:
            if bootstrap.queue:
                task_id = bootstrap.queue.popleft()
                if task_id in bootstrap.task_data:
                    bootstrap.ongoing_tasks.append(task_id)
                    return TaskInfoResponse(
                        code=200,
                        msg="成功",
                        data=TaskVoiceFlowInfo(
                            task_id=task_id, data=bootstrap.task_data[task_id]
                        ),
                    )
            return BaseResponse(code=200, msg="成功")
        return BaseResponse(code=200, msg="max_ongoing_tasks")
    return BaseResponse(code=401, msg="无法获取任务")


async def post_task_update_async(runner_state: RunnerState):
    bootstrap = get_bootstrap("runner_bootstrap_web")
    if constant_compare(runner_state.nonce, bootstrap.nonce):
        task_id = runner_state.task_id
        if task_id in bootstrap.task_states and task_id in bootstrap.task_data:
            if runner_state.finished:
                bootstrap.task_data[task_id].finished_at = time.time()
                try:
                    bootstrap.ongoing_tasks.remove(task_id)
                except ValueError:
                    pass
            update = {
                "task_id": task_id,
                "info": runner_state.state,
                "finished": runner_state.finished,
            }
            if runner_state.result:
                update["result"] = runner_state.result
            elif "result" in bootstrap.task_states[task_id]:
                update["result"] = bootstrap.task_states[task_id]["result"]
            bootstrap.task_states[task_id].update(update)
            if _music_record(bootstrap, task_id) is not None:
                bootstrap.music_store.update_state(
                    task_id, bootstrap.task_states[task_id]
                )
            user_id = bootstrap.extract_user_id(bootstrap.task_data[task_id])
            if user_id:
                bootstrap.update_user_task_index(
                    user_id, task_id, finished=runner_state.finished
                )
            logger.info("Task state %s to %s", task_id, bootstrap.task_states[task_id])
    return BaseResponse(code=200, msg="成功")


async def result_source_async(
    request: Request,
    task_id: str = Query(..., examples=["task_id"]),
    result_source_name: str = Query(..., examples=["result_path"]),
):
    principal = None
    bootstrap = get_bootstrap("runner_bootstrap_web")
    if _music_record(bootstrap, task_id) is not None:
        principal = bootstrap.music_auth.authenticate_request(request)
    resource = open_task_resource(
        task_id=task_id,
        result_source_name=result_source_name,
        principal=principal,
    )
    if isinstance(resource, BaseResponse):
        return resource
    return FileResponse(
        path=resource["path"],
        filename=resource["filename"],
        media_type=resource.get("media_type"),
    )


def open_task_resource(
    *, task_id: str, result_source_name: str, principal: str | None = None
):
    """Authorize and resolve a result without coupling it to an HTTP response."""
    bootstrap = get_bootstrap("runner_bootstrap_web")
    record = _music_record(bootstrap, task_id)
    if record is not None:
        if principal is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing authenticated principal",
            )
        authorize_music_resource(record["owner_id"], principal)
        state = bootstrap.music_store.recover_state(task_id)
        result = state.get("result") or {}
        artifact = next(
            (
                item
                for item in result.get("artifacts", [])
                if item.get("result_source_name") == result_source_name
            ),
            None,
        )
        if result.get("delivery_status") != "ready" or artifact is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="result source is not ready or not listed",
            )
        task_dir = bootstrap.music_store.task_dir(task_id).resolve(strict=True)
        candidate = task_dir / artifact["relative_path"]
        if candidate.is_symlink():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="result source path is invalid",
            )
        filepath = candidate.resolve(strict=True)
        if task_dir not in filepath.parents:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="result source path is invalid",
            )
        if filepath.stat().st_size != artifact["size_bytes"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="result source no longer matches its manifest",
            )
        digest = hashlib.sha256()
        with filepath.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != artifact["sha256"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="result source no longer matches its manifest",
            )
        return {
            "path": filepath,
            "filename": artifact["filename"],
            "media_type": artifact.get("media_type")
            or mimetypes.guess_type(artifact["filename"])[0],
            "size_bytes": artifact["size_bytes"],
            "sha256": artifact["sha256"],
        }

    if task_id not in bootstrap.task_states or task_id not in bootstrap.task_data:
        return BaseResponse(code=500, msg=f"{task_id}: 任务不存在")
    try:
        result = bootstrap.task_states[task_id].get("result") or {}
        filepath = result.get(result_source_name)
        if filepath and os.path.exists(filepath):
            path = Path(filepath)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            return {
                "path": path,
                "filename": path.name,
                "media_type": mimetypes.guess_type(path.name)[0],
                "size_bytes": path.stat().st_size,
                "sha256": digest,
            }
        return BaseResponse(code=500, msg=f"{filepath} 读取文件失败")
    except Exception as exc:
        logger.error("%s: %s", exc.__class__.__name__, exc, exc_info=exc)
        return BaseResponse(code=500, msg=f"{task_id}: 任务结果获取失败")


async def result_async(
    request: Request, task_id: str = Query(..., examples=["task_id"])
):
    bootstrap = get_bootstrap("runner_bootstrap_web")
    principal = None
    if _music_record(bootstrap, task_id) is not None:
        principal = bootstrap.music_auth.authenticate_request(request)
    return get_task_result(task_id=task_id, principal=principal)


def get_task_result(*, task_id: str, principal: str | None = None):
    """Protocol-neutral task lookup shared by HTTP and MCP."""
    bootstrap = get_bootstrap("runner_bootstrap_web")
    record = _music_record(bootstrap, task_id)
    if record is not None:
        if principal is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing authenticated principal",
            )
        authorize_music_resource(record["owner_id"], principal)
        return TaskRunnerResponse(
            code=200,
            msg="获取任务成功",
            data=_public_music_state(bootstrap.music_store.recover_state(task_id)),
        )
    if task_id not in bootstrap.task_states or task_id not in bootstrap.task_data:
        return BaseResponse(code=500, msg=f"{task_id}: 任务不存在")
    return TaskRunnerResponse(
        code=200, msg="获取任务成功", data=bootstrap.task_states[task_id]
    )


async def get_bootstrap_info(nonce: str = Query(..., examples=["samples"])):
    bootstrap = get_bootstrap("runner_bootstrap_web")
    if constant_compare(nonce, bootstrap.nonce):
        return TaskRunnerResponse(
            code=200,
            msg="获取任务成功",
            data={
                "_TASK_DATA": bootstrap.task_data,
                "_TASK_STATES": bootstrap.task_states,
                "_ONGOING_TASKS": bootstrap.ongoing_tasks,
                "_MAX_ONGOING_TASKS": bootstrap.max_ongoing_tasks,
            },
        )
    return BaseResponse(code=401, msg="无法获取任务")

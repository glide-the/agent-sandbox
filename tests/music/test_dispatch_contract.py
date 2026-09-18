import asyncio

import pytest
from pydantic import ValidationError

from sandbox.processors.music_utility_processor import (
    MusicListenProcessor,
    MusicScoreProcessor,
)
from sandbox.processors.sheetsage2_processor import SheetSage2Processor
from sandbox.processors.yue2_processor import YuE2Processor
from sandbox.server.model.flow_data import PayLoad
from sandbox.tasks.music_utility_task import MusicListenTask, MusicScoreTask
from sandbox.tasks.sheetsage2_task import SheetSage2Task
from sandbox.tasks.yue2_task import YuE2Task

SERVICE = {
    "task_id": "music_0123456789abcdef",
    "owner_id": "alice",
    "request_digest": "r",
    "execution_profile_digest": "p",
}


def payload(task_name, body):
    return PayLoad.model_validate(
        {
            "parameter": {"task_name": task_name, "reset": False},
            "payload": {**body, "_service": SERVICE},
        }
    )


def test_double_prepare_preserves_durable_identity():
    value = payload(
        "yue2_task",
        {
            "code_input": {"userId": "alice", "workflow_id": "wf"},
            "operation": "generate",
            "request": {"style": "pop", "lyrics": "hello"},
        },
    )
    assert YuE2Task.prepare(value).task_id == SERVICE["task_id"]
    assert (
        YuE2Task.prepare(PayLoad.model_validate(value.model_dump())).task_id
        == SERVICE["task_id"]
    )


def test_tasks_reject_cross_model_operations():
    value = payload(
        "yue2_task",
        {
            "code_input": {"userId": "alice", "workflow_id": "wf"},
            "operation": "transcribe",
            "audio_asset_id": "asset_x",
        },
    )
    with pytest.raises(ValidationError):
        YuE2Task.prepare(value)
    value = payload(
        "sheetsage2_task",
        {
            "code_input": {"userId": "alice", "workflow_id": "wf"},
            "operation": "generate",
            "request": {"style": "pop", "lyrics": "hello"},
        },
    )
    with pytest.raises(ValidationError):
        SheetSage2Task.prepare(value)


def test_model_tasks_have_distinct_processor_types(tmp_path):
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
    assert isinstance(YuE2Task(yue).processor, YuE2Processor)
    assert isinstance(SheetSage2Task(sheet).processor, SheetSage2Processor)


def test_official_utility_scripts_have_distinct_task_processor_types(tmp_path):
    common = {
        "cwd": str(tmp_path),
        "environment": str(tmp_path),
        "task_root": str(tmp_path),
    }
    score = MusicScoreProcessor(**common)
    listen = MusicListenProcessor(**common)
    assert isinstance(MusicScoreTask(score).processor, MusicScoreProcessor)
    assert isinstance(MusicListenTask(listen).processor, MusicListenProcessor)


def test_utility_tasks_reject_each_others_operations():
    listen = payload(
        "music_listen_task",
        {
            "code_input": {"userId": "alice", "workflow_id": "wf"},
            "operation": "score_check",
            "check": {
                "action": "inspect",
                "source": {"asset_id": "asset_score"},
            },
        },
    )
    with pytest.raises(ValidationError):
        MusicListenTask.prepare(listen)
    score = payload(
        "music_score_task",
        {
            "code_input": {"userId": "alice", "workflow_id": "wf"},
            "operation": "listen",
            "source_task_ids": ["music_source"],
        },
    )
    with pytest.raises(ValidationError):
        MusicScoreTask.prepare(score)


def test_worker_dispatch_uses_only_trusted_resource_handoff():
    seen = {}

    class StubProcessor:
        async def __call__(self, submission, task_id, resources):
            seen.update(resources)
            return {"outcome": "complete", "delivery_status": "ready"}

    task = MusicScoreTask(StubProcessor())

    async def report_progress(**kwargs):
        return None

    task.report_progress = report_progress
    value = payload(
        "music_score_task",
        {
            "code_input": {"userId": "alice", "workflow_id": "wf"},
            "operation": "score_check",
            "check": {
                "action": "inspect",
                "source": {"asset_id": "asset_score"},
            },
        },
    )
    value.payload["_service"]["resolved_resources"] = {
        "score_source": "/trusted/assets/score.abc"
    }
    runner = MusicScoreTask.prepare(value)
    asyncio.run(task.dispatch(runner))
    assert seen == {"score_source": "/trusted/assets/score.abc"}

"""Tasks for model-free score checks and listening comparison bundles."""

from __future__ import annotations

import inspect

from sandbox.common.registry import registry
from sandbox.processors import get_processors
from sandbox.processors.music_utility_processor import (
    MusicListenProcessor,
    MusicScoreProcessor,
)
from sandbox.server.model.flow_data import PayLoad
from sandbox.server.model.music import MusicListenSubmission, MusicScoreSubmission
from sandbox.tasks.base_task import FlowData, Runner, SandboxTaskAbstract
from sandbox.tasks.music_result import (
    resolve_decode_source,
    resolve_resource,
    save_music_result,
)


class MusicScoreFlowData(FlowData):
    submission: MusicScoreSubmission

    @property
    def type(self) -> str:
        return "MusicScoreFlowData"


@registry.register_task("music_score_task")
class MusicScoreTask(SandboxTaskAbstract):
    def __init__(self, processor: MusicScoreProcessor):
        super().__init__(preprocess_dict={"MusicScore": processor})
        self.processor = processor

    @classmethod
    def from_config(cls, cfg=None):
        bindings = [
            value
            for item in cfg.get("preprocess", [])
            for value in item.values()
        ]
        if len(bindings) != 1 or bindings[0].processor_name != "MusicScore":
            raise ValueError(
                "music_score_task requires one MusicScore processor binding"
            )
        processor = get_processors(bindings[0].processor)
        if not isinstance(processor, MusicScoreProcessor):
            raise TypeError("music_score_task cannot bind a different processor")
        return cls(processor)

    @classmethod
    def prepare(cls, payload: PayLoad) -> Runner:
        submission = MusicScoreSubmission.model_validate(payload.payload)
        if submission.service is None:
            raise ValueError("trusted service metadata is missing")
        return Runner(
            task_id=submission.service.task_id,
            flow_data=MusicScoreFlowData(submission=submission),
        )

    async def dispatch(self, runner: Runner) -> None:
        submission = runner.flow_data.submission
        await self.report_progress(
            task_id=runner.task_id,
            runner_stat="music_score_task",
            state="dispatch_music_score_task",
            result={"stage": "preparing"},
        )
        owner = submission.service.owner_id
        resources = {"score_source": resolve_resource(submission.check.source, owner)}
        if submission.check.after:
            resources["score_after"] = resolve_resource(submission.check.after, owner)
        result = self.processor(submission, runner.task_id, resources)
        if inspect.isawaitable(result):
            result = await result
        await save_music_result(self, runner, result)


class MusicListenFlowData(FlowData):
    submission: MusicListenSubmission

    @property
    def type(self) -> str:
        return "MusicListenFlowData"


@registry.register_task("music_listen_task")
class MusicListenTask(SandboxTaskAbstract):
    def __init__(self, processor: MusicListenProcessor):
        super().__init__(preprocess_dict={"MusicListen": processor})
        self.processor = processor

    @classmethod
    def from_config(cls, cfg=None):
        bindings = [
            value
            for item in cfg.get("preprocess", [])
            for value in item.values()
        ]
        if len(bindings) != 1 or bindings[0].processor_name != "MusicListen":
            raise ValueError(
                "music_listen_task requires one MusicListen processor binding"
            )
        processor = get_processors(bindings[0].processor)
        if not isinstance(processor, MusicListenProcessor):
            raise TypeError("music_listen_task cannot bind a different processor")
        return cls(processor)

    @classmethod
    def prepare(cls, payload: PayLoad) -> Runner:
        submission = MusicListenSubmission.model_validate(payload.payload)
        if submission.service is None:
            raise ValueError("trusted service metadata is missing")
        return Runner(
            task_id=submission.service.task_id,
            flow_data=MusicListenFlowData(submission=submission),
        )

    async def dispatch(self, runner: Runner) -> None:
        submission = runner.flow_data.submission
        await self.report_progress(
            task_id=runner.task_id,
            runner_stat="music_listen_task",
            state="dispatch_music_listen_task",
            result={"stage": "preparing"},
        )
        owner = submission.service.owner_id
        resources = {
            "source_tasks": [
                resolve_decode_source(task_id, owner)
                for task_id in submission.source_task_ids
            ]
        }
        result = self.processor(submission, runner.task_id, resources)
        if inspect.isawaitable(result):
            result = await result
        await save_music_result(self, runner, result)

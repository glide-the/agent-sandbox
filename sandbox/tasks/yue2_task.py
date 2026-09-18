"""Task bound exclusively to the YuE2 processor and environment."""

from __future__ import annotations

import inspect

from sandbox.common.registry import registry
from sandbox.processors import get_processors
from sandbox.processors.yue2_processor import YuE2Processor
from sandbox.server.model.flow_data import PayLoad
from sandbox.server.model.music import YuE2Submission
from sandbox.tasks.base_task import FlowData, Runner, SandboxTaskAbstract
from sandbox.tasks.music_result import save_music_result


class YuE2FlowData(FlowData):
    submission: YuE2Submission

    @property
    def type(self) -> str:
        return "YuE2FlowData"


@registry.register_task("yue2_task")
class YuE2Task(SandboxTaskAbstract):
    def __init__(self, processor: YuE2Processor):
        super().__init__(preprocess_dict={"YuE2": processor})
        self.processor = processor

    @classmethod
    def from_config(cls, cfg=None):
        bindings = []
        for item in cfg.get("preprocess", []):
            bindings.extend(item.values())
        if len(bindings) != 1 or bindings[0].processor_name != "YuE2":
            raise ValueError("yue2_task requires exactly one YuE2 processor binding")
        processor = get_processors(bindings[0].processor)
        if not isinstance(processor, YuE2Processor):
            raise TypeError("yue2_task cannot bind a non-YuE2 processor")
        return cls(processor)

    @classmethod
    def prepare(cls, payload: PayLoad) -> Runner:
        submission = YuE2Submission.model_validate(payload.payload)
        if submission.service is None:
            raise ValueError("trusted service metadata is missing")
        return Runner(
            task_id=submission.service.task_id,
            flow_data=YuE2FlowData(submission=submission),
        )

    async def dispatch(self, runner: Runner) -> None:
        submission = runner.flow_data.submission
        await self.report_progress(
            task_id=runner.task_id,
            runner_stat="yue2_task",
            state="dispatch_yue2_task",
            result={"stage": "preparing"},
        )
        resources = submission.service.resolved_resources
        result = self.processor(submission, runner.task_id, resources)
        if inspect.isawaitable(result):
            result = await result
        await save_music_result(self, runner, result)

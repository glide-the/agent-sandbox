"""Task bound exclusively to the SheetSage2 processor and environment."""

from __future__ import annotations

import inspect

from sandbox.common.registry import registry
from sandbox.processors import get_processors
from sandbox.processors.sheetsage2_processor import SheetSage2Processor
from sandbox.server.bootstrap.bootstrap_register import get_bootstrap
from sandbox.server.model.flow_data import PayLoad
from sandbox.server.model.music import SheetSage2Submission
from sandbox.tasks.base_task import FlowData, Runner, SandboxTaskAbstract
from sandbox.tasks.music_result import save_music_result


class SheetSage2FlowData(FlowData):
    submission: SheetSage2Submission

    @property
    def type(self) -> str:
        return "SheetSage2FlowData"


@registry.register_task("sheetsage2_task")
class SheetSage2Task(SandboxTaskAbstract):
    def __init__(self, processor: SheetSage2Processor):
        super().__init__(preprocess_dict={"SheetSage2": processor})
        self.processor = processor

    @classmethod
    def from_config(cls, cfg=None):
        bindings = []
        for item in cfg.get("preprocess", []):
            bindings.extend(item.values())
        if len(bindings) != 1 or bindings[0].processor_name != "SheetSage2":
            raise ValueError(
                "sheetsage2_task requires exactly one SheetSage2 processor binding"
            )
        processor = get_processors(bindings[0].processor)
        if not isinstance(processor, SheetSage2Processor):
            raise TypeError("sheetsage2_task cannot bind a non-SheetSage2 processor")
        return cls(processor)

    @classmethod
    def prepare(cls, payload: PayLoad) -> Runner:
        submission = SheetSage2Submission.model_validate(payload.payload)
        if submission.service is None:
            raise ValueError("trusted service metadata is missing")
        return Runner(
            task_id=submission.service.task_id,
            flow_data=SheetSage2FlowData(submission=submission),
        )

    async def dispatch(self, runner: Runner) -> None:
        submission = runner.flow_data.submission
        await self.report_progress(
            task_id=runner.task_id,
            runner_stat="sheetsage2_task",
            state="dispatch_sheetsage2_task",
            result={"stage": "preparing"},
        )
        bootstrap = get_bootstrap("runner_bootstrap_web")
        source = bootstrap.asset_store.resolve_uploaded_asset(
            owner_id=submission.service.owner_id,
            asset_id=submission.audio_asset_id,
        )
        result = self.processor(
            submission, runner.task_id, {"audio_asset": str(source)}
        )
        if inspect.isawaitable(result):
            result = await result
        await save_music_result(self, runner, result)

import logging
from typing import Dict

from sandbox.common.registry import registry
from sandbox.processors import BaseProcessor, get_processors
from sandbox.processors.agent_sandbox import (
    AgentMem0ProcessorData,
    AgentWorkspaceL2ProcessorData,
    AgentWorkspaceL3ProcessorData,
)
from sandbox.tasks import FlowData, Runner, SandboxTaskAbstract

logger = logging.getLogger("agent_sandbox_task")


class AgentMem0FlowData(FlowData):
    """FlowData wrapper for the L1 Mem0 processor."""

    mem0_input: AgentMem0ProcessorData

    @property
    def type(self) -> str:
        return "AgentMem0FlowData"


class AgentWorkspaceL2FlowData(FlowData):
    """FlowData wrapper for the L2 workspace processor."""

    l2_input: AgentWorkspaceL2ProcessorData

    @property
    def type(self) -> str:
        return "AgentWorkspaceL2FlowData"


class AgentWorkspaceL3FlowData(FlowData):
    """FlowData wrapper for the L3 workspace processor."""

    l3_input: AgentWorkspaceL3ProcessorData

    @property
    def type(self) -> str:
        return "AgentWorkspaceL3FlowData"


@registry.register_task("agent_mem0_task")
class AgentMem0Task(SandboxTaskAbstract):
    """Task to invoke the L1 Mem0 processor and persist results."""

    def __init__(self, preprocess_dict: Dict[str, BaseProcessor]):
        super().__init__(preprocess_dict=preprocess_dict)
        self._preprocess_dict = preprocess_dict

    @classmethod
    def from_config(cls, cfg=None):
        preprocess_dict = {}
        for preprocess in cfg.get("preprocess"):
            for key, preprocess_info in preprocess.items():
                preprocess_object = get_processors(preprocess_info.processor)
                preprocess_dict[preprocess_info.processor_name] = preprocess_object
        return cls(preprocess_dict=preprocess_dict)

    async def dispatch(self, runner: Runner) -> None:
        try:
            logger.info("agent_mem0_task.dispatch")
            await self.report_progress(
                task_id=runner.task_id,
                runner_stat="agent_mem0_task",
                state="dispatch_agent_mem0_task",
            )

            data = runner.flow_data
            if "AgentMem0FlowData" in data.type:
                preprocess_object = self.preprocess_dict.get(data.mem0_input.type)
                if not preprocess_object or not preprocess_object.match(data.mem0_input):
                    raise RuntimeError("不支持的 agent_mem0 processor")

                (
                    result_path,
                    log_detail_path,
                    log_summary_path,
                    log_run_path,
                ) = preprocess_object(data.mem0_input)

                await self.report_progress(
                    task_id=runner.task_id,
                    runner_stat="agent_mem0_task",
                    state="finished",
                    finished=False,
                )
                await super().save_task_write(
                    runner=runner,
                    result_path=result_path,
                    log_detail_path=log_detail_path,
                    log_summary_path=log_summary_path,
                    log_run_path=log_run_path,
                )
        except Exception as e:  # pragma: no cover - passthrough to outer handling
            await self.report_progress(
                task_id=runner.task_id,
                runner_stat="agent_mem0_task",
                state="error",
                finished=True,
                result={"error": str(e)},
            )
            raise


@registry.register_task("agent_workspace_l2_task")
class AgentWorkspaceL2Task(SandboxTaskAbstract):
    """Task to invoke the L2 workspace processor and persist results."""

    def __init__(self, preprocess_dict: Dict[str, BaseProcessor]):
        super().__init__(preprocess_dict=preprocess_dict)
        self._preprocess_dict = preprocess_dict

    @classmethod
    def from_config(cls, cfg=None):
        preprocess_dict = {}
        for preprocess in cfg.get("preprocess"):
            for key, preprocess_info in preprocess.items():
                preprocess_object = get_processors(preprocess_info.processor)
                preprocess_dict[preprocess_info.processor_name] = preprocess_object
        return cls(preprocess_dict=preprocess_dict)

    async def dispatch(self, runner: Runner) -> None:
        try:
            logger.info("agent_workspace_l2_task.dispatch")
            await self.report_progress(
                task_id=runner.task_id,
                runner_stat="agent_workspace_l2_task",
                state="dispatch_agent_workspace_l2_task",
            )

            data = runner.flow_data
            if "AgentWorkspaceL2FlowData" in data.type:
                preprocess_object = self.preprocess_dict.get(data.l2_input.type)
                if not preprocess_object or not preprocess_object.match(data.l2_input):
                    raise RuntimeError("不支持的 agent_workspace_l2 processor")

                (
                    result_path,
                    log_detail_path,
                    log_summary_path,
                    log_run_path,
                ) = preprocess_object(data.l2_input)

                await self.report_progress(
                    task_id=runner.task_id,
                    runner_stat="agent_workspace_l2_task",
                    state="finished",
                    finished=False,
                )
                await super().save_task_write(
                    runner=runner,
                    result_path=result_path,
                    log_detail_path=log_detail_path,
                    log_summary_path=log_summary_path,
                    log_run_path=log_run_path,
                )
        except Exception as e:  # pragma: no cover - passthrough to outer handling
            await self.report_progress(
                task_id=runner.task_id,
                runner_stat="agent_workspace_l2_task",
                state="error",
                finished=True,
                result={"error": str(e)},
            )
            raise


@registry.register_task("agent_workspace_l3_task")
class AgentWorkspaceL3Task(SandboxTaskAbstract):
    """Task to invoke the L3 workspace processor and persist results."""

    def __init__(self, preprocess_dict: Dict[str, BaseProcessor]):
        super().__init__(preprocess_dict=preprocess_dict)
        self._preprocess_dict = preprocess_dict

    @classmethod
    def from_config(cls, cfg=None):
        preprocess_dict = {}
        for preprocess in cfg.get("preprocess"):
            for key, preprocess_info in preprocess.items():
                preprocess_object = get_processors(preprocess_info.processor)
                preprocess_dict[preprocess_info.processor_name] = preprocess_object
        return cls(preprocess_dict=preprocess_dict)

    async def dispatch(self, runner: Runner) -> None:
        try:
            logger.info("agent_workspace_l3_task.dispatch")
            await self.report_progress(
                task_id=runner.task_id,
                runner_stat="agent_workspace_l3_task",
                state="dispatch_agent_workspace_l3_task",
            )

            data = runner.flow_data
            if "AgentWorkspaceL3FlowData" in data.type:
                preprocess_object = self.preprocess_dict.get(data.l3_input.type)
                if not preprocess_object or not preprocess_object.match(data.l3_input):
                    raise RuntimeError("不支持的 agent_workspace_l3 processor")

                (
                    result_path,
                    log_detail_path,
                    log_summary_path,
                    log_run_path,
                ) = preprocess_object(data.l3_input)

                await self.report_progress(
                    task_id=runner.task_id,
                    runner_stat="agent_workspace_l3_task",
                    state="finished",
                    finished=False,
                )
                await super().save_task_write(
                    runner=runner,
                    result_path=result_path,
                    log_detail_path=log_detail_path,
                    log_summary_path=log_summary_path,
                    log_run_path=log_run_path,
                )
        except Exception as e:  # pragma: no cover - passthrough to outer handling
            await self.report_progress(
                task_id=runner.task_id,
                runner_stat="agent_workspace_l3_task",
                state="error",
                finished=True,
                result={"error": str(e)},
            )
            raise

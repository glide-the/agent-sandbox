import hashlib
import logging
from typing import Dict

from sandbox.common.registry import registry
from sandbox.processors import BaseProcessor, get_processors
from sandbox.processors.agent_sandbox import (
    AgentMem0ProcessorData,
    AgentWorkspaceL2ProcessorData,
    AgentWorkspaceL3ProcessorData,
)
from sandbox.server.model.flow_data import PayLoad
from sandbox.tasks import FlowData, Runner, SandboxTaskAbstract

logger = logging.getLogger("agent_sandbox_task")


def calculate_md5(input_string):
    md5_hash = hashlib.md5()
    md5_hash.update(input_string.encode('utf-8'))
    return md5_hash.hexdigest()


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

    @classmethod
    def prepare(cls, payload: PayLoad) -> Runner:
        """
        Prepare AgentMem0 task runner
        """
        params = payload.payload
        # Extract mem0 input data from payload
        mem0_input_data = params.get("mem0_input", {})

        # Create AgentMem0ProcessorData instance
        mem0_input = AgentMem0ProcessorData(**mem0_input_data)

        # Create FlowData instance
        flow_data = AgentMem0FlowData(mem0_input=mem0_input)

        # Generate unique task_id
        task_id = f'{mem0_input.user_id}_{int(payload.created_at)}_{calculate_md5(str(mem0_input))}'

        # Create and return Runner instance
        runner = Runner(
            task_id=task_id,
            flow_data=flow_data
        )

        return runner

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
                preprocess_object = self._preprocess_dict.get(data.mem0_input.type)
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

    @classmethod
    def prepare(cls, payload: PayLoad) -> Runner:
        """
        Prepare AgentWorkspaceL2 task runner
        """
        params = payload.payload
        # Extract L2 workspace input data from payload
        l2_input_data = params.get("l2_input", {})

        # Create AgentWorkspaceL2ProcessorData instance
        l2_input = AgentWorkspaceL2ProcessorData(**l2_input_data)

        # Create FlowData instance
        flow_data = AgentWorkspaceL2FlowData(l2_input=l2_input)

        # Generate unique task_id
        task_id = f'{l2_input.user_id}_{int(payload.created_at)}_{calculate_md5(str(l2_input))}'

        # Create and return Runner instance
        runner = Runner(
            task_id=task_id,
            flow_data=flow_data
        )

        return runner

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
                preprocess_object = self._preprocess_dict.get(data.l2_input.type)
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

    @classmethod
    def prepare(cls, payload: PayLoad) -> Runner:
        """
        Prepare AgentWorkspaceL3 task runner
        """
        params = payload.payload
        # Extract L3 workspace input data from payload
        l3_input_data = params.get("l3_input", {})

        # Create AgentWorkspaceL3ProcessorData instance
        l3_input = AgentWorkspaceL3ProcessorData(**l3_input_data)

        # Create FlowData instance
        flow_data = AgentWorkspaceL3FlowData(l3_input=l3_input)

        # Generate unique task_id
        task_id = f'{l3_input.user_id}_{int(payload.created_at)}_{calculate_md5(str(l3_input))}'

        # Create and return Runner instance
        runner = Runner(
            task_id=task_id,
            flow_data=flow_data
        )

        return runner

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
                preprocess_object = self._preprocess_dict.get(data.l3_input.type)
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

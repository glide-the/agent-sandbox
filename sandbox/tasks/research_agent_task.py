import hashlib
from typing import Dict

from sandbox.common.registry import registry
from sandbox.processors import BaseProcessor, ResearchAgentSandboxProcessorData, get_processors
from sandbox.server.bootstrap.bootstrap_register import get_bootstrap
from sandbox.server.model.flow_data import PayLoad
from sandbox.tasks import FlowData, Runner, SandboxTaskAbstract
from sandbox.tasks.exceptions import TaskRejectedError


def _md5(input_string: str) -> str:
    md5_hash = hashlib.md5()
    md5_hash.update(input_string.encode("utf-8"))
    return md5_hash.hexdigest()


class ResearchAgentFlowData(FlowData):
    """
    Runner.flow_data 的具体类型：
    - sandbox_input: 文件/路径相关参数（ResearchAgentSandboxProcessorData）
    - topic: 研究主题
    """

    sandbox_input: ResearchAgentSandboxProcessorData
    topic: str

    @property
    def type(self) -> str:
        """FlowData 类型标识，用于 dispatch 判断。"""
        return "ResearchAgentFlowData"


@registry.register_task("research_agent_task")
class ResearchAgentTask(SandboxTaskAbstract):
    """
    新增的 research_agent 任务，实现 prepare / dispatch，
    复用 SandboxTaskAbstract.save_task_write 做统一收尾。
    """

    def __init__(self, preprocess_dict: Dict[str, BaseProcessor]):
        super().__init__(preprocess_dict=preprocess_dict)
        self._preprocess_dict = preprocess_dict

    @classmethod
    def from_config(cls, cfg=None):
        """
        根据 YAML 中的 preprocess 配置构建 processor 字典。
        """
        preprocess_dict: Dict[str, BaseProcessor] = {}
        for preprocess in cfg.get("preprocess"):
            for _, preprocess_info in preprocess.items():
                processor = get_processors(preprocess_info.processor)
                preprocess_dict[preprocess_info.processor_name] = processor

        return cls(preprocess_dict=preprocess_dict)

    @property
    def preprocess_dict(self) -> Dict[str, BaseProcessor]:
        return self._preprocess_dict

    @classmethod
    def prepare(cls, payload: PayLoad) -> Runner:
        """
        runner 构建。约定请求体结构为：

        {
          "parameter": {
            "task_name": "research_agent_task",
            "reset": true
          },
          "payload": {
            "code_input": { ... ResearchAgentSandboxProcessorData 所需字段 ... },
            "topic": "需要研究的主题"
          }
        }
        """
        params = payload.payload or {}
        code_input = params.get("code_input", {})
        topic = params.get("topic", "")

        user_id = code_input.get("userId")
        if user_id:
            try:
                runner_bootstrap_web = get_bootstrap("runner_bootstrap_web")
            except ValueError:
                runner_bootstrap_web = None

            if runner_bootstrap_web and runner_bootstrap_web.user_has_running_task(user_id):
                running_task_ids = runner_bootstrap_web.get_user_running_tasks(user_id)
                running_task_text = ", ".join(sorted(running_task_ids))
                raise TaskRejectedError(
                    f"user {user_id} already has running tasks: {running_task_text}"
                )

        sandbox_input = ResearchAgentSandboxProcessorData(**code_input)
        flow_data = ResearchAgentFlowData(sandbox_input=sandbox_input, topic=topic)

        raw_id = f"{sandbox_input.userId}_{payload.created_at}_{_md5(str(sandbox_input) + topic)}"
        task_id = raw_id

        runner = Runner(
            task_id=task_id,
            flow_data=flow_data,
        )
        return runner

    async def dispatch(self, runner: Runner) -> None:
        """
        调度逻辑：
        - 找到对应 Processor（ResearchAgentProcessor）
        - 调用 processor(sandbox_input, topic)
        - 把返回的路径交给 SandboxTaskAbstract.save_task_write
        """
        try:
            self.logger.info("research_agent_task.dispatch")

            await self.report_progress(
                task_id=runner.task_id,
                runner_stat="research_agent_task",
                state="dispatch_start",
                finished=False,
            )

            data = runner.flow_data
            if "ResearchAgentFlowData" not in data.type:
                raise RuntimeError(f"Unexpected flow_data type: {data.type}")

            sandbox_input = data.sandbox_input
            topic = data.topic or ""

            processor: BaseProcessor = self.preprocess_dict.get(sandbox_input.type)
            if processor is None:
                raise RuntimeError(f"Processor not found for type={sandbox_input.type}")

            if hasattr(processor, "match") and not processor.match(sandbox_input):
                raise RuntimeError("Unsupported processor for this Sandbox input")

            result_path, log_detail_path, log_summary_path, log_run_path = processor(
                sandbox_input, topic
            )

            await self.report_progress(
                task_id=runner.task_id,
                runner_stat="research_agent_task",
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

        except Exception as exc:
            await self.report_progress(
                task_id=runner.task_id,
                runner_stat="research_agent_task",
                state="error",
                finished=True,
            )
            self.logger.error(
                f"{exc.__class__.__name__}: {exc}",
                exc_info=exc,
            )
            raise

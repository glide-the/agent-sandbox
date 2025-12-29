import hashlib
import inspect
import traceback
from typing import Dict

from sandbox.common.registry import registry
from sandbox.processors import BaseProcessor, SandboxProcessorData, get_processors
from sandbox.server.model.flow_data import PayLoad
from sandbox.tasks import FlowData, Runner, SandboxTaskAbstract


def calculate_md5(input_string):
    md5_hash = hashlib.md5()
    md5_hash.update(input_string.encode('utf-8'))
    return md5_hash.hexdigest()


class SandboxEvalFlowData(FlowData):
    sandbox_input: SandboxProcessorData

    @property
    def type(self) -> str:
        """Type of the FlowData Message, used for serialization."""
        return "SandboxEvalFlowData"


@registry.register_task("sandbox_eval_task")
class SandboxEvalTask(SandboxTaskAbstract):

    def __init__(self, preprocess_dict: Dict[str, BaseProcessor]):
        super().__init__(preprocess_dict=preprocess_dict)
        self._preprocess_dict = preprocess_dict

    @classmethod
    def from_config(cls, cfg=None):
        preprocess_dict = {}
        for preprocess in cfg.get('preprocess'):
            for key, preprocess_info in preprocess.items():
                preprocess_object = get_processors(preprocess_info.processor)
                preprocess_dict[preprocess_info.processor_name] = preprocess_object

        return cls(preprocess_dict=preprocess_dict)

    @property
    def preprocess_dict(self) -> Dict[str, BaseProcessor]:
        return self._preprocess_dict

    @classmethod
    def prepare(cls, payload: PayLoad) -> Runner:
        """
        runner任务构建
        """
        params = payload.payload
        # 获取payload中的edge和rvc的值
        code_input = params.get("code_input", {})

        # 创建一个 EdgeProcessorData 实例
        sandbox_input = SandboxProcessorData(**code_input)

        voice_flow_data = SandboxEvalFlowData(sandbox_input=sandbox_input)

        # 创建 Runner 实例并传递上面创建的 SandboxEvalFlowData 实例作为参数
        task_id = f'{sandbox_input.userId}_{int(payload.created_at)}_{calculate_md5(str(sandbox_input))}'
        runner = Runner(
            task_id=task_id,
            flow_data=voice_flow_data
        )

        return runner

    async def dispatch(self, runner: Runner) -> None:

        try:
            # 加载task
            self.logger.info('dispatch')

            # 开启任务1
            await self.report_progress(task_id=runner.task_id, runner_stat='sandbox_eval_task',
                                       state='dispatch_sandbox_eval_task')
            data = runner.flow_data
            if 'SandboxEvalFlowData' in data.type:
                if 'Sandbox' in data.sandbox_input.type:
                    preprocess_object = self.preprocess_dict.get(data.sandbox_input.type)
                    if not preprocess_object.match(data.sandbox_input):
                        raise RuntimeError('不支持的process')
                    preprocess_result = preprocess_object(data.sandbox_input)
                    if inspect.isawaitable(preprocess_result):
                        preprocess_result = await preprocess_result
                    result_path, log_detail_path, log_summary_path, log_run_path = preprocess_result

                    # 完成任务，构建响应数据
                    await self.report_progress(task_id=runner.task_id,
                                               runner_stat='sandbox_eval_task',
                                               state='finished',
                                               finished=False)

                    await super().save_task_write(runner=runner, result_path=result_path,
                                                  log_detail_path=log_detail_path,
                                                  log_summary_path=log_summary_path, log_run_path=log_run_path)

                    del result_path, log_detail_path, log_summary_path, log_run_path
                    del runner

        except Exception as e:
            await self.report_progress(task_id=runner.task_id, runner_stat='sandbox_eval_task',
                                       state='error', finished=True)

            self.logger.error(f'{e.__class__.__name__}: {e}',
                              exc_info=e)

            traceback.print_exc()
            raise e


    def complete(self, runner: Runner):
        pass

import asyncio
import logging
import os
import traceback

import requests
from omegaconf import OmegaConf

from sandbox.common.registry import registry
from sandbox.common.utils import get_abs_path, get_tmp_path
from sandbox.processors import load_preprocess
from sandbox.server.model.flow_data import PayLoad
from sandbox.tasks import get_task, load_task, tasks_cache

logger = logging.getLogger('speaker_runner')


class Speaker:
    """
        在任务系统中，"runner" 通常指的是负责执行任务的组件或模块。Runner 的生命周期是指它从创建到销毁的整个过程，
        其中包含了一些关键的阶段和操作。虽然不同的任务系统可能会有不同的实现细节，但通常可以概括为以下几个主要的生命周期阶段：

        创建（Creation）：在任务被提交或调度之前，runner 需要被创建。这个阶段可能涉及资源分配、
        初始化操作、配置设置等。Runner 的创建过程通常包括为任务分配所需的资源，准备运行环境，建立与任务管理器或调度器的连接等。

        准备（Preparation）：在 runner 开始执行任务之前，需要对任务本身进行一些准备工作。这可能包括下载所需的文件、
        加载依赖项、设置环境变量、配置运行参数等。准备阶段的目标是确保任务在执行过程中所需的一切都已就绪。

        执行（Execution）：执行阶段是 runner 的主要功能，它负责实际运行任务的代码逻辑。
        这可能涉及到执行计算、处理数据、调用外部服务等，具体取决于任务的性质。在执行阶段，runner 需要监控任务的进展，
        处理异常情况，并可能与其他系统组件进行交互。

        监控与报告（Monitoring and Reporting）：在任务执行期间，runner 需要持续监控任务的状态和进度。
        这可能包括收集性能指标、记录日志、报告错误或异常等。监控与报告是确保任务在预期范围内执行的重要手段。

        完成与清理（Completion and Cleanup）：当任务执行结束后，runner 需要处理任务的完成操作。
        这可能涉及处理执行结果、释放资源、清理临时文件、关闭连接等。完成与清理阶段的目标是确保任务执行后不会留下不必要的残留状态。

        销毁（Destruction）：在 runner 的生命周期结束时，
        需要进行销毁操作。这可能包括释放占用的资源、关闭连接、清理临时数据等。销毁阶段的目标是确保系统不会因为不再需要的 runner 而产生资源浪费或不稳定性。

    """

    def __init__(self, speakers_config_file: str = 'sandbox.yaml',
                 verbose: bool = False):
        self.verbose = verbose

        config = OmegaConf.load(get_abs_path(speakers_config_file))
        load_preprocess(config=config.get('preprocess'))
        load_task(config.get("tasks"))

    async def preparation_runner(self, task_id: str, payload: PayLoad = None):
        voice_task = get_task(payload.parameter.task_name)
        try:

            runner = voice_task.prepare(payload=payload)

            await voice_task.dispatch(runner=runner)

            await voice_task.report_progress(task_id=runner.task_id, runner_stat='preparation_runner',
                                             state='end',
                                             finished=True)
        except Exception as e:

            logger.error(f'{e.__class__.__name__}: {e}',
                         exc_info=e)
            await voice_task.report_progress(task_id=task_id, runner_stat='preparation_runner',
                                             state='error', finished=True)


class WebSpeaker(Speaker):
    def __init__(self, speakers_config_file: str = 'sandbox.yaml',
                 verbose: bool = False,
                 nonce: str = ''):
        super().__init__(speakers_config_file=speakers_config_file, verbose=verbose)

        config = OmegaConf.load(get_abs_path(speakers_config_file))
        remote_infos = {}
        for bootstraps in config.get("bootstrap"):
            for key, bootstrap_cfg in bootstraps.items():  # 使用 .items() 方法获取键值对

                remote_infos[bootstrap_cfg.name] = {
                    'host': bootstrap_cfg.host,
                    'port': bootstrap_cfg.port
                }

        self.remote_infos = remote_infos
        self.nonce = nonce
        self._task_results = {}

    async def listen(self):
        """
        监听server端任务，注册任务监听器接收消息通知
        (已修改为异步并发调度模式)
        """
        logger.info('Waiting for WebSpeaker tasks')

        MAX_CONCURRENT_TASKS = 100
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
        background_tasks = set()

        async def sync_state(task_id: str, runner_stat: str, state: str, finished: bool, result: dict):
            # wait for runner to be end first (bad solution?)
            finished = finished and not state == 'finished'
            while True:
                try:
                    data = {
                        'task_id': task_id,
                        'runner_stat': runner_stat,
                        'nonce': self.nonce,
                        'state': state,
                        'finished': finished,
                        'result': result
                    }
                    # 处理每个runner的调度
                    for _key, _remote_info in self.remote_infos.items():

                        if self._task_results.get(_key) is None or self._task_results.get(_key).get("task_id") is None:
                            continue
                        if task_id in self._task_results.get(_key).get("task_id"):
                            host = '127.0.0.1'
                            if not '0.0.0.0' in _remote_info.get("host"):
                                host = _remote_info.get("host")

                            requests.post(
                                f'http://{host}:{_remote_info.get("port")}/runner/task-update-internal',
                                json=data, timeout=20)
                            break
                    break
                except Exception:
                    # if translation is finished server has to know
                    if finished:
                        continue
                    else:
                        break

        for key, task in tasks_cache.items():
            task.add_progress_hook(sync_state)

        async def task_worker(t_id: str, p_load: PayLoad):
            async with semaphore:
                try:
                    logger.info(f'Processing task {t_id} concurrently')
                    await self.preparation_runner(task_id=t_id, payload=p_load)
                except Exception as e:
                    logger.error(f"Task {t_id} failed: {e}")
                    logger.error(traceback.format_exc())

        while True:
            if semaphore.locked():
                await asyncio.sleep(0.1)
                continue

            self._task_results = self._get_task()

            has_valid_task = False
            if self._task_results:
                for key, task_info in self._task_results.items():
                    if task_info and task_info.get("task_id"):
                        has_valid_task = True
                        break

            if not has_valid_task:
                await asyncio.sleep(1)
                continue

            for key, remote_info in self.remote_infos.items():
                task_info = self._task_results.get(key)
                if not task_info or not task_info.get("task_id"):
                    continue
                task_id = task_info.get("task_id")

                try:
                    payload_obj = PayLoad.parse_obj(task_info.get("data"))
                    task = asyncio.create_task(task_worker(task_id, payload_obj))
                    background_tasks.add(task)
                    task.add_done_callback(background_tasks.discard)
                except Exception as e:
                    logger.error(f"Failed to schedule task {task_id}: {e}")

            await asyncio.sleep(0.01)

    def _get_task(self):
        try:
            task_results = {}
            for key, _remote_info in self.remote_infos.items():  # 使用 .items() 方法获取键值对

                host = '127.0.0.1'
                if not '0.0.0.0' in _remote_info.get("host"):
                    host = _remote_info.get("host")

                response = requests.get(
                    f'http://{host}:{_remote_info["port"]}/runner/task-internal?nonce={self.nonce}',
                    timeout=3600)
                # 检查响应状态码
                if response.status_code == 200:
                    task_results[key] = response.json().get("data")
            return task_results
        except Exception:
            logger.error(f'runner_bootstrap_web connection error: {traceback.format_exc()}')
            return None

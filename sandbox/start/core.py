import asyncio
import logging
import traceback

import requests
from omegaconf import OmegaConf

from sandbox.common.utils import get_abs_path
from sandbox.processors import load_preprocess
from sandbox.server.model.flow_data import PayLoad
from sandbox.tasks import get_task, load_task, tasks_cache

logger = logging.getLogger("speaker_runner")


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

    def __init__(
        self, speakers_config_file: str = "sandbox.yaml", verbose: bool = False
    ):
        self.verbose = verbose

        config = OmegaConf.load(get_abs_path(speakers_config_file))
        load_preprocess(config=config.get("preprocess"))
        load_task(config.get("tasks"))

    async def preparation_runner(self, task_id: str, payload: PayLoad = None):
        voice_task = get_task(payload.parameter.task_name)
        try:
            runner = voice_task.prepare(payload=payload)
            if runner.task_id != task_id:
                raise RuntimeError(
                    f"prepared task id {runner.task_id!r} does not match dispatched id {task_id!r}"
                )

            await voice_task.dispatch(runner=runner)

            await voice_task.report_progress(
                task_id=runner.task_id,
                runner_stat="preparation_runner",
                state="end",
                finished=True,
            )
        except Exception as e:
            logger.error(f"{e.__class__.__name__}: {e}", exc_info=e)
            await voice_task.report_progress(
                task_id=task_id,
                runner_stat="preparation_runner",
                state="error",
                finished=True,
            )


class WebSpeaker(Speaker):
    def __init__(
        self,
        speakers_config_file: str = "sandbox.yaml",
        verbose: bool = False,
        nonce: str = "",
    ):
        super().__init__(speakers_config_file=speakers_config_file, verbose=verbose)

        config = OmegaConf.load(get_abs_path(speakers_config_file))
        remote_infos = {}
        for bootstraps in config.get("bootstrap"):
            for (
                key,
                bootstrap_cfg,
            ) in bootstraps.items():  # 使用 .items() 方法获取键值对
                remote_infos[bootstrap_cfg.name] = {
                    "host": bootstrap_cfg.host,
                    "port": bootstrap_cfg.port,
                }

        self.remote_infos = remote_infos
        self.nonce = nonce
        # 存储所有正在处理的任务 {key: {task_id: {"data": dict, "status": "processing"/"scheduled"}}}
        self._task_results = {}
        self._completed_tasks = set()  # 记录已完成的任务ID，用于清理

    async def listen(self):
        """
        监听server端任务，注册任务监听器接收消息通知
        (已修改为异步并发调度模式)
        """
        logger.info("Waiting for WebSpeaker tasks")

        MAX_CONCURRENT_TASKS = 100
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
        background_tasks = set()

        async def sync_state(
            task_id: str, runner_stat: str, state: str, finished: bool, result: dict
        ):
            finished = finished and not state == "finished"
            attempts = 3 if finished else 1
            for attempt in range(attempts):
                try:
                    data = {
                        "task_id": task_id,
                        "runner_stat": runner_stat,
                        "nonce": self.nonce,
                        "state": state,
                        "finished": finished,
                        "result": result,
                    }
                    # 处理每个runner的调度
                    for _key, _remote_info in self.remote_infos.items():
                        if self._task_results.get(_key) is None:
                            continue
                        if task_id in self._task_results.get(_key):
                            host = "127.0.0.1"
                            if "0.0.0.0" not in _remote_info.get("host"):
                                host = _remote_info.get("host")

                            response = await asyncio.to_thread(
                                requests.post,
                                f'http://{host}:{_remote_info.get("port")}/runner/task-update-internal',
                                json=data,
                                timeout=20,
                            )
                            response.raise_for_status()
                            break
                    break
                except Exception:
                    if attempt + 1 < attempts:
                        await asyncio.sleep(0.5 * (2**attempt))
                    else:
                        logger.error(
                            "Failed to synchronize task %s state after %s attempt(s)",
                            task_id,
                            attempts,
                            exc_info=True,
                        )

            # 如果任务完成，标记为已完成
            if finished:
                self._completed_tasks.add(task_id)

        for key, task in tasks_cache.items():
            task.add_progress_hook(sync_state)

        async def task_worker(t_id: str, p_load: PayLoad):
            async with semaphore:
                try:
                    logger.info(f"Processing task {t_id} concurrently")
                    await self.preparation_runner(task_id=t_id, payload=p_load)
                except Exception as e:
                    logger.error(f"Task {t_id} failed: {e}")
                    logger.error(traceback.format_exc())

        while True:
            if semaphore.locked():
                await asyncio.sleep(0.1)
                continue

            # 获取新任务（不覆盖已有任务）
            new_tasks = await asyncio.to_thread(self._get_task)

            # 合并新任务到处理队列中
            if new_tasks:
                for key, task_info in new_tasks.items():
                    # 只添加新任务，不覆盖正在处理的任务
                    if task_info and task_info.get("task_id"):
                        task_id = task_info.get("task_id")
                        # 如果是新任务且未完成，添加到处理队列
                        if task_id not in self._completed_tasks:
                            # 初始化该key的任务字典（如果不存在）
                            if key not in self._task_results:
                                self._task_results[key] = {}

                            # 检查任务是否已经在处理队列中
                            if task_id not in self._task_results[key]:
                                self._task_results[key][task_id] = {
                                    "data": task_info.get("data"),
                                    "status": "processing",
                                }
                                logger.info(
                                    f"Added new task {task_id} to processing queue for {key}"
                                )

            # 清理已完成的任务
            for key in list(self._task_results.keys()):
                for task_id in list(self._task_results[key].keys()):
                    if task_id in self._completed_tasks:
                        logger.info(f"Removing completed task {task_id} from {key}")
                        del self._task_results[key][task_id]
                        self._completed_tasks.discard(task_id)
                # 如果该key下没有任务了，删除整个key
                if not self._task_results[key]:
                    del self._task_results[key]

            # 检查是否有有效任务需要处理
            has_valid_task = False
            for key, tasks_dict in self._task_results.items():
                for task_id, task_info in tasks_dict.items():
                    if task_info.get("status") == "processing":
                        has_valid_task = True
                        break
                if has_valid_task:
                    break

            if not has_valid_task:
                await asyncio.sleep(1)
                continue

            # 调度任务
            for key, remote_info in self.remote_infos.items():
                if key not in self._task_results:
                    continue

                # 遍历该key下的所有任务
                for task_id, task_info in list(self._task_results[key].items()):
                    if task_info.get("status") != "processing":
                        continue

                    # 标记任务为已调度，避免重复调度
                    self._task_results[key][task_id]["status"] = "scheduled"

                    try:
                        payload_obj = PayLoad.parse_obj(task_info.get("data"))
                        task = asyncio.create_task(task_worker(task_id, payload_obj))
                        background_tasks.add(task)
                        task.add_done_callback(background_tasks.discard)
                    except Exception as e:
                        logger.error(f"Failed to schedule task {task_id}: {e}")
                        # 调度失败，重置状态以便重试
                        self._task_results[key][task_id]["status"] = "processing"

            await asyncio.sleep(0.01)

    def _get_task(self):
        try:
            task_results = {}
            for (
                key,
                _remote_info,
            ) in self.remote_infos.items():  # 使用 .items() 方法获取键值对
                host = "127.0.0.1"
                if "0.0.0.0" not in _remote_info.get("host"):
                    host = _remote_info.get("host")

                response = requests.get(
                    f'http://{host}:{_remote_info["port"]}/runner/task-internal?nonce={self.nonce}',
                    timeout=3600,
                )
                # 检查响应状态码
                if response.status_code == 200:
                    task_results[key] = response.json().get("data")
            return task_results
        except Exception:
            logger.error(
                f"runner_bootstrap_web connection error: {traceback.format_exc()}"
            )
            return None

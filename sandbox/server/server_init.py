import asyncio
import logging
import os
import secrets
import subprocess
import sys
import time
import traceback

from omegaconf import OmegaConf
from sandbox.common.registry import registry
from sandbox.common.utils import get_abs_path
from sandbox.processors import load_preprocess
from sandbox.server.bootstrap.bootstrap_register import get_bootstrap, load_bootstrap
from sandbox.tasks import load_task

logger = logging.getLogger("server_init")

root_dir = os.path.dirname(os.path.abspath(__file__))
registry.register_path("server_library_root", root_dir)
# Time to wait for web client to send a request to /task-state request
# before that web clients task gets removed from the queue
WEB_CLIENT_TIMEOUT = 1800
# Time before finished tasks get removed from memory
FINISHED_TASK_REMOVE_TIMEOUT = 300


def generate_nonce():
    return secrets.token_hex(16)


def start_translator_client_proc(speakers_config_file: str, nonce: str = None):
    cmds = [
        sys.executable,
        "-m",
        "sandbox.start.start",
        "--mode",
        "web_runner",
        "--speakers-config-file",
        speakers_config_file,
        "--nonce",
        nonce,
        "--verbose",
    ]

    proc = subprocess.Popen(cmds, cwd=f"{registry.get_path('library_root')}")
    return proc


async def start_async_app(speakers_config_file: str, nonce: str = None):
    config = OmegaConf.load(get_abs_path(speakers_config_file))
    # The API validates the same immutable Task/Processor binding that the
    # worker will use. Constructors do not import or initialize GPU models.
    load_preprocess(config=config.get("preprocess"))
    load_task(config.get("tasks"))
    load_bootstrap(config=config.get("bootstrap"))

    runner_bootstrap_web = get_bootstrap("runner_bootstrap_web")

    runner_bootstrap_web.set_nonce(nonce=nonce)
    await runner_bootstrap_web.run()
    return runner_bootstrap_web


async def dispatch(speakers_config_file: str, nonce: str = None):
    global WEB_CLIENT_TIMEOUT, FINISHED_TASK_REMOVE_TIMEOUT
    if nonce is None:
        nonce = os.getenv("MT_WEB_NONCE", generate_nonce())
    # 写入特定日志
    logger.info(f"Nonce: {nonce}")

    runner = await start_async_app(
        speakers_config_file=speakers_config_file, nonce=nonce
    )
    # Create client process
    client_process = start_translator_client_proc(speakers_config_file, nonce=nonce)
    config = OmegaConf.load(get_abs_path(speakers_config_file))
    bootstrap_config = config.get("bootstrap")

    for bootstraps in bootstrap_config:
        for key, bootstrap_cfg in bootstraps.items():  # 使用 .items() 方法获取键值对
            if bootstrap_cfg.name == "runner_bootstrap_web":
                if bootstrap_cfg.get("web_client_timeout") is not None:
                    WEB_CLIENT_TIMEOUT = int(bootstrap_cfg.get("web_client_timeout"))
                if bootstrap_cfg.get("finished_task_remove_timeout") is not None:
                    FINISHED_TASK_REMOVE_TIMEOUT = int(
                        bootstrap_cfg.get("finished_task_remove_timeout")
                    )

                break
                pass

    logger.info(f"WEB_CLIENT_TIMEOUT: {WEB_CLIENT_TIMEOUT}")
    logger.info(f"FINISHED_TASK_REMOVE_TIMEOUT: {FINISHED_TASK_REMOVE_TIMEOUT}")
    worker_paused = False
    try:
        while True:
            """任务队列状态维护"""
            await asyncio.sleep(1)

            # Restart client if OOM or similar errors occured
            if not worker_paused and client_process.poll() is not None:
                music_tasks = [
                    task_id
                    for task_id in runner.ongoing_tasks
                    if runner.task_data.get(task_id)
                    and runner.task_data[task_id].parameter.task_name
                    in {
                        "yue2_task",
                        "sheetsage2_task",
                        "music_score_task",
                        "music_listen_task",
                    }
                ]
                if music_tasks:
                    logger.critical(
                        "Music worker exited unexpectedly; task dispatch is paused to avoid "
                        "resampling while model child state may remain"
                    )
                    for task_id in music_tasks:
                        state = {
                            "task_id": task_id,
                            "info": "error",
                            "finished": True,
                            "result": {
                                "stage": "interrupted",
                                "outcome": "failed",
                                "model_completed": False,
                                "delivery_status": "failed",
                                "artifacts": [],
                                "error": {
                                    "kind": "worker_crash",
                                    "message": "worker exited; automatic model restart is paused",
                                },
                            },
                        }
                        runner.task_states[task_id] = state
                        runner.ongoing_tasks.remove(task_id)
                        if runner.music_store:
                            runner.music_store.update_state(task_id, state)
                        payload = runner.task_data.get(task_id)
                        if payload:
                            user_id = runner.extract_user_id(payload)
                            runner.update_user_task_index(user_id, task_id, True)
                    worker_paused = True
                else:
                    logger.info("Restarting translator process")
                    if runner.ongoing_tasks:
                        task_id = runner.ongoing_tasks.pop(0)
                        state = runner.task_states[task_id]
                        state["info"] = "error"
                        state["finished"] = True
                    client_process = start_translator_client_proc(
                        speakers_config_file=speakers_config_file, nonce=nonce
                    )

            # Filter queued and finished tasks
            now = time.time()
            to_del_task_ids = set()
            for tid, s in runner.task_states.items():
                payload = runner.task_data[tid]
                logger.debug(
                    f"Checking now: {now}, task_id: {tid}, state: {s}, payload: {payload}"
                )
                # Remove finished tasks
                if (
                    s["finished"]
                    and (s["info"] == "end" or s["info"] == "error")
                    and (now - payload.finished_at) > FINISHED_TASK_REMOVE_TIMEOUT
                ):
                    to_del_task_ids.add(tid)

                # Remove queued tasks without web client
                elif WEB_CLIENT_TIMEOUT >= 0 and payload.parameter.task_name not in {
                    "yue2_task",
                    "sheetsage2_task",
                    "music_score_task",
                    "music_listen_task",
                }:
                    if (
                        tid not in runner.ongoing_tasks
                        and not s["finished"]
                        and (now - payload.requested_at) > WEB_CLIENT_TIMEOUT
                    ):
                        logger.info(f"REMOVING TASK，{tid}")
                        to_del_task_ids.add(tid)
                        try:
                            runner.queue.remove(tid)
                        except Exception:
                            pass

            for tid in to_del_task_ids:
                logger.info(f"Removing task {tid} from queue")
                # Remove task from queue
                payload = runner.task_data.get(tid)
                if payload:
                    user_id = runner.extract_user_id(payload)
                    if user_id:
                        runner.update_user_task_index(
                            user_id=user_id,
                            task_id=tid,
                            finished=True,
                        )
                del runner.task_states[tid]
                del runner.task_data[tid]

    except Exception as e:
        logger.error(f"{e.__class__.__name__}: {e}")
        if client_process.poll() is None:
            # client_process.terminate()
            client_process.kill()
        await runner.destroy()
        traceback.print_exc()
        raise

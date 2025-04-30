import asyncio
import json
import logging
import os
from pathlib import Path
import time

import anyio
from anyio.streams.text import TextReceiveStream
from contextlib import asynccontextmanager
import nest_asyncio

from sandbox.common.registry import registry
from sandbox.processors import BaseProcessor, ProcessorData

logger = logging.getLogger('sandbox_started')


class SandboxProcessorData(ProcessorData):
    """
       填写input_param.json标准答案和测试提交文件，例如：

       {
         "fileData":{
           "evaluatorDir":"", # 默认("eval", user_id)
           "evaluatorPath":"", # 默认("eval", user_id, "eval_result.json")
           "standardFileDir":"", # 默认("eval", user_id, "eval")
           "standardFilePath":"answer.txt",
           "userFileDir":"", # 默认("eval", user_id, "submit")
           "userFilePath":"submit.txt", # 程序自动填写
           "logDetailPath": "eval/log_detail.jsonl",
           "logSummaryPath": "eval/log_summary.json",
           "logRunPath": "eval/log_run.log"
         }
       }
    """
    evaluatorDir: str
    evaluatorPath: str
    standardFileDir: str
    standardFilePath: str
    userFileDir: str
    userFilePath: str
    userId: str
    userImagesDir: str = ""
    is_mm_eval: bool = False
    logDetailPath: str = "eval/log_detail.jsonl"
    logSummaryPath: str = "eval/log_summary.json"
    logRunPath: str = "eval/log_run.log"

    @property
    def type(self) -> str:
        """Type of the Message, used for serialization."""
        return "Sandbox"


@registry.register_processor("sandbox_started_processor")
class SandboxToVoice(BaseProcessor):

    def __init__(self, cwd: str):
        super().__init__()
        self.cwd = cwd
        nest_asyncio.apply()

    def __call__(
            self,
            code_input: SandboxProcessorData
    ):

        # 同步调用协程代码
        result_path, log_detail_path, log_summary_path, log_run_path = asyncio.get_event_loop().run_until_complete(
            self._call_sandbox_start(code_input=code_input))

        return result_path, log_detail_path, log_summary_path, log_run_path

    @classmethod
    def from_config(cls, cfg=None):
        if cfg is None:
            raise RuntimeError("from_config cfg is None.")

        cwd = cfg.get("cwd", "/app/sandbox")

        return cls(cwd=cwd)

    def match(self, data: ProcessorData):
        return "Sandbox" in data.type

    async def _call_sandbox_start(self, code_input: SandboxProcessorData):
        cwd = self.cwd
        code_input.evaluatorDir = (Path(cwd) / code_input.evaluatorDir).as_posix()
        code_input.evaluatorPath = (Path(code_input.evaluatorDir) / code_input.evaluatorPath).as_posix()
        code_input.standardFileDir = (Path(cwd) / code_input.standardFileDir).as_posix()
        code_input.standardFilePath = (Path(code_input.standardFileDir) / code_input.standardFilePath).as_posix()
        code_input.userFileDir = (Path(cwd) / code_input.userFileDir).as_posix()
        code_input.userFilePath = (Path(code_input.userFileDir) / code_input.userFilePath).as_posix()
        code_input.userImagesDir = (Path(code_input.userFileDir) / code_input.userImagesDir).as_posix()
        code_input.logDetailPath = (Path(code_input.evaluatorDir) / code_input.logDetailPath).as_posix()
        code_input.logSummaryPath = (Path(code_input.evaluatorDir) / code_input.logSummaryPath).as_posix()
        code_input.logRunPath = (Path(code_input.evaluatorDir) / code_input.logRunPath).as_posix()
        # 转换为json字符串fileData
        json_str = json.dumps({
            "fileData": code_input.dict()
        })
        # 创建 evaluatorDir
        if not os.path.exists(code_input.evaluatorDir):
            os.makedirs(code_input.evaluatorDir, exist_ok=True)
        # 创建 standardFileDir
        if not os.path.exists(code_input.standardFileDir):
            os.makedirs(code_input.standardFileDir, exist_ok=True)
        # 创建 userFileDir
        if not os.path.exists(code_input.userFileDir):
            os.makedirs(code_input.userFileDir, exist_ok=True)

        # 创建用户目录

        user_path = os.path.join(cwd, "eval", code_input.userId)
        if not os.path.exists(user_path):
            os.makedirs(user_path, exist_ok=True)

        # 保存到文件
        with open(os.path.join(user_path, "input_param.json"), "w") as f:
            f.write(json_str)
        # 执行脚本之前，查看标准答案是否存在，查看用户提交文件是否存在
        # 如果不存在，返回错误信息,提示调用程序初始化工作空间
        if not os.path.exists(code_input.standardFilePath):
            raise RuntimeError("standard file not found")

        if not os.path.exists(code_input.userFilePath):
            raise RuntimeError("user file not found")

        # 判断评测目录
        os.makedirs(code_input.evaluatorDir, exist_ok=True)

        result_path = os.path.join(cwd, code_input.evaluatorDir, code_input.evaluatorPath)

        # debugger

        async with run_evaluate_process(user_path, result_path):
            pass  # 如果你需要在运行期间做点啥，这里可以写

        return result_path, code_input.logDetailPath, code_input.logSummaryPath, code_input.logRunPath


@asynccontextmanager
async def run_evaluate_process(user_path: str, result_path: str):
    """
    用异步方式运行评测脚本 evaluate.py 并实时打印 stdout/stderr 到日志。
    """
    from subprocess import PIPE

    py_entrance = os.path.join(user_path, "evaluate.py")
    input_param = os.path.join(user_path, "input_param.json")

    cmd = ["python", "-u", py_entrance, input_param, result_path]

    logger.info(f"Running evaluate command: {' '.join(cmd)} in {user_path}")

    async with await anyio.open_process(
            cmd,
            cwd=user_path,
            stdout=PIPE,
            stderr=PIPE,
    ) as process:

        last_output_time = time.time()
        silence_timeout = 60  # N秒无输出就杀掉进程，可调整

        async def stream_reader(stream, label):
            nonlocal last_output_time
            try:
                async for line in TextReceiveStream(stream, encoding="utf-8", errors="replace"):
                    last_output_time = time.time()
                    logger.info(f"[{user_path}] [{label}] {line.strip()}")
            except Exception as e:
                logger.warning(f"[{user_path}] [{label}] reader failed: {e}")

        async def watchdog():
            while True:
                await anyio.sleep(1)
                if process.returncode is not None:
                    # 子进程已经结束，退出 watchdog
                    break
                if time.time() - last_output_time > silence_timeout:
                    logger.warning(f"No log output for {silence_timeout} seconds, terminating process.")
                    process.terminate()
                    break

        async with anyio.create_task_group() as tg:
            tg.start_soon(stream_reader, process.stdout, "STDOUT")
            tg.start_soon(stream_reader, process.stderr, "STDERR")
            tg.start_soon(watchdog)
            yield  # 控制权交给调用方（如 _call_sandbox_start）

        await process.wait()
        logger.info(f"Evaluate process exited with code {process.returncode}")
        if process.returncode != 0:
            raise RuntimeError("Evaluate script failed or was terminated due to silence.")
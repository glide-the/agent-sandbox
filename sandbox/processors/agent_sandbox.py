import json
import logging
import os
import shutil
import asyncio
import time   # 新增：用于时间戳和耗时
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import anyio
from anyio.streams.text import TextReceiveStream
import nest_asyncio
from pydantic import Field

from sandbox.common.registry import registry
from sandbox.processors import BaseProcessor, ProcessorData

logger = logging.getLogger("agent_sandbox")


class AgentMem0ProcessorData(ProcessorData):
    """Processor data for the L1 Mem0 interface call."""

    user_id: str
    conversation_id: Optional[str] = None
    messages: List[Dict[str, Any]] = Field(default_factory=list)

    mem0_endpoint: str
    mem0_api_key: Optional[str] = None

    workspace_dir: str = "workspace"
    result_filename: str = "mem0_result.json"

    @property
    def type(self) -> str:
        return "AgentMem0"


@registry.register_processor("agent_mem0_processor")
class AgentMem0Processor(BaseProcessor):
    """L1 processor: invoke Mem0 HTTP API and write result to workspace."""

    def __init__(self, cwd: str):
        super().__init__()
        self.cwd = cwd

    @classmethod
    def from_config(cls, cfg=None):
        if cfg is None:
            raise RuntimeError("agent_mem0_processor.from_config cfg is None.")
        cwd = cfg.get("cwd", "/app/sandbox")
        return cls(cwd=cwd)

    @classmethod
    def match(cls, data: ProcessorData):
        return "AgentMem0" in data.type

    def __call__(self, data: AgentMem0ProcessorData):
        import requests

        workspace_root = os.path.join(self.cwd, data.workspace_dir, data.user_id)
        os.makedirs(workspace_root, exist_ok=True)
        result_path = os.path.join(workspace_root, data.result_filename)

        headers = {"Content-Type": "application/json"}
        if data.mem0_api_key:
            headers["Authorization"] = f"Bearer {data.mem0_api_key}"

        payload = {
            "user_id": data.user_id,
            "conversation_id": data.conversation_id,
            "messages": data.messages,
        }

        resp = requests.post(
            data.mem0_endpoint,
            headers=headers,
            json=payload,
            timeout=9999,
        )
        resp.raise_for_status()
        result_json = resp.json()

        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result_json, f, ensure_ascii=False, indent=2)

        log_detail_path = os.path.join(workspace_root, "mem0_log_detail.jsonl")
        log_summary_path = os.path.join(workspace_root, "mem0_log_summary.json")
        log_run_path = os.path.join(workspace_root, "mem0_log_run.log")

        return result_path, log_detail_path, log_summary_path, log_run_path


class AgentWorkspaceL2ProcessorData(ProcessorData):
    """Processor data for the L2 workspace kode workflow."""

    user_id: str
    workspace_dir: str = "workspace"
    workflow_name: str = "l2_workflow"

    mcp_endpoint: Optional[str] = None
    mcp_connection_id: Optional[str] = None

    result_filename: str = "l2_result.json"
    logDetailPath: str = "l2/log_detail.jsonl"
    logSummaryPath: str = "l2/log_summary.json"
    logRunPath: str = "l2/log_run.log"

    @property
    def type(self) -> str:
        return "AgentWorkspaceL2"


class AgentWorkspaceL3ProcessorData(ProcessorData):
    """Processor data for the L3 workspace kode workflow."""

    user_id: str
    workspace_dir: str = "workspace"
    workflow_name: str = "l3_workflow"

    mcp_endpoint: Optional[str] = None
    mcp_connection_id: Optional[str] = None

    result_filename: str = "l3_result.json"
    logDetailPath: str = "l3/log_detail.jsonl"
    logSummaryPath: str = "l3/log_summary.json"
    logRunPath: str = "l3/log_run.log"

    @property
    def type(self) -> str:
        return "AgentWorkspaceL3"


@asynccontextmanager
async def run_kode_workflow(
    user_workspace: str,
    workflow_name: str,
    log_run_path: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    mcp_endpoint: Optional[str] = None,
    mcp_connection_id: Optional[str] = None,
):
    """
    Launch a kode workflow within the given user workspace.
    """

    from subprocess import PIPE

    # Execute kode mcp add-sse command if mcp_endpoint and mcp_connection_id are provided
    if mcp_endpoint and mcp_connection_id:
        import subprocess
        mcp_cmd = ["kode", "mcp", "add-sse", mcp_connection_id, mcp_endpoint]
        logger.info(f"Running MCP setup: {' '.join(mcp_cmd)} in {user_workspace}")
        try:
            subprocess.run(mcp_cmd, cwd=user_workspace, check=True, capture_output=True, text=True)
            logger.info(f"MCP setup completed for connection {mcp_connection_id}")
        except subprocess.CalledProcessError as e:
            logger.error(f"MCP setup failed: {e}")
            raise RuntimeError(f"kode mcp add-sse command failed: {e}")

    cmd = ["kode",  workflow_name]
    logger.info(f"Running kode workflow: {' '.join(cmd)} in {user_workspace}")

    # Setup file logging if log_run_path is provided
    file_handler = None
    if log_run_path:
        # Ensure log directory exists
        log_dir = os.path.dirname(log_run_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        # Create file handler for dynamic logging
        file_handler = logging.FileHandler(log_run_path, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.INFO)

        # Create formatter for file logs
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)

        # Add file handler to logger
        logger.addHandler(file_handler)

        # Write initial log entry
        logger.info(f"Starting kode workflow logging to: {log_run_path}")

    async with await anyio.open_process(
        cmd,
        cwd=user_workspace,
        stdout=PIPE,
        stderr=PIPE,
        env=env,
    ) as process:
        last_output_time = time.time()
        silence_timeout = 300

        async def stream_reader(stream, label: str):
            nonlocal last_output_time
            try:
                async for line in TextReceiveStream(
                    stream, encoding="utf-8", errors="replace"
                ):
                    last_output_time = anyio.current_time()
                    log_msg = f"[{user_workspace}] [{label}] {line.strip()}"
                    logger.info(log_msg)
                    # Also write to file if available
                    if file_handler:
                        file_handler.emit(
                            logging.LogRecord(
                                name="agent_sandbox",
                                level=logging.INFO,
                                pathname="",
                                lineno=0,
                                msg=log_msg,
                                args=(),
                                exc_info=None
                            )
                        )
            except Exception as e:  # pragma: no cover - logging only
                warning_msg = f"[{user_workspace}] [{label}] reader failed: {e}"
                logger.warning(warning_msg)
                # Also write to file if available
                if file_handler:
                    file_handler.emit(
                        logging.LogRecord(
                            name="agent_sandbox",
                            level=logging.WARNING,
                            pathname="",
                            lineno=0,
                            msg=warning_msg,
                            args=(),
                            exc_info=None
                        )
                    )

        async def watchdog():
            while True:
                await anyio.sleep(1)
                if process.returncode is not None:
                    break
                if anyio.current_time() - last_output_time > silence_timeout:
                    warning_msg = (
                        f"No log output for {silence_timeout} seconds, terminating process."
                    )
                    logger.warning(warning_msg)
                    # Also write to file if available
                    if file_handler:
                        file_handler.emit(
                            logging.LogRecord(
                                name="agent_sandbox",
                                level=logging.WARNING,
                                pathname="",
                                lineno=0,
                                msg=warning_msg,
                                args=(),
                                exc_info=None
                            )
                        )
                    process.terminate()
                    break

        try:
            async with anyio.create_task_group() as tg:
                tg.start_soon(stream_reader, process.stdout, "STDOUT")
                tg.start_soon(stream_reader, process.stderr, "STDERR")
                tg.start_soon(watchdog)
                yield

            await process.wait()
            exit_msg = f"Kode workflow exited with code {process.returncode}"
            logger.info(exit_msg)
            # Also write to file if available
            if file_handler:
                file_handler.emit(
                    logging.LogRecord(
                        name="agent_sandbox",
                        level=logging.INFO,
                        pathname="",
                        lineno=0,
                        msg=exit_msg,
                        args=(),
                        exc_info=None
                    )
                )

            if process.returncode != 0:
                error_msg = "Kode workflow failed or was terminated due to silence."
                # Also write to file if available
                if file_handler:
                    file_handler.emit(
                        logging.LogRecord(
                            name="agent_sandbox",
                            level=logging.ERROR,
                            pathname="",
                            lineno=0,
                            msg=error_msg,
                            args=(),
                            exc_info=None
                        )
                    )
                raise RuntimeError(error_msg)
        finally:
            # Clean up file handler
            if file_handler:
                file_handler.flush()
                file_handler.close()
                logger.removeHandler(file_handler)


@registry.register_processor("agent_workspace_l2_processor")
class AgentWorkspaceL2Processor(BaseProcessor):
    """L2 processor: run kode workflow in user workspace for intermediate results."""

    def __init__(self, cwd: str):
        super().__init__()
        self.cwd = cwd
        nest_asyncio.apply()

    @classmethod
    def from_config(cls, cfg=None):
        if cfg is None:
            raise RuntimeError(
                "agent_workspace_l2_processor.from_config cfg is None."
            )
        cwd = cfg.get("cwd", "/app/sandbox")
        return cls(cwd=cwd)

    @classmethod
    def match(cls, data: ProcessorData):
        return "AgentWorkspaceL2" in data.type

    async def _call_kode(self, data: AgentWorkspaceL2ProcessorData):
        # Handle paths similar to _call_sandbox_start method
        # 1. 计算用户工作空间目录
        user_workspace = os.path.join(self.cwd, data.workspace_dir, data.user_id)
        os.makedirs(user_workspace, exist_ok=True)

        data.logDetailPath = (Path(user_workspace) / data.logDetailPath).as_posix()
        data.logSummaryPath = (Path(user_workspace) / data.logSummaryPath).as_posix()
        data.logRunPath = (Path(user_workspace) / data.logRunPath).as_posix()

        # 2. 初始化 memory_dis：从全局 workspace/memory_dis 拷贝到 user_workspace/memory_dis
        src_memory_dis = os.path.join(self.cwd, data.workspace_dir, "memory_dis")
        dst_memory_dis = os.path.join(user_workspace, "memory_dis")

        try:
            if os.path.exists(src_memory_dis):
                if os.path.exists(dst_memory_dis):
                    shutil.rmtree(dst_memory_dis)
                shutil.copytree(src_memory_dis, dst_memory_dis)
                logger.info(
                    f"Initialized user memory_dis: {src_memory_dis} -> {dst_memory_dis}"
                )
            else:
                logger.warning(
                    f"Global memory_dis not found, skip copy: {src_memory_dis}"
                )
        except Exception as e:
            # memory_dis 初始化失败不阻断流程，只打 warning
            logger.warning(f"Failed to init user memory_dis: {e}")

        # 3. 结果文件和日志路径
        result_path = os.path.join(user_workspace, data.result_filename)
        log_detail_path = data.logDetailPath
        log_summary_path = data.logSummaryPath
        log_run_path = data.logRunPath

        # 确保日志目录存在
        for log_path in (log_detail_path, log_summary_path, log_run_path):
            log_dir = os.path.dirname(log_path)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
 
        env = os.environ.copy()
        # 确保交互式CLI有正确的终端环境
        env["PYTHONUNBUFFERED"] = "1"
        env["FORCE_COLOR"] = "1"  # 强制启用颜色输出

        async with run_kode_workflow(
            user_workspace=dst_memory_dis,
            workflow_name=data.workflow_name,
            log_run_path=log_run_path,
            env=env,
            mcp_endpoint=data.mcp_endpoint,
            mcp_connection_id=data.mcp_connection_id,
        ):
                pass
        # 8. 返回给 SandboxTaskAbstract.save_task_write 使用
        return result_path, log_detail_path, log_summary_path, log_run_path

    def __call__(self, data: AgentWorkspaceL2ProcessorData):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self._call_kode(data))


@registry.register_processor("agent_workspace_l3_processor")
class AgentWorkspaceL3Processor(BaseProcessor):
    """L3 processor: run kode workflow in user workspace for final results."""

    def __init__(self, cwd: str):
        super().__init__()
        self.cwd = cwd
        nest_asyncio.apply()

    @classmethod
    def from_config(cls, cfg=None):
        if cfg is None:
            raise RuntimeError(
                "agent_workspace_l3_processor.from_config cfg is None."
            )
        cwd = cfg.get("cwd", "/app/sandbox")
        return cls(cwd=cwd)

    @classmethod
    def match(cls, data: ProcessorData):
        return "AgentWorkspaceL3" in data.type

    async def _call_kode(self, data: AgentWorkspaceL3ProcessorData):
        # Handle paths similar to _call_sandbox_start method
        data.logDetailPath = (Path(self.cwd) / data.logDetailPath).as_posix()
        data.logSummaryPath = (Path(self.cwd) / data.logSummaryPath).as_posix()
        data.logRunPath = (Path(self.cwd) / data.logRunPath).as_posix()

        user_workspace = os.path.join(self.cwd, data.workspace_dir, data.user_id)
        os.makedirs(user_workspace, exist_ok=True)

        result_path = os.path.join(user_workspace, data.result_filename)
        log_detail_path = data.logDetailPath
        log_summary_path = data.logSummaryPath
        log_run_path = data.logRunPath

        env = os.environ.copy()
        # 确保交互式CLI有正确的终端环境
        env["PYTHONUNBUFFERED"] = "1"
        env["FORCE_COLOR"] = "1"  # 强制启用颜色输出

        async with run_kode_workflow(
            user_workspace=user_workspace,
            workflow_name=data.workflow_name,
            log_run_path=log_run_path,
            env=env,
            mcp_endpoint=data.mcp_endpoint,
            mcp_connection_id=data.mcp_connection_id,
        ):
            pass

        return result_path, log_detail_path, log_summary_path, log_run_path

    def __call__(self, data: AgentWorkspaceL3ProcessorData):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self._call_kode(data))

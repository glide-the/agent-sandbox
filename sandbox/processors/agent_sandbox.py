import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
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
    result_path: str,
    env: Optional[Dict[str, str]] = None,
):
    """
    Launch a kode workflow within the given user workspace.
    """

    from subprocess import PIPE

    cmd = ["kode",  workflow_name, "--output", result_path]
    logger.info(f"Running kode workflow: {' '.join(cmd)} in {user_workspace}")

    async with await anyio.open_process(
        cmd,
        cwd=user_workspace,
        stdout=PIPE,
        stderr=PIPE,
        env=env,
    ) as process:
        last_output_time = 0.0
        silence_timeout = 300

        async def stream_reader(stream, label: str):
            nonlocal last_output_time
            try:
                async for line in TextReceiveStream(
                    stream, encoding="utf-8", errors="replace"
                ):
                    last_output_time = anyio.current_time()
                    logger.info(f"[{user_workspace}] [{label}] {line.strip()}")
            except Exception as e:  # pragma: no cover - logging only
                logger.warning(f"[{user_workspace}] [{label}] reader failed: {e}")

        async def watchdog():
            while True:
                await anyio.sleep(1)
                if process.returncode is not None:
                    break
                if anyio.current_time() - last_output_time > silence_timeout:
                    logger.warning(
                        f"No log output for {silence_timeout} seconds, terminating process."
                    )
                    process.terminate()
                    break

        async with anyio.create_task_group() as tg:
            tg.start_soon(stream_reader, process.stdout, "STDOUT")
            tg.start_soon(stream_reader, process.stderr, "STDERR")
            tg.start_soon(watchdog)
            yield

        await process.wait()
        logger.info(f"Kode workflow exited with code {process.returncode}")
        if process.returncode != 0:
            raise RuntimeError(
                "Kode workflow failed or was terminated due to silence."
            )


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
        user_workspace = os.path.join(self.cwd, data.workspace_dir, data.user_id)
        os.makedirs(user_workspace, exist_ok=True)

        result_path = os.path.join(user_workspace, data.result_filename)
        log_detail_path = os.path.join(self.cwd, data.logDetailPath)
        log_summary_path = os.path.join(self.cwd, data.logSummaryPath)
        log_run_path = os.path.join(self.cwd, data.logRunPath)

        env = os.environ.copy()
        if data.mcp_endpoint:
            env["MCP_ENDPOINT"] = data.mcp_endpoint
        if data.mcp_connection_id:
            env["MCP_CONNECTION_ID"] = data.mcp_connection_id

        async with run_kode_workflow(
            user_workspace=user_workspace,
            workflow_name=data.workflow_name,
            result_path=result_path,
            env=env,
        ):
            pass

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
        user_workspace = os.path.join(self.cwd, data.workspace_dir, data.user_id)
        os.makedirs(user_workspace, exist_ok=True)

        result_path = os.path.join(user_workspace, data.result_filename)
        log_detail_path = os.path.join(self.cwd, data.logDetailPath)
        log_summary_path = os.path.join(self.cwd, data.logSummaryPath)
        log_run_path = os.path.join(self.cwd, data.logRunPath)

        env = os.environ.copy()
        if data.mcp_endpoint:
            env["MCP_ENDPOINT"] = data.mcp_endpoint
        if data.mcp_connection_id:
            env["MCP_CONNECTION_ID"] = data.mcp_connection_id

        async with run_kode_workflow(
            user_workspace=user_workspace,
            workflow_name=data.workflow_name,
            result_path=result_path,
            env=env,
        ):
            pass

        return result_path, log_detail_path, log_summary_path, log_run_path

    def __call__(self, data: AgentWorkspaceL3ProcessorData):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self._call_kode(data))

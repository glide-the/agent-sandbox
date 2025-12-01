import os
import logging
import time
from typing import Optional, List
from contextlib import asynccontextmanager

import anyio
from anyio.streams.text import TextReceiveStream

from sandbox.common.registry import registry


def get_abs_path(rel_path):
    return os.path.join(registry.get_path("library_root"), rel_path)


def get_tmp_path(rel_path):
    return os.path.join(registry.get_path("tmp_root"), rel_path)


logger = logging.getLogger(__name__)


async def run_command_async(
    cmd: List[str],
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
    timeout: int = 300,
    workspace_name: str = "workspace"
) -> int:
    """
    Run an async command with timeout and stream logging.

    Args:
        cmd: Command to execute as list of strings
        cwd: Working directory for command
        env: Environment variables (defaults to os.environ if None)
        timeout: Seconds of silence before terminating process
        workspace_name: Name for log prefix

    Returns:
        Process return code

    Raises:
        RuntimeError: If process fails or times out
    """
    from subprocess import PIPE

    if env is None:
        env = os.environ.copy()

    logger.info(f"Running async command: {' '.join(cmd)} in {cwd}")

    async with await anyio.open_process(
        cmd,
        cwd=cwd,
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
        env=env,
    ) as process:

        last_output_time = time.time()

        async def stream_reader(stream, label):
            nonlocal last_output_time
            try:
                async for line in TextReceiveStream(stream, encoding="utf-8", errors="replace"):
                    last_output_time = time.time()
                    logger.info(f"[{workspace_name}] [{label}] {line.strip()}")
            except Exception as e:
                logger.warning(f"[{workspace_name}] [{label}] reader failed: {e}")

        async def watchdog():
            while True:
                await anyio.sleep(1)
                if process.returncode is not None:
                    break
                if time.time() - last_output_time > timeout:
                    logger.warning(f"No log output for {timeout} seconds, terminating process.")
                    process.terminate()
                    break

        async with anyio.create_task_group() as tg:
            tg.start_soon(stream_reader, process.stdout, "STDOUT")
            tg.start_soon(stream_reader, process.stderr, "STDERR")
            tg.start_soon(watchdog)

        await process.wait()
        logger.info(f"Process exited with code {process.returncode}")

        if process.returncode != 0:
            raise RuntimeError(f"Command failed or was terminated due to silence (exit code: {process.returncode})")

        return process.returncode


@asynccontextmanager
async def run_kode_workflow_async(
    user_workspace: str,
    workflow_name: str,
    env: Optional[dict] = None,
    timeout: int = 300
):
    """
    Context manager for running kode workflows with async process management.

    Args:
        user_workspace: Path to user workspace
        workflow_name: Name of the kode workflow
        env: Environment variables
        timeout: Silence timeout in seconds

    Yields:
        Control to the caller for additional operations
    """
    from subprocess import PIPE

    if env is None:
        env = os.environ.copy()

    cmd = ["kode", "-c", user_workspace, workflow_name, "--debug", "--verbose", "--print"]
    logger.info(f"Running kode workflow: {' '.join(cmd)}")
    env["CI"] = "1"

    async with await anyio.open_process(
        cmd,
        cwd=user_workspace,
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
        env=env,
    ) as process:

        last_output_time = time.time()

        async def stream_reader(stream, label):
            nonlocal last_output_time
            try:
                async for line in TextReceiveStream(stream, encoding="utf-8", errors="replace"):
                    last_output_time = time.time()
                    logger.info(f"[{user_workspace}] [{label}] {line.strip()}")
            except Exception as e:
                logger.warning(f"[{user_workspace}] [{label}] reader failed: {e}")

        async def watchdog():
            while True:
                await anyio.sleep(1)
                if process.returncode is not None:
                    break
                if time.time() - last_output_time > timeout:
                    logger.warning(f"No log output for {timeout} seconds, terminating process.")
                    process.terminate()
                    break

        async with anyio.create_task_group() as tg:
            tg.start_soon(stream_reader, process.stdout, "STDOUT")
            tg.start_soon(stream_reader, process.stderr, "STDERR")
            tg.start_soon(watchdog)
            yield

        await process.wait()
        logger.info(f"Process exited with code {process.returncode}")
        if process.returncode != 0:
            raise RuntimeError("Evaluate script failed or was terminated due to silence.")


async def run_mcp_setup_async(
    mcp_endpoint: str,
    mcp_connection_id: str,
    user_workspace: str,
    workspace_name: str = "workspace"
):
    """
    Run MCP setup command using async subprocess.

    Args:
        mcp_endpoint: MCP SSE endpoint URL
        mcp_connection_id: MCP connection ID
        user_workspace: Working directory for the command
        workspace_name: Name for log prefix

    Raises:
        RuntimeError: If MCP setup command fails
    """
    mcp_cmd = ["kode", "-c", user_workspace,  "mcp", "add-sse", mcp_connection_id, mcp_endpoint]
    logger.info(f"Running MCP setup: {' '.join(mcp_cmd)} in {user_workspace}")

    try:
        await run_command_async(
            cmd=mcp_cmd,
            cwd=user_workspace,
            workspace_name=workspace_name
        )
        logger.info(f"MCP setup completed for connection {mcp_connection_id}")
    except Exception as e:
        logger.error(f"MCP setup failed: {e}")
        raise RuntimeError(f"kode mcp add-sse command failed: {e}")

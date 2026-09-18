"""Shared subprocess runtime for isolated music model environments."""

from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


@dataclass(frozen=True)
class ProcessResult:
    argv: list[str]
    returncode: int
    timed_out: bool
    stdout_tail: str
    stderr_tail: str


def resolve_python_environment(environment: str | os.PathLike[str]) -> Path:
    root = Path(environment).expanduser().resolve(strict=True)
    python = root / "bin" / "python"
    if not python.is_file() or not os.access(python, os.X_OK):
        raise RuntimeError(f"Python environment is not executable: {python}")
    return python


def preflight(
    *,
    environment: str,
    cwd: str,
    required_paths: Sequence[str] = (),
) -> tuple[Path, Path]:
    python = resolve_python_environment(environment)
    working_dir = Path(cwd).expanduser().resolve(strict=True)
    if not working_dir.is_dir():
        raise RuntimeError(f"Working directory is not a directory: {working_dir}")
    for value in required_paths:
        path = Path(value).expanduser().resolve(strict=True)
        if not path.exists():
            raise RuntimeError(f"Required path does not exist: {path}")
    return python, working_dir


def _bounded_tail(buffer: bytearray, chunk: bytes, limit: int) -> None:
    buffer.extend(chunk)
    if len(buffer) > limit:
        del buffer[:-limit]


async def _terminate_process_group(
    process: asyncio.subprocess.Process, grace_seconds: float
) -> None:
    if process.returncode is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=grace_seconds)
        return
    except asyncio.TimeoutError:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    await process.wait()


async def run_model_process(
    *,
    argv: Sequence[str],
    cwd: str | os.PathLike[str],
    environment: Mapping[str, str] | None,
    stdout_path: str | os.PathLike[str],
    stderr_path: str | os.PathLike[str],
    deadline_seconds: float,
    termination_grace_seconds: float = 10,
    tail_bytes: int = 32768,
) -> ProcessResult:
    """Run a fixed argv without a shell and reliably reap its process group."""
    if not argv or not os.path.isabs(argv[0]):
        raise ValueError("argv[0] must be an absolute executable path")
    if deadline_seconds <= 0:
        raise ValueError("deadline_seconds must be positive")

    stdout_file = Path(stdout_path)
    stderr_file = Path(stderr_path)
    stdout_file.parent.mkdir(parents=True, exist_ok=True)
    stderr_file.parent.mkdir(parents=True, exist_ok=True)
    child_env = os.environ.copy()
    # A service launched from a virtualenv must not leak its import path into
    # either of the model-specific environments.
    child_env.pop("PYTHONHOME", None)
    child_env.pop("PYTHONPATH", None)
    child_env.update(dict(environment or {}))
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=os.fspath(cwd),
        env=child_env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    stdout_tail = bytearray()
    stderr_tail = bytearray()

    async def consume(stream, target: Path, tail: bytearray):
        with target.open("ab") as handle:
            while True:
                chunk = await stream.read(65536)
                if not chunk:
                    break
                handle.write(chunk)
                handle.flush()
                _bounded_tail(tail, chunk, tail_bytes)

    consumers = [
        asyncio.create_task(consume(process.stdout, stdout_file, stdout_tail)),
        asyncio.create_task(consume(process.stderr, stderr_file, stderr_tail)),
    ]
    timed_out = False
    try:
        await asyncio.wait_for(process.wait(), timeout=deadline_seconds)
    except asyncio.TimeoutError:
        timed_out = True
        await _terminate_process_group(process, termination_grace_seconds)
    except asyncio.CancelledError:
        await _terminate_process_group(process, termination_grace_seconds)
        raise
    finally:
        await asyncio.gather(*consumers, return_exceptions=True)

    return ProcessResult(
        argv=list(argv),
        returncode=process.returncode
        if process.returncode is not None
        else -signal.SIGKILL,
        timed_out=timed_out,
        stdout_tail=stdout_tail.decode("utf-8", errors="replace"),
        stderr_tail=stderr_tail.decode("utf-8", errors="replace"),
    )

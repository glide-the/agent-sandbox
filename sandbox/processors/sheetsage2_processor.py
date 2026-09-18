"""SheetSage2 transcription command adapter."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sandbox.common.registry import registry
from sandbox.processors.base_processor import BaseProcessor
from sandbox.processors.music_artifacts import publish_music_result
from sandbox.processors.music_runtime import preflight, run_model_process
from sandbox.server.model.music import SheetSage2Submission


@registry.register_processor("sheetsage2_processor")
class SheetSage2Processor(BaseProcessor):
    def __init__(
        self,
        *,
        cwd: str,
        environment: str,
        task_root: str,
        model_path: str,
        base_model_path: str,
        offline: bool = True,
        device: str = "cuda",
        dtype: str = "bf16",
        preset: str = "default",
        threads: int = 4,
        timeout_seconds: float = 7200,
    ):
        super().__init__()
        self.cwd = cwd
        self.environment = environment
        self.task_root = task_root
        self.model_path = model_path
        self.base_model_path = base_model_path
        self.offline = bool(offline)
        self.device = device
        self.dtype = dtype
        self.preset = preset
        self.threads = int(threads)
        self.timeout_seconds = float(timeout_seconds)

    @classmethod
    def from_config(cls, cfg=None):
        return cls(
            cwd=cfg.get("cwd"),
            environment=cfg.get("environment"),
            task_root=cfg.get("task_root", "/root/agent-sandbox-data/tasks"),
            model_path=cfg.get("model_path"),
            base_model_path=cfg.get("base_model_path"),
            offline=cfg.get("offline", True),
            device=cfg.get("device", "cuda"),
            dtype=cfg.get("dtype", "bf16"),
            preset=cfg.get("preset", "default"),
            threads=cfg.get("threads", 4),
            timeout_seconds=cfg.get("timeout_seconds", 7200),
        )

    @classmethod
    def match(cls, data):
        return getattr(data, "operation", None) == "transcribe"

    def init_paths(self, code_input, task_id: str) -> dict[str, str]:
        task_dir = (Path(self.task_root) / task_id).resolve()
        task_dir.mkdir(parents=True, exist_ok=True)
        for name in ("input", "work", "logs", "artifacts"):
            (task_dir / name).mkdir(exist_ok=True)
        return {
            "task_dir": os.fspath(task_dir),
            "native_dir": os.fspath(task_dir / "work" / "native"),
            "stdout_path": os.fspath(task_dir / "logs" / "stdout.log"),
            "stderr_path": os.fspath(task_dir / "logs" / "stderr.log"),
        }

    async def __call__(
        self,
        submission: SheetSage2Submission,
        task_id: str,
        resources: dict[str, str],
    ) -> dict[str, Any]:
        paths = self.init_paths(submission.code_input, task_id)
        python, cwd = preflight(
            environment=self.environment,
            cwd=self.cwd,
            required_paths=[self.model_path, self.base_model_path],
        )
        options = submission.transcription
        argv = [
            os.fspath(python),
            "-u",
            os.fspath(cwd / "scripts" / "transcribe.py"),
            resources["audio_asset"],
            "--output",
            paths["native_dir"],
            "--task",
            options.task,
            "--model",
            self.model_path,
            "--base-model",
            self.base_model_path,
            "--device",
            self.device,
            "--dtype",
            self.dtype,
            "--preset",
            self.preset,
            "--threads",
            str(self.threads),
        ]
        if self.offline:
            argv.append("--offline")
        if options.max_seconds is not None:
            argv.extend(["--max-seconds", str(options.max_seconds)])
        child_env = {
            "VIRTUAL_ENV": self.environment,
            "PATH": f"{Path(self.environment) / 'bin'}:{os.environ.get('PATH', '')}",
            "PYTHONNOUSERSITE": "1",
            "PYTHONUNBUFFERED": "1",
            "HF_HOME": "/root/checkpoint/.hf",
            "HF_HUB_CACHE": "/root/checkpoint/.hf/hub",
            "HF_MODULES_CACHE": "/root/checkpoint/.hf/modules",
        }
        if self.offline:
            child_env.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
        process_result = await run_model_process(
            argv=argv,
            cwd=cwd,
            environment=child_env,
            stdout_path=paths["stdout_path"],
            stderr_path=paths["stderr_path"],
            deadline_seconds=self.timeout_seconds,
        )
        return publish_music_result(
            task_id=task_id,
            task_dir=paths["task_dir"],
            native_dir=paths["native_dir"],
            operation="transcribe",
            process_result=process_result,
            runtime={"processor": "sheetsage2", "python": os.fspath(python)},
        )

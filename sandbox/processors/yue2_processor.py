"""YuE2 command adapter. Model code always runs in its configured environment."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from sandbox.common.registry import registry
from sandbox.processors.base_processor import BaseProcessor
from sandbox.processors.music_artifacts import publish_music_result
from sandbox.processors.music_runtime import preflight, run_model_process
from sandbox.server.model.music import YuE2Submission


@registry.register_processor("yue2_processor")
class YuE2Processor(BaseProcessor):
    def __init__(
        self,
        *,
        cwd: str,
        environment: str,
        task_root: str,
        model_path: str,
        vae_path: str,
        offline: bool = True,
        device: str = "cuda",
        memory_budget_gib: float = 24,
        timeout_seconds: float = 7200,
    ):
        super().__init__()
        self.cwd = cwd
        self.environment = environment
        self.task_root = task_root
        self.model_path = model_path
        self.vae_path = vae_path
        self.offline = bool(offline)
        self.device = device
        self.memory_budget_gib = float(memory_budget_gib)
        self.timeout_seconds = float(timeout_seconds)

    @classmethod
    def from_config(cls, cfg=None):
        return cls(
            cwd=cfg.get("cwd"),
            environment=cfg.get("environment"),
            task_root=cfg.get("task_root", "/root/agent-sandbox-data/tasks"),
            model_path=cfg.get("model_path"),
            vae_path=cfg.get("vae_path"),
            offline=cfg.get("offline", True),
            device=cfg.get("device", "cuda"),
            memory_budget_gib=cfg.get("memory_budget_gib", 24),
            timeout_seconds=cfg.get("timeout_seconds", 7200),
        )

    @classmethod
    def match(cls, data):
        operation = getattr(data, "operation", None)
        return operation in {"generate", "plan", "all_modes", "decode", "score_check"}

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

    def _common_model_args(self) -> list[str]:
        result = ["--model", self.model_path, "--vae", self.vae_path]
        if self.offline:
            result.append("--offline")
        result.extend(
            [
                "--device",
                self.device,
                "--memory-budget-gib",
                str(self.memory_budget_gib),
            ]
        )
        return result

    async def __call__(
        self,
        submission: YuE2Submission,
        task_id: str,
        resources: dict[str, str],
    ) -> dict[str, Any]:
        paths = self.init_paths(submission.code_input, task_id)
        python, cwd = preflight(
            environment=self.environment,
            cwd=self.cwd,
            required_paths=[self.model_path, self.vae_path],
        )
        task_dir = Path(paths["task_dir"])
        request_path = task_dir / "input" / "request.execution.json"
        original_path = task_dir / "input" / "request.original.json"
        if submission.request is not None:
            request_data = submission.request.model_dump(
                exclude={"tags"}, exclude_none=True
            )
            original_path.write_text(
                json.dumps(request_data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            request_path.write_text(
                json.dumps(request_data, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        scripts = cwd / "scripts"
        operation = submission.operation
        if operation == "score_check":
            action = submission.check.action
            native_dir = Path(paths["native_dir"])
            native_dir.mkdir(parents=False, exist_ok=False)
            output_name = {
                "inspect": "inspection.json",
                "strip_chords": "score.abc",
                "compare": "compare.json",
            }[action]
            cli_action = "strip-chords" if action == "strip_chords" else action
            argv = [
                os.fspath(python),
                "-u",
                os.fspath(scripts / "abc_tools.py"),
                cli_action,
                resources["score_source"],
            ]
            if action == "strip_chords":
                argv.append(os.fspath(native_dir / output_name))
                argv.extend(["--keep-voice", submission.check.voices])
            elif action == "compare":
                argv.append(resources["score_after"])
                argv.extend(["--voices", submission.check.voices])
                if submission.check.allow_tempo_change:
                    argv.append("--allow-tempo-change")
                argv.extend(["--output", os.fspath(native_dir / output_name)])
            else:
                argv.extend(["--output", os.fspath(native_dir / output_name)])
        else:
            command = "all-modes" if operation == "all_modes" else operation
            argv = [
                os.fspath(python),
                "-u",
                os.fspath(scripts / "run_yue2.py"),
                command,
            ]
            if operation == "decode":
                argv.extend(["--source", resources["source_task"]])
            else:
                argv.extend(["--request", os.fspath(request_path)])
                if "abc_source" in resources:
                    argv.extend(["--abc-file", resources["abc_source"]])
            argv.extend(["--output", paths["native_dir"], *self._common_model_args()])

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
            task_dir=task_dir,
            native_dir=paths["native_dir"],
            operation=operation,
            process_result=process_result,
            runtime={"processor": "yue2", "python": os.fspath(python)},
        )

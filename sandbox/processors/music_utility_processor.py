"""Adapters for the model-free YuE2 score and listening helper scripts."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import Any

from sandbox.common.registry import registry
from sandbox.processors.base_processor import BaseProcessor
from sandbox.processors.music_artifacts import publish_music_result
from sandbox.processors.music_runtime import preflight, run_model_process
from sandbox.server.model.music import MusicListenSubmission, MusicScoreSubmission


class _MusicUtilityProcessor(BaseProcessor):
    def __init__(
        self,
        *,
        cwd: str,
        environment: str,
        task_root: str,
        timeout_seconds: float = 300,
    ):
        super().__init__()
        self.cwd = cwd
        self.environment = environment
        self.task_root = task_root
        self.timeout_seconds = float(timeout_seconds)

    @classmethod
    def from_config(cls, cfg=None):
        return cls(
            cwd=cfg.get("cwd"),
            environment=cfg.get("environment"),
            task_root=cfg.get("task_root", "/root/agent-sandbox-data/tasks"),
            timeout_seconds=cfg.get("timeout_seconds", 300),
        )

    def init_paths(self, task_id: str) -> dict[str, str]:
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

    def runtime(self) -> tuple[Path, Path, dict[str, str]]:
        python, cwd = preflight(environment=self.environment, cwd=self.cwd)
        environment = {
            "VIRTUAL_ENV": self.environment,
            "PATH": f"{Path(self.environment) / 'bin'}:{os.environ.get('PATH', '')}",
            "PYTHONNOUSERSITE": "1",
            "PYTHONUNBUFFERED": "1",
        }
        return python, cwd, environment


@registry.register_processor("music_score_processor")
class MusicScoreProcessor(_MusicUtilityProcessor):
    @classmethod
    def match(cls, data):
        return getattr(data, "operation", None) == "score_check"

    async def __call__(
        self,
        submission: MusicScoreSubmission,
        task_id: str,
        resources: dict[str, str],
    ) -> dict[str, Any]:
        paths = self.init_paths(task_id)
        python, cwd, child_env = self.runtime()
        native_dir = Path(paths["native_dir"])
        native_dir.mkdir(parents=False, exist_ok=False)
        action = submission.check.action
        output_name = {
            "inspect": "inspection.json",
            "strip_chords": "score.abc",
            "compare": "compare.json",
        }[action]
        cli_action = "strip-chords" if action == "strip_chords" else action
        argv = [
            os.fspath(python),
            "-u",
            os.fspath(cwd / "scripts" / "abc_tools.py"),
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
        result = await run_model_process(
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
            operation="score_check",
            process_result=result,
            runtime={"processor": "music_score", "python": os.fspath(python)},
        )


@registry.register_processor("music_listen_processor")
class MusicListenProcessor(_MusicUtilityProcessor):
    @classmethod
    def match(cls, data):
        return getattr(data, "operation", None) == "listen"

    async def __call__(
        self,
        submission: MusicListenSubmission,
        task_id: str,
        resources: dict[str, list[str]],
    ) -> dict[str, Any]:
        paths = self.init_paths(task_id)
        python, cwd, child_env = self.runtime()
        argv = [
            os.fspath(python),
            "-u",
            os.fspath(cwd / "scripts" / "listen.py"),
            *resources["source_tasks"],
            "--output",
            paths["native_dir"],
        ]
        result = await run_model_process(
            argv=argv,
            cwd=cwd,
            environment=child_env,
            stdout_path=paths["stdout_path"],
            stderr_path=paths["stderr_path"],
            deadline_seconds=self.timeout_seconds,
        )
        native_dir = Path(paths["native_dir"])
        if native_dir.is_dir():
            archive = Path(paths["task_dir"]) / "work" / "comparison.zip"
            with zipfile.ZipFile(
                archive, mode="w", compression=zipfile.ZIP_DEFLATED
            ) as bundle:
                for path in sorted(native_dir.rglob("*")):
                    if path.is_file() and not path.is_symlink():
                        bundle.write(path, path.relative_to(native_dir))
            archive.replace(native_dir / archive.name)
        return publish_music_result(
            task_id=task_id,
            task_dir=paths["task_dir"],
            native_dir=paths["native_dir"],
            operation="listen",
            process_result=result,
            runtime={"processor": "music_listen", "python": os.fspath(python)},
        )

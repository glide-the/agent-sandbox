import asyncio
import sys
from pathlib import Path

from sandbox.processors.music_artifacts import publish_music_result
from sandbox.processors.music_runtime import ProcessResult, run_model_process


def test_subprocess_captures_both_streams_without_shell(tmp_path):
    result = asyncio.run(
        run_model_process(
            argv=[
                sys.executable,
                "-c",
                "import sys; print('你好'); print('error', file=sys.stderr)",
            ],
            cwd=tmp_path,
            environment={"PYTHONPATH": "ignored"},
            stdout_path=tmp_path / "stdout.log",
            stderr_path=tmp_path / "stderr.log",
            deadline_seconds=5,
        )
    )
    assert result.returncode == 0
    assert "你好" in result.stdout_tail and "error" in result.stderr_tail


def test_publish_has_manifest_names_hashes_and_internal_paths(tmp_path):
    task_dir = tmp_path / "music_task"
    native = task_dir / "work" / "native"
    native.mkdir(parents=True)
    (task_dir / "input").mkdir()
    (task_dir / "input" / "request.execution.json").write_text("{}")
    (native / "audio.flac").write_bytes(b"fake-flac")
    (native / "run.json").write_text('{"complete": true}')
    result = publish_music_result(
        task_id="music_task",
        task_dir=task_dir,
        native_dir=native,
        operation="generate",
        process_result=ProcessResult([], 0, False, "", ""),
        runtime={"processor": "fake"},
    )
    assert result["stage"] == "ready"
    assert {item["result_source_name"] for item in result["artifacts"]} == {
        "audio",
        "report",
        "request",
    }
    assert Path(result["audio"]).read_bytes() == b"fake-flac"
    assert all(len(item["sha256"]) == 64 for item in result["artifacts"])


def test_native_incomplete_is_needs_review(tmp_path):
    task_dir = tmp_path / "task"
    native = task_dir / "work" / "native"
    native.mkdir(parents=True)
    (native / "audio.flac").write_bytes(b"audio")
    (native / "run.json").write_text('{"complete": false, "truncated": true}')
    result = publish_music_result(
        task_id="task",
        task_dir=task_dir,
        native_dir=native,
        operation="generate",
        process_result=ProcessResult([], 0, False, "", ""),
        runtime={},
    )
    assert result["outcome"] == "needs_review"
    assert result["delivery_status"] == "ready"


def test_all_modes_partial_is_not_reported_complete(tmp_path):
    task_dir = tmp_path / "task"
    native = task_dir / "work" / "native"
    (native / "full").mkdir(parents=True)
    (native / "off").mkdir()
    (native / "full" / "audio.flac").write_bytes(b"full")
    (native / "off" / "audio.flac").write_bytes(b"off")
    (native / "run.json").write_text(
        '{"results": ['
        '{"mode":"full","status":"complete"},'
        '{"mode":"melody","status":"failed"},'
        '{"mode":"off","status":"complete"}]}'
    )
    result = publish_music_result(
        task_id="task",
        task_dir=task_dir,
        native_dir=native,
        operation="all_modes",
        process_result=ProcessResult([], 1, False, "", ""),
        runtime={},
    )
    assert result["outcome"] == "partial"
    assert result["delivery_status"] == "ready"

"""Shared lifecycle helper for independently bound music tasks."""

from __future__ import annotations


async def save_music_result(task, runner, result: dict) -> None:
    await task.report_progress(
        task_id=runner.task_id,
        runner_stat="save_music_result",
        state="save_write",
        finished=False,
        result=result,
    )
    if result.get("delivery_status") == "failed" or result.get("outcome") in {
        "failed",
        "partial",
    }:
        raise RuntimeError("music task completed with a non-success terminal outcome")

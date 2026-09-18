"""Verification and publication of music task artifacts."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

from sandbox.processors.music_runtime import ProcessResult

PUBLIC_NAMES = {
    "audio.flac": "audio",
    "audio.wav": "audio",
    "score.abc": "score",
    "score.mid": "midi",
    "score.midi": "midi",
    "request.execution.json": "request",
    "input.json": "request",
    "request.json": "request",
    "result.json": "report",
    "run.json": "report",
    "abc_check.json": "report",
    "failure.json": "report",
    "transcription_manifest.json": "report",
    "model_provenance.json": "report",
    "provenance.json": "report",
    "invocation.json": "report",
    "inspection.json": "report",
    "compare.json": "report",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _media_type(path: Path) -> str:
    overrides = {
        ".flac": "audio/flac",
        ".abc": "text/vnd.abc",
        ".mid": "audio/midi",
        ".midi": "audio/midi",
    }
    return (
        overrides.get(path.suffix.lower())
        or mimetypes.guess_type(path.name)[0]
        or "application/octet-stream"
    )


def collect_music_artifacts(
    task_id: str, task_dir: Path, published_dir: Path
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    name_counts: dict[str, int] = {}
    candidates = list(published_dir.rglob("*"))
    request_path = task_dir / "input" / "request.execution.json"
    if request_path.is_file():
        candidates.append(request_path)
    for path in sorted(candidates):
        if not path.is_file() or path.is_symlink():
            continue
        base_name = PUBLIC_NAMES.get(path.name)
        if base_name is None:
            continue
        name_counts[base_name] = name_counts.get(base_name, 0) + 1
        result_source_name = base_name
        if name_counts[base_name] > 1:
            result_source_name = f"{base_name}-{name_counts[base_name]}"
        relative_path = path.relative_to(task_dir).as_posix()
        records.append(
            {
                "result_source_name": result_source_name,
                "filename": path.name,
                "media_type": _media_type(path),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "relative_path": relative_path,
            }
        )
    return records


def verify_native_result(
    operation: str,
    published_dir: Path,
    process_result: ProcessResult,
) -> tuple[str, dict[str, str] | None]:
    public_files = [
        p for p in published_dir.rglob("*") if p.is_file() and p.name in PUBLIC_NAMES
    ]
    if process_result.timed_out:
        return "failed", {
            "kind": "timeout",
            "message": "model process exceeded its deadline",
        }
    if process_result.returncode == 2 or process_result.returncode < 0:
        return "failed", {
            "kind": "model_process",
            "message": f"model process exited with code {process_result.returncode}",
        }
    if not public_files:
        return "failed", {
            "kind": "missing_output",
            "message": "model process produced no deliverable artifacts",
        }
    if process_result.returncode not in {0, 1}:
        return "failed", {
            "kind": "model_process",
            "message": (
                f"unexpected model process exit code {process_result.returncode}"
            ),
        }
    run_manifest = published_dir / "run.json"
    if run_manifest.is_file():
        try:
            native_state = json.loads(run_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "failed", {
                "kind": "invalid_manifest",
                "message": "native run.json is not valid JSON",
            }
        results = native_state.get("results")
        if isinstance(results, list) and results:
            statuses = [item.get("status") for item in results]
            successful = sum(
                value in {"complete", "needs_review"} for value in statuses
            )
            if successful == 0:
                return "failed", {
                    "kind": "all_modes_failed",
                    "message": "all requested modes failed",
                }
            if operation == "all_modes" and any(
                value != "complete" for value in statuses
            ):
                return "partial", {
                    "kind": "partial_modes",
                    "message": "one or more modes failed or require review",
                }
            if any(value == "needs_review" for value in statuses):
                return "needs_review", {
                    "kind": "native_review",
                    "message": "native helper marked the result for review",
                }
        truncated = native_state.get("truncated")
        if (isinstance(truncated, dict) and any(truncated.values())) or (
            native_state.get("complete") is False
        ):
            return "needs_review", {
                "kind": "incomplete_native_result",
                "message": "native helper marked the result incomplete or truncated",
            }
        abc_check = native_state.get("abc_check")
        if isinstance(abc_check, dict) and abc_check.get("ok") is False:
            return "needs_review", {
                "kind": "abc_check",
                "message": "native ABC validation requires review",
            }
    if process_result.returncode == 1:
        return "needs_review", {
            "kind": "partial_output",
            "message": (
                "model process produced reviewable output with a non-zero status"
            ),
        }
    if operation in {"generate", "decode", "all_modes"} and not any(
        p.suffix.lower() in {".flac", ".wav", ".mp3"} for p in public_files
    ):
        return "failed", {"kind": "missing_audio", "message": "audio output is missing"}
    if operation == "transcribe" and not any(
        p.suffix.lower() == ".abc" for p in public_files
    ):
        return "needs_review", {
            "kind": "missing_score",
            "message": "transcription score is missing",
        }
    if operation == "transcribe":
        score = next(p for p in public_files if p.suffix.lower() == ".abc")
        text = score.read_text(encoding="utf-8", errors="replace")
        if "X:" not in text or "K:" not in text:
            return "needs_review", {
                "kind": "invalid_score",
                "message": "transcription ABC is missing required headers",
            }
    return "complete", None


def publish_music_result(
    *,
    task_id: str,
    task_dir: str | os.PathLike[str],
    native_dir: str | os.PathLike[str],
    operation: str,
    process_result: ProcessResult,
    runtime: dict[str, Any],
) -> dict[str, Any]:
    root = Path(task_dir).resolve(strict=True)
    source = Path(native_dir).resolve(strict=True)
    if root not in source.parents:
        raise RuntimeError("native output escaped the task directory")
    destination = root / "artifacts" / "native"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RuntimeError("published native directory already exists")
    os.replace(source, destination)

    outcome, error = verify_native_result(operation, destination, process_result)
    artifacts = collect_music_artifacts(task_id, root, destination)
    delivery_status = "ready" if outcome != "failed" else "failed"
    result = {
        "stage": "ready" if delivery_status == "ready" else "publishing_failed",
        "outcome": outcome,
        "model_completed": not process_result.timed_out and bool(artifacts),
        "delivery_status": delivery_status,
        "artifacts": artifacts,
        "runtime": {
            **runtime,
            "returncode": process_result.returncode,
            "timed_out": process_result.timed_out,
        },
        "error": error,
    }
    # The existing result_source endpoint expects a result key containing the
    # backing path.  These internal keys are removed from the public projection.
    for artifact in artifacts:
        result[artifact["result_source_name"]] = os.fspath(
            root / artifact["relative_path"]
        )
    manifest = root / "result-manifest.json"
    temporary = manifest.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary, manifest)
    return result

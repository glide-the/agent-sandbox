"""Single-use, short-lived upload capabilities for remote MCP clients."""

from __future__ import annotations

import mimetypes
import os
import secrets
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlparse

from fastapi import HTTPException, Request, UploadFile, status

from sandbox.server.runner_service import upload_input


@dataclass(frozen=True)
class UploadCapability:
    principal: str
    filename: str
    media_type: str
    expires_at: float


class UploadCapabilityStore:
    def __init__(
        self,
        *,
        public_base_url: str,
        path_template: str = "/api/uploads/{token}",
        ttl_seconds: int = 300,
        max_input_bytes: int = 268435456,
        clock=time.time,
    ):
        parsed = urlparse(public_base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("mcp.public_base_url must be a trusted HTTP(S) origin")
        if path_template.count("{token}") != 1 or not path_template.startswith("/"):
            raise ValueError("mcp.upload_capability_path must contain one {token}")
        if ttl_seconds <= 0:
            raise ValueError("mcp.upload_ttl_seconds must be positive")
        self.public_base_url = public_base_url.rstrip("/")
        self.path_template = path_template
        self.ttl_seconds = int(ttl_seconds)
        self.max_input_bytes = int(max_input_bytes)
        self._clock = clock
        self._records: dict[str, UploadCapability] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _path_details(file_path: str, client_os: str) -> tuple[str, str]:
        if (
            not file_path
            or "\x00" in file_path
            or "\r" in file_path
            or "\n" in file_path
        ):
            raise ValueError("file_path contains invalid characters")
        if len(file_path) > 4096:
            raise ValueError("file_path is too long")
        if client_os not in {"darwin", "linux", "windows"}:
            raise ValueError("client_os must be darwin, linux, or windows")
        path = (
            PureWindowsPath(file_path)
            if client_os == "windows"
            else PurePosixPath(file_path)
        )
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError("file_path must be an absolute path without traversal")
        filename = path.name
        if filename in {"", ".", ".."}:
            raise ValueError("file_path must identify a file")
        return filename, mimetypes.guess_type(filename)[0] or "application/octet-stream"

    @staticmethod
    def _command(client_os: str, file_path: str, media_type: str, url: str) -> str:
        args = [
            "curl.exe" if client_os == "windows" else "curl",
            "-sS",
            "--fail-with-body",
            "-X",
            "PUT",
            "-H",
            f"Content-Type: {media_type}",
            "--upload-file",
            file_path,
            "--",
            url,
        ]
        if client_os == "windows":
            return subprocess.list2cmdline(args)
        return shlex.join(args)

    def issue(self, *, principal: str, file_path: str, client_os: str) -> dict:
        filename, media_type = self._path_details(file_path, client_os)
        token = secrets.token_urlsafe(32)
        now = self._clock()
        with self._lock:
            self._records = {
                key: value
                for key, value in self._records.items()
                if value.expires_at > now
            }
            self._records[token] = UploadCapability(
                principal=principal,
                filename=filename,
                media_type=media_type,
                expires_at=now + self.ttl_seconds,
            )
        path = self.path_template.replace("{token}", token)
        url = f"{self.public_base_url}{path}"
        return {
            "method": "PUT",
            "upload_url": url,
            "command": self._command(client_os, file_path, media_type, url),
            "filename": filename,
            "media_type": media_type,
            "single_use": True,
            "expires_in_seconds": self.ttl_seconds,
            "bytes_uploaded": False,
        }

    def consume(self, token: str) -> UploadCapability:
        with self._lock:
            capability = self._records.pop(token, None)
        if capability is None or capability.expires_at <= self._clock():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="upload capability is invalid, expired, or already used",
            )
        return capability

    async def receive(self, *, token: str, request: Request):
        capability = self.consume(token)
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="invalid Content-Length",
                ) from exc
            if declared_size > self.max_input_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=(
                        "file exceeds the configured upload limit; "
                        "this single-use URL has been consumed"
                    ),
                )

        temp_dir = Path(tempfile.mkdtemp(prefix="runner-upload-"))
        os.chmod(temp_dir, 0o700)
        temp_path = temp_dir / "payload"
        received = 0
        try:
            with temp_path.open("xb") as handle:
                os.chmod(temp_path, 0o600)
                async for chunk in request.stream():
                    received += len(chunk)
                    if received > self.max_input_bytes:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=(
                                "file exceeds the configured upload limit; "
                                "this single-use URL has been consumed"
                            ),
                        )
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            raw = temp_path.open("rb")
            upload = UploadFile(
                file=raw,
                filename=capability.filename,
                headers={"content-type": capability.media_type},
            )
            return await upload_input(principal=capability.principal, upload=upload)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

"""MCP protocol adapter for the existing Runner business operations."""

from __future__ import annotations

import base64
import contextvars
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode, urlparse

from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, ResourceLink, TextContent, ToolAnnotations
from pydantic import ValidationError
from starlette.responses import JSONResponse

from sandbox.server.model.result import BaseResponse
from sandbox.server.music_auth import MusicAuth
from sandbox.server.runner_service import read_task, read_task_resource, submit_task
from sandbox.server.upload_capability import UploadCapabilityStore

_principal: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "runner_mcp_principal", default=None
)


def _response_dict(response: Any) -> dict:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if isinstance(response, dict):
        return response
    raise TypeError(f"unsupported Runner response: {type(response)!r}")


def _json_text(value: dict) -> TextContent:
    return TextContent(
        type="text", text=json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    )


def _success(value: dict, *extra) -> CallToolResult:
    return CallToolResult(
        content=[_json_text(value), *extra],
        structuredContent=value,
        isError=False,
    )


def _failure(exc: Exception) -> CallToolResult:
    if isinstance(exc, HTTPException):
        code = int(exc.status_code)
        message = str(exc.detail)
    elif isinstance(exc, ValidationError):
        code = 422
        message = str(exc)
    elif isinstance(exc, (ValueError, TypeError)):
        code = 422
        message = str(exc)
    elif isinstance(exc, KeyError):
        code = 404
        message = f"resource not found: {exc}"
    elif isinstance(exc, PermissionError):
        code = 403
        message = str(exc)
    else:
        code = 500
        message = "Runner operation failed"
    value = {"code": code, "msg": message, "data": None}
    return CallToolResult(
        content=[_json_text(value)], structuredContent=value, isError=True
    )


def _authenticated_principal() -> str:
    principal = _principal.get()
    if not principal:
        raise HTTPException(status_code=401, detail="missing authenticated principal")
    return principal


class AuthenticatedMCPApp:
    """Resolve and bind the configured principal for each MCP request."""

    def __init__(self, app, auth: MusicAuth):
        self.app = app
        self.auth = auth

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        try:
            principal = self.auth.authenticate_header(headers.get("authorization"))
        except HTTPException as exc:
            response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
            await response(scope, receive, send)
            return
        marker = _principal.set(principal)
        try:
            await self.app(scope, receive, send)
        finally:
            _principal.reset(marker)


@dataclass
class RunnerMCPIntegration:
    server: FastMCP
    app: Any
    capabilities: UploadCapabilityStore
    mount_path: str


def create_runner_mcp(
    *, config: dict, auth: MusicAuth, max_input_bytes: int
) -> RunnerMCPIntegration:
    public_base_url = str(config["public_base_url"])
    parsed = urlparse(public_base_url)
    mount_path = str(config.get("path", "/mcp"))
    if not mount_path.startswith("/") or mount_path == "/":
        raise ValueError("mcp.path must be a non-root absolute path")
    max_request_bytes = int(config.get("max_request_bytes", 1048576))
    inline_max_bytes = int(config.get("inline_max_bytes", 262144))
    if inline_max_bytes <= 0 or inline_max_bytes > max_request_bytes:
        raise ValueError("mcp.inline_max_bytes must be within max_request_bytes")
    capabilities = UploadCapabilityStore(
        public_base_url=public_base_url,
        path_template=str(config.get("upload_capability_path", "/api/uploads/{token}")),
        ttl_seconds=int(config.get("upload_ttl_seconds", 300)),
        max_input_bytes=max_input_bytes,
    )
    allowed_tools = config.get(
        "tools",
        [
            "runner_upload",
            "runner_submit",
            "runner_result",
            "runner_result_source",
        ],
    )
    expected_tools = {
        "runner_upload",
        "runner_submit",
        "runner_result",
        "runner_result_source",
    }
    if set(allowed_tools) != expected_tools or len(allowed_tools) != 4:
        raise ValueError("mcp.tools must contain exactly the four Runner tools")

    server = FastMCP(
        "agent-sandbox Runner",
        instructions=(
            "Call the existing Runner task service without changing task identity."
        ),
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        max_request_body_size=max_request_bytes,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=bool(
                config.get("dns_rebinding_protection", True)
            ),
            allowed_hosts=[parsed.netloc],
            allowed_origins=[f"{parsed.scheme}://{parsed.netloc}"],
        ),
    )

    @server.tool(
        name="runner_upload",
        description="Sign a single-use URL so the local client can PUT a Runner input.",
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=False, idempotentHint=False
        ),
        structured_output=True,
    )
    async def runner_upload(
        file_path: str, client_os: Literal["darwin", "linux", "windows"]
    ) -> CallToolResult:
        try:
            data = capabilities.issue(
                principal=_authenticated_principal(),
                file_path=file_path,
                client_os=client_os,
            )
            value = {"code": 200, "msg": "上传地址已签发；尚未上传", "data": data}
            return _success(value)
        except Exception as exc:
            return _failure(exc)

    @server.tool(
        name="runner_submit",
        description=(
            "Submit through the same Runner queue and idempotency store as HTTP."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=False, idempotentHint=False
        ),
        structured_output=True,
    )
    async def runner_submit(
        parameter: dict[str, Any],
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> CallToolResult:
        try:
            if idempotency_key is not None and not 1 <= len(idempotency_key) <= 128:
                raise ValueError("idempotency_key must contain 1 to 128 characters")
            response = await submit_task(
                principal=_authenticated_principal(),
                parameter=parameter,
                payload=payload,
                idempotency_key=idempotency_key,
            )
            return _success(_response_dict(response))
        except Exception as exc:
            return _failure(exc)

    @server.tool(
        name="runner_result",
        description="Read one Runner task state without polling or resubmitting it.",
        annotations=ToolAnnotations(
            readOnlyHint=True, destructiveHint=False, idempotentHint=True
        ),
        structured_output=True,
    )
    async def runner_result(task_id: str) -> CallToolResult:
        try:
            response = read_task(principal=_authenticated_principal(), task_id=task_id)
            value = _response_dict(response)
            if isinstance(response, BaseResponse) and value.get("code") != 200:
                return CallToolResult(
                    content=[_json_text(value)],
                    structuredContent=value,
                    isError=True,
                )
            return _success(value)
        except Exception as exc:
            return _failure(exc)

    @server.tool(
        name="runner_result_source",
        description="Read an authorized Runner result inline or return its HTTP link.",
        annotations=ToolAnnotations(
            readOnlyHint=True, destructiveHint=False, idempotentHint=True
        ),
        structured_output=True,
    )
    async def runner_result_source(
        task_id: str,
        result_source_name: str,
        mode: Literal["auto", "inline", "link"] = "auto",
    ) -> CallToolResult:
        try:
            resource = read_task_resource(
                principal=_authenticated_principal(),
                task_id=task_id,
                result_source_name=result_source_name,
            )
            if isinstance(resource, BaseResponse):
                value = _response_dict(resource)
                return CallToolResult(
                    content=[_json_text(value)],
                    structuredContent=value,
                    isError=True,
                )
            size = int(resource["size_bytes"])
            delivery = "inline" if mode == "inline" else mode
            if mode == "auto":
                delivery = "inline" if size <= inline_max_bytes else "link"
            metadata = {
                "task_id": task_id,
                "result_source_name": result_source_name,
                "filename": resource["filename"],
                "media_type": resource.get("media_type") or "application/octet-stream",
                "sha256": resource["sha256"],
                "size_bytes": size,
            }
            if delivery == "inline":
                if size > inline_max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            "result exceeds the configured inline limit; use link mode"
                        ),
                    )
                raw = Path(resource["path"]).read_bytes()
                if len(raw) != size:
                    raise HTTPException(
                        status_code=409,
                        detail="result source changed while it was being read",
                    )
                metadata.update(
                    {
                        "delivery": "inline",
                        "bytes_included": True,
                        "encoding": "base64",
                        "content_base64": base64.b64encode(raw).decode("ascii"),
                    }
                )
                return _success(
                    {"code": 200, "msg": "已返回文件字节的Base64编码", "data": metadata}
                )

            query = urlencode(
                {"task_id": task_id, "result_source_name": result_source_name}
            )
            url = f"{public_base_url.rstrip('/')}/runner/result_source?{query}"
            metadata.update(
                {
                    "delivery": "link",
                    "bytes_included": False,
                    "url": url,
                    "requires_auth": auth.required,
                }
            )
            link = ResourceLink(
                type="resource_link",
                name=resource["filename"],
                uri=url,
                mimeType=metadata["media_type"],
                size=size,
            )
            return _success(
                {
                    "code": 200,
                    "msg": "返回资源链接，尚未传输文件字节",
                    "data": metadata,
                },
                link,
            )
        except Exception as exc:
            return _failure(exc)

    return RunnerMCPIntegration(
        server=server,
        app=AuthenticatedMCPApp(server.streamable_http_app(), auth),
        capabilities=capabilities,
        mount_path=mount_path,
    )

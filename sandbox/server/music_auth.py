"""Request-principal resolution for model task and runner asset routes."""

from __future__ import annotations

import hashlib
import hmac
import json
import stat
from pathlib import Path

from fastapi import HTTPException, Request, status


class MusicAuth:
    def __init__(
        self,
        api_keys_file: str | None,
        required: bool = True,
        anonymous_principal: str = "local",
    ):
        self.api_keys_file = Path(api_keys_file).expanduser() if api_keys_file else None
        self.required = required
        self.anonymous_principal = anonymous_principal.strip()
        if not self.required and not self.anonymous_principal:
            raise ValueError("anonymous principal must not be empty")

    def _principals(self) -> dict[str, str]:
        if self.api_keys_file is None or not self.api_keys_file.is_file():
            if self.required:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="music authentication is not configured",
                )
            return {}
        if stat.S_IMODE(self.api_keys_file.stat().st_mode) & 0o077:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="music authentication file must have mode 0600 or stricter",
            )
        value = json.loads(self.api_keys_file.read_text(encoding="utf-8"))
        if "tokens" in value:
            value = value["tokens"]
        elif "principals" in value:
            value = {
                item["token_sha256"]: item["user_id"] for item in value["principals"]
            }
        if not isinstance(value, dict):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="music authentication configuration is invalid",
            )
        return {str(digest): str(owner) for digest, owner in value.items()}

    def authenticate_header(self, authorization: str | None) -> str:
        if not self.required:
            return self.anonymous_principal
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing bearer token",
            )
        token = authorization.removeprefix("Bearer ").strip()
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        for expected, owner in self._principals().items():
            if hmac.compare_digest(digest, expected):
                return owner
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid bearer token",
        )

    def authenticate_request(self, request: Request) -> str:
        return self.authenticate_header(request.headers.get("Authorization"))


def authorize_music_resource(owner_id: str, principal: str) -> None:
    if not hmac.compare_digest(owner_id, principal):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="resource belongs to another principal",
        )

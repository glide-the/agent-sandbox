"""Durable, owner-bound assets shared by upload and model task dispatch."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status


class RunnerAssetStore:
    def __init__(self, root: str, max_input_bytes: int = 268435456):
        self.root = Path(root).expanduser()
        self.uploads_root = self.root / "uploads"
        self.max_input_bytes = int(max_input_bytes)

    @staticmethod
    def _owner_directory(owner_id: str) -> str:
        return hashlib.sha256(owner_id.encode("utf-8")).hexdigest()

    async def register_uploaded_asset(
        self, *, owner_id: str, upload: UploadFile
    ) -> dict:
        asset_id = "asset_" + uuid.uuid4().hex
        extension = Path(upload.filename or "").suffix.lower()
        if extension and not re.fullmatch(r"\.[a-z0-9]{1,10}", extension):
            extension = ""
        directory = self.uploads_root / self._owner_directory(owner_id) / asset_id
        directory.mkdir(parents=True, exist_ok=False)
        final_path = directory / f"source{extension}"
        temporary = directory / ".uploading"
        digest = hashlib.sha256()
        size = 0
        try:
            with temporary.open("xb") as handle:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > self.max_input_bytes:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="uploaded file exceeds the configured limit",
                        )
                    digest.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, final_path)
            metadata = {
                "asset_id": asset_id,
                "owner_id": owner_id,
                "filename": upload.filename or final_path.name,
                "relative_path": final_path.relative_to(self.root).as_posix(),
                "size_bytes": size,
                "sha256": digest.hexdigest(),
            }
            metadata_temp = directory / ".asset.json.tmp"
            metadata_temp.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(metadata_temp, directory / "asset.json")
            return metadata
        except Exception:
            import shutil

            shutil.rmtree(directory, ignore_errors=True)
            raise
        finally:
            await upload.close()

    def resolve_uploaded_asset(self, *, owner_id: str, asset_id: str) -> Path:
        if not re.fullmatch(r"asset_[0-9a-f]{32}", asset_id):
            raise KeyError(asset_id)
        directory = self.uploads_root / self._owner_directory(owner_id) / asset_id
        metadata_path = directory / "asset.json"
        if not metadata_path.is_file():
            raise KeyError(asset_id)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("owner_id") != owner_id:
            raise PermissionError(asset_id)
        candidate = self.root / metadata["relative_path"]
        if candidate.is_symlink():
            raise PermissionError(asset_id)
        path = candidate.resolve(strict=True)
        if directory.resolve() not in path.parents:
            raise PermissionError(asset_id)
        if path.stat().st_size != metadata["size_bytes"]:
            raise IOError("asset size no longer matches its record")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != metadata["sha256"]:
            raise IOError("asset digest no longer matches its record")
        return path

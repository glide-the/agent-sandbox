import asyncio
import io

import pytest
from starlette.datastructures import UploadFile

from sandbox.server.runner_assets import RunnerAssetStore


def upload(name: str, data: bytes):
    return UploadFile(filename=name, file=io.BytesIO(data))


def test_same_filename_uploads_are_immutable_and_owner_bound(tmp_path):
    store = RunnerAssetStore(str(tmp_path), max_input_bytes=100)
    first = asyncio.run(
        store.register_uploaded_asset(
            owner_id="alice", upload=upload("song.wav", b"first")
        )
    )
    second = asyncio.run(
        store.register_uploaded_asset(
            owner_id="alice", upload=upload("song.wav", b"second")
        )
    )
    assert first["asset_id"] != second["asset_id"]
    assert (
        store.resolve_uploaded_asset(
            owner_id="alice", asset_id=first["asset_id"]
        ).read_bytes()
        == b"first"
    )
    with pytest.raises(KeyError):
        store.resolve_uploaded_asset(owner_id="bob", asset_id=first["asset_id"])


def test_asset_tampering_is_detected(tmp_path):
    store = RunnerAssetStore(str(tmp_path))
    metadata = asyncio.run(
        store.register_uploaded_asset(
            owner_id="alice", upload=upload("score.abc", b"X:1\nK:C\nC")
        )
    )
    path = store.resolve_uploaded_asset(owner_id="alice", asset_id=metadata["asset_id"])
    path.write_bytes(b"Y:2\nK:D\nD")
    with pytest.raises(OSError):
        store.resolve_uploaded_asset(owner_id="alice", asset_id=metadata["asset_id"])


def test_oversized_or_interrupted_upload_leaves_no_asset(tmp_path):
    store = RunnerAssetStore(str(tmp_path), max_input_bytes=3)
    with pytest.raises(Exception):
        asyncio.run(
            store.register_uploaded_asset(
                owner_id="alice", upload=upload("large.wav", b"1234")
            )
        )
    assert not list((tmp_path / "uploads").rglob("asset.json"))

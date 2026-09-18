# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import shutil
import zipfile
from datetime import datetime
from typing import Dict

from fastapi import File, Form, HTTPException, Request, UploadFile, status

from sandbox.server.bootstrap.bootstrap_register import get_bootstrap
from sandbox.server.model.result import TaskRunnerResponse
from sandbox.server.runner_service import upload_input


async def upload_runner_file(
    request: Request,
    file: UploadFile = File(...),
    user_id: str = Form(...),
) -> TaskRunnerResponse:
    """Store one immutable, owner-bound runner input without unpacking it."""
    bootstrap = get_bootstrap("runner_bootstrap_web")
    if bootstrap.asset_store is None or bootstrap.music_auth is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="runner uploads are not configured",
        )
    principal = bootstrap.music_auth.authenticate_request(request)
    if principal != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user_id does not match the authenticated principal",
        )
    return await upload_input(principal=principal, upload=file)


cwd = "/app/sandbox"


async def extract_standard_file(
    file: UploadFile,
    rank_id: str,
    user_id: str,
) -> Dict:
    created_at = f"{rank_id}_{int(datetime.now().timestamp())}"

    file_dir = os.path.join(cwd, "eval", user_id)
    # 先删除文件夹
    shutil.rmtree(file_dir, ignore_errors=True)
    os.makedirs(file_dir, exist_ok=True)
    # 获取 file.filename后辍
    file_extension = os.path.splitext(file.filename)[1].lower()

    file_path = os.path.join(file_dir, created_at + file_extension)
    with open(file_path, "wb") as fp:
        shutil.copyfileobj(file.file, fp)
    file.file.close()

    with zipfile.ZipFile(file_path, "r") as zip_ref:
        zip_ref.extractall(file_dir)
        zip_ref.close()
    eval_file_dir = os.path.join(file_dir, "eval.zip")
    with zipfile.ZipFile(eval_file_dir, "r") as zip_ref:
        zip_ref.extractall(file_dir)
        zip_ref.close()

    return dict(
        id=created_at,
        filename=file.filename,
        bytes=file.size,
        created_at=created_at,
        object="file",
        purpose="standard",
    )


async def extract_submit_file(
    file: UploadFile,
    rank_id: str,
    user_id: str,
) -> Dict:
    """
    提取评分文件到选手提交路径
    :param file:
    :param rank_id:
    :param user_id:
    :return:
    """
    created_at = f"{rank_id}_{int(datetime.now().timestamp())}"

    file_dir = os.path.join(cwd, "eval", user_id, "submit")
    # 先删除文件夹
    shutil.rmtree(file_dir, ignore_errors=True)
    os.makedirs(file_dir, exist_ok=True)
    # 获取 file.filename后辍
    file_extension = os.path.splitext(file.filename)[1].lower()
    file_path = os.path.join(file_dir, created_at + file_extension)
    with open(file_path, "wb") as fp:
        shutil.copyfileobj(file.file, fp)
    file.file.close()

    return dict(
        id=created_at,
        filename=file.filename,
        bytes=file.size,
        created_at=created_at,
        object="file",
        purpose="submit",
    )


async def extract_submit_mm_file(
    file: UploadFile,
    rank_id: str,
    user_id: str,
) -> Dict:
    """
    提取多模态文件到指定路径
    :param file:
    :param rank_id:
    :param user_id:
    :return:
    """
    try:
        created_at = f"{rank_id}_{int(datetime.now().timestamp())}"

        file_dir = os.path.join(cwd, "eval", user_id, "submit")
        # 先删除文件夹
        shutil.rmtree(file_dir, ignore_errors=True)
        os.makedirs(file_dir, exist_ok=True)
        # 获取 file.filename后辍
        file_extension = os.path.splitext(file.filename)[1].lower()

        file_path = os.path.join(file_dir, created_at + file_extension)
        with open(file_path, "wb") as fp:
            shutil.copyfileobj(file.file, fp)
        file.file.close()

        with zipfile.ZipFile(file_path, "r") as zip_ref:
            zip_ref.extractall(file_dir)
            zip_ref.close()

        # 定义需要检查的文件和文件夹路径
        submit_file = os.path.join(file_dir, "submit_mm.jsonl")
        imgs_dir = os.path.join(file_dir, "imgs")

        # 检查 submit_mm.jsonl 是否存在
        if not os.path.isfile(submit_file):
            raise ValueError("文件 submit_mm.jsonl 不存在。")

        # 检查 imgs 文件夹是否存在
        if not os.path.isdir(imgs_dir):
            raise ValueError("文件夹imgs不存在。")

        return dict(
            id=created_at,
            submit_file="submit_mm.jsonl",
            imgs_dir="imgs",
            filename=file.filename,
            bytes=file.size,
            created_at=created_at,
            object="file",
            purpose="submit",
        )
    except Exception as e:
        return dict(error=str(e))

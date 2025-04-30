import logging
import threading

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import HTMLResponse

from sandbox.common.registry import registry
from sandbox.server.bootstrap.base import Bootstrap
from sandbox.server.bootstrap.bootstrap_register import bootstrap_register
from sandbox.server.model.result import BaseResponse
from sandbox.server.servlet.document import document, page_index
from sandbox.server.servlet.extract_file import (
    extract_standard_file,
    extract_submit_file, extract_submit_mm_file,
)
from sandbox.server.servlet.logger_info import adjust_logging
from sandbox.server.servlet.runner import (
    get_task_async,
    post_task_update_async,
    result_async,
    result_source_async,
    submit_async, get_bootstrap_info,
)
from sandbox.server.utils import MakeFastAPIOffline
# 全局标识，标记 middleware 是否已执行过一次
logging_adjusted = False

@bootstrap_register.register_bootstrap("runner_bootstrap_web")
class RunnerBootstrapBaseWeb(Bootstrap):
    """
    Bootstrap Server Lifecycle
    """
    app: FastAPI
    server_thread: threading

    def __init__(self, host: str, port: int, max_ongoing_tasks: int | None = None):
        super().__init__()

        self.host = host
        self.port = port
        if max_ongoing_tasks:
            self._MAX_ONGOING_TASKS = max_ongoing_tasks

    @classmethod
    def from_config(cls, cfg=None):
        host = cfg.get("host")
        port = cfg.get("port")
        max_ongoing_tasks = cfg.get("max_ongoing_tasks", None)
        return cls(host=host, port=port, max_ongoing_tasks=max_ongoing_tasks)

    async def run(self):
        self.app = FastAPI(
            title="API Server",
            version=self.version
        )
        MakeFastAPIOffline(self.app)
        self.app.mount("/static",
                       StaticFiles(directory=f"{registry.get_path('server_library_root')}/static/static"),
                       name="static")
        # Add CORS middleware to allow all origins
        # 在config.py中设置OPEN_DOMAIN=True，允许跨域
        # set OPEN_DOMAIN=True in config.py to allow cross-domain
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        self.app.get("/",
                     response_model=BaseResponse,
                     summary="演示首页")(page_index)
        self.app.get("/docs",
                     response_model=BaseResponse,
                     summary="swagger 文档")(document)
        self.app.post("/runner/submit",
                      tags=["Runner"],
                      summary="提交调度Runner")(submit_async)
        self.app.get("/runner/task-internal",
                     tags=["Runner"],
                     summary="内部获取调度Runner")(get_task_async)
        self.app.get("/runner/get_bootstrap_info",
                     tags=["Runner"],
                     summary="内部获取调度任务Runner信息")(get_bootstrap_info)
        self.app.post("/runner/task-update-internal",
                      tags=["Runner"],
                      summary="内部同步调度RunnerStat")(post_task_update_async)
        self.app.get("/runner/result_source",
                     tags=["Runner"],
                     summary="获取任务资源结果")(result_source_async)
        self.app.get("/runner/result",
                     tags=["Runner"],
                     summary="获取任务结果")(result_async)

        self.app.post("/extract_standard_file",
                      tags=["ExtractFile"],
                      summary="extract_standard_file")(extract_standard_file)

        self.app.post("/extract_submit_file",
                      tags=["ExtractFile"],
                      summary="extract_submit_file")(extract_submit_file)

        self.app.post("/extract_submit_mm_file",
                      tags=["ExtractFile"],
                      summary="extract_submit_mm_file")(extract_submit_mm_file)

        self.app.post("/logging/adjust",
                      tags=["logging"],
                      summary="更新日志级别")(adjust_logging)
        app = self.app

        # 中间件函数，用于设置特定路径的日志级别
        async def set_logging_level(request: Request, call_next):
            global logging_adjusted
            if not logging_adjusted:
                # 获取请求路径
                path = request.url.path

                # 如果是指定路径，则设置日志级别为 WARNING
                if path.startswith("/runner/task-internal"):
                    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
                else:
                    # 其他路径则保持默认级别
                    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
                logging_adjusted = True
            return await call_next(request)

        # 将中间件添加到应用中
        app.middleware("http")(set_logging_level)

        def run_server():
            uvicorn.run(app, host=self.host, port=self.port)

        self.server_thread = threading.Thread(target=run_server)
        self.server_thread.start()

    async def destroy(self):
        server_thread = self.server_thread
        app = self.app

        @app.on_event("shutdown")
        def shutdown_event():
            server_thread.join()  # 等待服务器线程结束

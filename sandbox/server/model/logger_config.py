
from pydantic import BaseModel, Field


# 定义请求体数据模型
class LogConfig(BaseModel):
    logger_name: str  # 日志名称，例如 "urllib3"
    level: str        # 新的日志级别，例如 "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
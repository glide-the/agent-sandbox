from fastapi import FastAPI, HTTPException

from sandbox.server.model.logger_config import LogConfig
import logging


async def adjust_logging(config: LogConfig):
    # 验证日志级别是否合法
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    new_level = config.level.upper()
    if new_level not in valid_levels:
        raise HTTPException(status_code=400, detail="Invalid logging level provided.")

    # 获取指定 logger 并动态修改日志级别
    logger = logging.getLogger(config.logger_name)
    logger.setLevel(new_level)

    return {"message": f"Logger '{config.logger_name}' level set to {new_level}"}


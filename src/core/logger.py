"""日志配置模块"""
import sys
from pathlib import Path
from loguru import logger


def setup_logger(log_level: str = "INFO", log_file: str = "logs/app.log"):
    """
    配置loguru日志器

    Args:
        log_level: 日志级别
        log_file: 日志文件路径
    """
    # 移除默认handler
    logger.remove()

    # 添加控制台输出
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=log_level,
        colorize=True,
    )

    # 添加文件输出
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=log_level,
        rotation="10 MB",
        retention="30 days",
        compression="zip",
    )

    return logger


def get_logger(name: str):
    """获取logger实例"""
    return logger.bind(name=name)

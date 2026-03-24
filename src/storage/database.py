"""数据库基础设施。

提供 SQLAlchemy engine、SessionLocal、Base 以及初始化入口。
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as SQLAlchemySession
from sqlalchemy.orm import close_all_sessions, declarative_base, sessionmaker

from src.core.config import config_loader
from src.core.logger import get_logger

logger = get_logger(__name__)


def get_database_url() -> str:
    """获取当前应使用的数据库 URL。

    测试环境可通过环境变量 ETF_AI_TEST_DB 注入临时数据库，避免误写业务库。
    """
    return os.getenv("ETF_AI_TEST_DB") or config_loader.load_settings().database_url


def _ensure_sqlite_directory(database_url: str) -> None:
    """在 SQLite 文件路径场景下创建父目录。"""
    if database_url.startswith("sqlite:///"):
        db_path = Path(database_url.replace("sqlite:///", "", 1))
        db_path.parent.mkdir(parents=True, exist_ok=True)


DATABASE_URL: str | None = None
engine: Engine | None = None


class _RoutingSession(SQLAlchemySession):
    """将 Session 的实际 bind 路由到当前全局 engine。

    目的：reset_engine() 后，即使旧 Session 实例被误用，也不会继续写旧库。
    """

    def get_bind(self, mapper=None, clause=None, bind=None, **kw):  # type: ignore[override]
        if bind is not None:
            return bind
        if engine is None:
            # 按现有行为约定：应先 init_db()/reset_engine() 再使用 Session。
            raise RuntimeError("Database engine is not initialized; call init_db() first.")
        return engine


# 注意：不要在导入时绑定 engine，避免 pytest 收集阶段意外触及默认业务库。
SessionLocal = sessionmaker(
    class_=_RoutingSession,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

Base = declarative_base()


def reset_engine(database_url: str | None = None) -> None:
    """重建 engine 并将 SessionLocal 绑定到新的数据库。

    - 默认使用 get_database_url() 的结果
    - 允许测试通过调用 reset_engine(...) 或设置 ETF_AI_TEST_DB 来隔离数据库
    """
    global DATABASE_URL, engine

    # 先关闭已存在的 Session，避免持有旧连接/事务继续写入旧库。
    close_all_sessions()

    resolved_url = database_url or get_database_url()
    _ensure_sqlite_directory(resolved_url)

    old_engine = engine
    new_engine = create_engine(
        resolved_url,
        future=True,
        echo=False,
    )
    SessionLocal.configure(bind=new_engine)

    DATABASE_URL = resolved_url
    engine = new_engine

    if old_engine is not None and old_engine is not new_engine:
        old_engine.dispose()


def init_db() -> None:
    """创建所有已声明的数据表。"""
    from src.storage import models  # noqa: F401

    if engine is None:
        reset_engine()

    Base.metadata.create_all(bind=engine)
    logger.info(f"Database initialized: {DATABASE_URL}")

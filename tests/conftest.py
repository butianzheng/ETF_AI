import os

import pytest
from sqlalchemy.orm import close_all_sessions


@pytest.fixture(scope="session", autouse=True)
def _use_temp_sqlite_database(tmp_path_factory) -> None:
    """在整个测试 session 期间使用临时 SQLite，避免误写默认业务库。"""
    db_dir = tmp_path_factory.mktemp("etf_ai_test_db")
    db_path = db_dir / "test.db"
    database_url = f"sqlite:///{db_path}"

    os.environ["ETF_AI_TEST_DB"] = database_url

    # 延迟导入，确保环境变量已就位。
    from src.storage import database as db

    db.reset_engine(database_url)
    db.init_db()
    yield

    if db.engine is not None:
        db.engine.dispose()


@pytest.fixture(autouse=True)
def _clean_orm_tables() -> None:
    """每个用例前清空所有 ORM 表，避免测试顺序敏感。"""
    from src.storage import database as db

    # 确保用例边界不携带旧 Session 状态/连接。
    close_all_sessions()
    db.init_db()
    assert db.engine is not None

    with db.engine.begin() as conn:
        for table in reversed(db.Base.metadata.sorted_tables):
            conn.execute(table.delete())

    yield
    close_all_sessions()

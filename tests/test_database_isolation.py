import os
from datetime import date
from pathlib import Path

import pytest


def test_sessionlocal_uses_temp_database(tmp_path, monkeypatch):
    from src.storage import database as db
    from src.core.config import config_loader

    project_root = Path(__file__).resolve().parents[1]
    settings_db_url = config_loader.load_settings().database_url
    if not settings_db_url.startswith("sqlite:///"):
        pytest.skip("only sqlite file db is supported for production-db touch assertion")
    relative_db_path = settings_db_url.replace("sqlite:///", "", 1)
    production_db_path = (project_root / relative_db_path).resolve()
    existed_before = production_db_path.exists()
    stat_before = production_db_path.stat() if existed_before else None

    previous_url = os.getenv("ETF_AI_TEST_DB")
    assert previous_url is not None  # 由 tests/conftest.py 注入

    try:
        test_db_path = tmp_path / "test.db"
        monkeypatch.setenv("ETF_AI_TEST_DB", f"sqlite:///{test_db_path}")
        db.reset_engine()
        db.init_db()

        assert db.DATABASE_URL is not None
        assert db.DATABASE_URL.endswith("test.db")
        assert test_db_path.exists()
        assert test_db_path.stat().st_size > 0

        # 直接证明默认业务库文件未被创建或写入。
        assert production_db_path.exists() == existed_before
        if existed_before and stat_before is not None:
            stat_after = production_db_path.stat()
            assert stat_after.st_mtime_ns == stat_before.st_mtime_ns
            assert stat_after.st_size == stat_before.st_size
    finally:
        # 恢复到 session 级临时库，避免中途失败时污染后续测试
        monkeypatch.setenv("ETF_AI_TEST_DB", previous_url)
        db.reset_engine(previous_url)


def test_reset_engine_prevents_old_session_writing_old_database(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from src.storage import database as db
    from src.storage.models import MarketPrice

    previous_url = os.getenv("ETF_AI_TEST_DB")
    assert previous_url is not None

    old_db_path = tmp_path / "old.db"
    new_db_path = tmp_path / "new.db"
    old_url = f"sqlite:///{old_db_path}"
    new_url = f"sqlite:///{new_db_path}"

    def _count_rows(database_url: str) -> int:
        engine = create_engine(database_url, future=True)
        Session = sessionmaker(bind=engine, future=True)
        session = Session()
        try:
            return session.query(MarketPrice).count()
        finally:
            session.close()
            engine.dispose()

    try:
        monkeypatch.setenv("ETF_AI_TEST_DB", old_url)
        db.reset_engine()
        db.init_db()

        session = db.SessionLocal()
        session.add(
            MarketPrice(
                symbol="510300",
                trade_date=date(2026, 3, 13),
                close=5.0,
                source="test",
            )
        )
        session.commit()

        monkeypatch.setenv("ETF_AI_TEST_DB", new_url)
        db.reset_engine()
        db.init_db()

        # 复用旧 Session：不应继续写入旧库（应路由到当前 engine/new_url）。
        session.add(
            MarketPrice(
                symbol="510300",
                trade_date=date(2026, 3, 14),
                close=6.0,
                source="test",
            )
        )
        session.commit()
        session.close()

        assert _count_rows(old_url) == 1
        assert _count_rows(new_url) == 1
    finally:
        monkeypatch.setenv("ETF_AI_TEST_DB", previous_url)
        db.reset_engine(previous_url)

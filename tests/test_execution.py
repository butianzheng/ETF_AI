from datetime import date

import pytest
import pandas as pd

from src.execution.checker import OrderChecker, OrderRequest
from src.execution.executor import RebalanceExecutor
from src.storage.models import PortfolioState
from src.storage.repositories import ExecutionRepository, PortfolioRepository, PriceRepository


def _seed_price(symbol: str, trade_date: date, close: float) -> None:
    repo = PriceRepository()
    try:
        repo.save_prices(
            symbol,
            pd.DataFrame(
                [
                    {
                        "trade_date": trade_date,
                        "open": close,
                        "high": close,
                        "low": close,
                        "close": close,
                        "volume": 100000,
                        "amount": close * 100000,
                        "source": "test",
                    }
                ]
            ),
        )
    finally:
        repo.close()


@pytest.fixture(autouse=True)
def _seed_execution_fixtures(_clean_orm_tables):
    # 依赖 conftest 的统一清表 fixture，确保每个用例都有一致的初始数据。
    _seed_price("510300", date(2026, 3, 13), 5.0)
    _seed_price("510500", date(2026, 3, 13), 6.0)
    yield


def test_order_checker_accepts_valid_order():
    checker = OrderChecker()
    try:
        result = checker.check(
            OrderRequest(
                trade_date=date(2026, 3, 13),
                target_position="510300",
                current_position=None,
                available_cash=100000.0,
                order_amount=50000.0,
                rebalance=True,
            )
        )
        assert result.passed is True
        assert result.estimated_shares >= 100
    finally:
        checker.close()


def test_order_checker_rejects_invalid_order():
    checker = OrderChecker()
    try:
        result = checker.check(
            OrderRequest(
                trade_date=date(2026, 3, 13),
                target_position="999999",
                current_position=None,
                available_cash=1000.0,
                order_amount=1000.0,
                rebalance=True,
                manual_approved=False,
            )
        )
        assert result.passed is False
        assert any("白名单" in reason for reason in result.reasons)
        assert any("人工确认" in reason for reason in result.reasons)
    finally:
        checker.close()


def test_order_checker_uses_sell_proceeds_preview_for_rebalance():
    checker = OrderChecker()
    try:
        result = checker.check(
            OrderRequest(
                trade_date=date(2026, 3, 13),
                target_position="510500",
                current_position="510300",
                available_cash=0.0,
                order_amount=500.0,
                rebalance=True,
                current_holding_shares=100,
            )
        )
        assert result.passed is False
        assert result.estimated_shares == 0
        assert any("不足一个最小交易单位" in reason for reason in result.reasons)
    finally:
        checker.close()


def test_order_checker_prefers_repo_portfolio_state_over_request_snapshot():
    portfolio_repo = PortfolioRepository()
    try:
        portfolio_repo.save_state(
            PortfolioState(
                trade_date=date(2026, 3, 12),
                cash=0.0,
                holding_symbol="510300",
                holding_shares=100.0,
                total_asset=500.0,
                nav=500.0,
            )
        )
    finally:
        portfolio_repo.close()

    checker = OrderChecker()
    try:
        result = checker.check(
            OrderRequest(
                trade_date=date(2026, 3, 13),
                target_position="510500",
                current_position=None,
                available_cash=100000.0,
                order_amount=100000.0,
                rebalance=True,
                current_holding_shares=0,
            )
        )
    finally:
        checker.close()

    assert result.passed is False
    assert result.estimated_shares == 0
    assert any("不足一个最小交易单位" in reason for reason in result.reasons)


def test_executor_records_execution_result():
    executor = RebalanceExecutor()
    try:
        result = executor.execute(
            OrderRequest(
                trade_date=date(2026, 3, 13),
                target_position="510300",
                current_position=None,
                available_cash=100000.0,
                order_amount=50000.0,
                rebalance=True,
            )
        )
        assert result.status == "filled"
        assert result.filled_shares >= 100

        execution_repo = ExecutionRepository()
        portfolio_repo = PortfolioRepository()
        try:
            latest_record = execution_repo.get_latest()
            latest_state = portfolio_repo.get_by_date(date(2026, 3, 13))
            assert latest_record is not None
            assert latest_record.status == "filled"
            assert latest_state is not None
            assert latest_state.holding_symbol == "510300"
        finally:
            execution_repo.close()
            portfolio_repo.close()
    finally:
        executor.close()

import csv
from datetime import date, timedelta

import pandas as pd
import pytest

from src.backtest.comparator import compare_params
from src.backtest.engine import SimpleBacktestEngine
from src.data.calendar import TradingCalendar, trading_calendar
from src.execution.checker import OrderRequest
from src.execution.executor import RebalanceExecutor
from src.execution.schedule import RebalanceScheduleService
from src.execution.trade_policy import TradePolicy
from src.core.config import config_loader
from src.main import _build_risk_input, run_daily_pipeline
from src.research_pipeline import _save_research_outputs
from src.storage.database import SessionLocal
from src.storage.models import AgentLog, BacktestRun, ExecutionRecord, MarketPrice, PortfolioState, StrategySignal
from src.storage.repositories import ExecutionRepository, PortfolioRepository, PriceRepository
from src.strategy.engine import StrategyResult


def _reset_calendar() -> None:
    trading_calendar._calendar = None
    trading_calendar._calendar_set = None


def _seed_symbol(symbol: str, start_date: date, days: int, base: float, slope: float) -> None:
    rows = []
    for idx in range(days):
        current_date = start_date + timedelta(days=idx)
        if current_date.weekday() >= 5:
            continue
        close = round(base + slope * idx, 4)
        rows.append(
            {
                "trade_date": current_date,
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": 100000 + idx,
                "amount": close * (100000 + idx),
                "source": "test",
            }
        )
    repo = PriceRepository()
    try:
        repo.save_prices(symbol, pd.DataFrame(rows))
    finally:
        repo.close()


def _build_price_df(start_date: date, days: int, base: float, slope: float) -> pd.DataFrame:
    rows = []
    for idx in range(days):
        current_date = start_date + timedelta(days=idx)
        if current_date.weekday() >= 5:
            continue
        close = round(base + slope * idx, 4)
        rows.append(
            {
                "trade_date": current_date,
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": 100000 + idx,
                "amount": close * (100000 + idx),
                "source": "test",
            }
        )
    return pd.DataFrame(rows)


@pytest.fixture(autouse=True)
def _reset_state():
    _reset_calendar()
    yield


def test_executor_rejects_zero_share_after_fee():
    _seed_symbol("510300", date(2026, 3, 13), 1, 5.0, 0.0)

    executor = RebalanceExecutor()
    try:
        result = executor.execute(
            OrderRequest(
                trade_date=date(2026, 3, 13),
                target_position="510300",
                current_position=None,
                available_cash=500.0,
                order_amount=500.0,
                rebalance=True,
                manual_approved=True,
            )
        )
    finally:
        executor.close()

    execution_repo = ExecutionRepository()
    portfolio_repo = PortfolioRepository()
    try:
        latest_record = execution_repo.get_latest()
        latest_state = portfolio_repo.get_by_date(date(2026, 3, 13))
    finally:
        execution_repo.close()
        portfolio_repo.close()

    assert result.status == "rejected"
    assert "不足一个最小交易单位" in result.reason
    assert latest_record is not None
    assert latest_record.status == "rejected"
    assert latest_state is None


def test_backtest_uses_integer_lots_and_keeps_cash_remainder():
    start = date(2025, 12, 1)
    _seed_symbol("510300", start, 140, 6.0, 0.0)

    engine = SimpleBacktestEngine(
        config=config_loader.load_strategy_config(),
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
        initial_capital=100000.0,
        fee_rate=0.001,
    )

    def _fixed_signal(trade_date, price_data, current_position):
        return StrategyResult(
            trade_date=trade_date,
            strategy_version="test",
            rebalance=True,
            current_position=current_position,
            target_position="510300",
            scores=[],
        )

    engine.engine.run = _fixed_signal
    nav_series, results = engine.run(persist_run=False)

    assert len(results) == 1
    assert nav_series.index[-1] == date(2026, 3, 31)
    assert nav_series.iloc[-1] == pytest.approx(99900.4)


def test_daily_pipeline_rejects_holiday_execution():
    start = date(2025, 12, 1)
    price_data = {
        "510300": _build_price_df(start, 320, 4.0, 0.001),
        "510500": _build_price_df(start, 320, 3.5, 0.006),
        "159915": _build_price_df(start, 320, 3.0, 0.002),
        "515180": _build_price_df(start, 320, 2.8, 0.0015),
    }
    for symbol, df in price_data.items():
        price_data[symbol] = df[df["trade_date"] != date(2026, 10, 1)].reset_index(drop=True)

    result = run_daily_pipeline(
        as_of_date=date(2026, 10, 1),
        log_level="INFO",
        execute_trade=True,
        manual_approved=True,
        available_cash=100000.0,
        refresh_data=False,
        price_data_override=price_data,
    )

    assert result["status"] == "ok"
    assert result["order_check_result"].passed is False
    assert any("不是交易日" in reason for reason in result["order_check_result"].reasons)
    assert result["execution_result"] is None


def test_biweekly_rebalance_uses_last_trading_day_before_15th():
    calendar = TradingCalendar()
    trading_days = [item.date() for item in pd.date_range("2026-03-01", "2026-03-31", freq="B")]
    calendar.load_calendar(trading_days)
    service = RebalanceScheduleService(
        calendar,
        TradePolicy(rebalance_frequency="biweekly"),
    )

    assert service.build_signal_dates(
        date(2026, 3, 1),
        date(2026, 3, 31),
    ) == [date(2026, 3, 13), date(2026, 3, 31)]


def test_compare_params_persists_single_backtest_run():
    start = date(2024, 12, 1)
    _seed_symbol("510300", start, 520, 4.0, 0.001)
    _seed_symbol("510500", start, 520, 3.5, 0.0045)
    _seed_symbol("159915", start, 520, 3.0, 0.0025)
    _seed_symbol("515180", start, 520, 2.8, 0.0018)

    session = SessionLocal()
    try:
        before = session.query(BacktestRun).count()
    finally:
        session.close()

    compare_params(
        [{"rebalance_frequency": "monthly"}],
        start_date=date(2025, 12, 1),
        end_date=date(2026, 3, 11),
    )

    session = SessionLocal()
    try:
        after = session.query(BacktestRun).count()
    finally:
        session.close()

    assert after - before == 1


def test_build_risk_input_uses_portfolio_history():
    repo = PortfolioRepository()
    try:
        repo.save_state(
            PortfolioState(
                trade_date=date(2026, 3, 10),
                cash=10000.0,
                holding_symbol="510300",
                holding_shares=1000.0,
                total_asset=100000.0,
                nav=100000.0,
            )
        )
        repo.save_state(
            PortfolioState(
                trade_date=date(2026, 3, 11),
                cash=10000.0,
                holding_symbol="510300",
                holding_shares=1000.0,
                total_asset=90000.0,
                nav=90000.0,
            )
        )
    finally:
        repo.close()

    risk_input = _build_risk_input(
        trade_date=date(2026, 3, 11),
        price_data={
            "510300": pd.DataFrame(
                [
                    {"trade_date": date(2026, 3, 10), "close": 1.0},
                    {"trade_date": date(2026, 3, 11), "close": 0.98},
                ]
            )
        },
        portfolio_state={
            "cash": 10000.0,
            "holding_symbol": "510300",
            "holding_shares": 1000.0,
            "total_asset": 90000.0,
            "nav": 90000.0,
        },
    )

    assert len(risk_input.nav_series) == 2
    assert risk_input.nav_series[-1]["nav"] == 90000.0
    assert round(risk_input.current_drawdown, 4) == -0.1


def test_save_research_outputs_writes_valid_csv():
    output_paths = _save_research_outputs(
        end_date=date(2026, 3, 12),
        comparison_rows=[
            {
                "name": "baseline",
                "annual_return": 0.1,
                "max_drawdown": -0.05,
                "sharpe": 1.2,
                "turnover": 0.3,
                "trade_count": 2,
                "win_rate": 0.5,
                "profit_drawdown_ratio": 2.0,
                "overrides": {
                    "rebalance_frequency": "biweekly",
                    "note": "contains,comma",
                    "score_formula": {"return_20_weight": 0.6, "return_60_weight": 0.4},
                },
            }
        ],
        research_output={
            "summary": "x",
            "recommendation": "y",
            "overfit_risk": "low",
            "ranked_candidates": [],
        },
        markdown_report="x",
    )

    with open(output_paths["csv"], "r", encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))

    assert len(rows[0]) == 9
    assert len(rows[1]) == 9
    assert '"note": "contains,comma"' in rows[1][-1]

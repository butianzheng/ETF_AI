from datetime import date

import pandas as pd

from src.core.config import ConfigLoader
from src.data.calendar import TradingCalendar
from src.execution.schedule import RebalanceScheduleService
from src.execution.trade_policy import TradePolicy


def _build_calendar(start: str, end: str) -> TradingCalendar:
    calendar = TradingCalendar()
    calendar.load_calendar([item.date() for item in pd.date_range(start, end, freq="B")])
    return calendar


def test_monthly_schedule_generates_signal_and_next_execution():
    calendar = _build_calendar("2026-03-01", "2026-04-10")
    policy = TradePolicy(rebalance_frequency="monthly", execution_delay_trading_days=1)

    schedule = RebalanceScheduleService(calendar, policy)
    dates = schedule.build_plan(date(2026, 3, 1), date(2026, 3, 31))

    assert len(dates) == 1
    assert dates[0].signal_date == date(2026, 3, 31)
    assert dates[0].execution_date == date(2026, 4, 1)


def test_schedule_service_exposes_signal_and_execution_day_flags():
    calendar = _build_calendar("2026-03-01", "2026-04-10")
    policy = TradePolicy(rebalance_frequency="monthly", execution_delay_trading_days=1)

    service = RebalanceScheduleService(calendar, policy)
    service.build_plan(date(2026, 3, 1), date(2026, 3, 31))

    assert service.is_signal_day(date(2026, 3, 30)) is False
    assert service.is_signal_day(date(2026, 3, 31)) is True
    assert service.is_execution_day(date(2026, 4, 1)) is True
    assert service.is_execution_day(date(2026, 3, 31)) is False


def test_schedule_service_keeps_signal_day_when_execution_day_is_unavailable():
    calendar = _build_calendar("2026-03-01", "2026-03-31")
    policy = TradePolicy(rebalance_frequency="monthly", execution_delay_trading_days=1)

    service = RebalanceScheduleService(calendar, policy)
    dates = service.build_plan(date(2026, 3, 1), date(2026, 3, 31))

    assert len(dates) == 1
    assert dates[0].signal_date == date(2026, 3, 31)
    assert dates[0].execution_date is None
    assert service.is_signal_day(date(2026, 3, 31)) is True
    assert service.is_execution_day(date(2026, 4, 1)) is False


def test_config_loader_reads_trade_policy_and_production_strategy_id(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "strategy.yaml").write_text(
        """
production_strategy_id: live-momentum
strategy:
  name: etf_momentum_v1
  version: "1.0.0"
  rebalance_frequency: monthly
  hold_count: 1
  trade_policy:
    rebalance_frequency: biweekly
    execution_delay_trading_days: 2
    lot_size: 200
    fee_rate: 0.002
  score_formula:
    return_20_weight: 0.5
    return_60_weight: 0.5
  trend_filter:
    enabled: true
    ma_period: 120
    ma_type: sma
  defensive_mode:
    enabled: false
    defensive_etf: null
  allow_cash: true
""".strip(),
        encoding="utf-8",
    )

    loader = ConfigLoader(str(config_dir))
    config = loader.load_strategy_config()

    assert loader.load_production_strategy_id() == "live-momentum"
    assert config.trade_policy.rebalance_frequency == "biweekly"
    assert config.trade_policy.execution_delay_trading_days == 2
    assert config.trade_policy.lot_size == 200
    assert config.trade_policy.fee_rate == 0.002

"""调仓计划服务。"""
from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import List

from pydantic import BaseModel

from src.data.calendar import TradingCalendar
from src.execution.trade_policy import TradePolicy


class RebalanceEvent(BaseModel):
    """单次调仓事件。"""

    signal_date: date
    execution_date: date | None


class RebalanceScheduleService:
    """基于交易日历和交易策略生成调仓计划。"""

    def __init__(self, calendar: TradingCalendar, policy: TradePolicy):
        self.calendar = calendar
        self.policy = policy
        self._events: List[RebalanceEvent] = []
        self._signal_days: set[date] = set()
        self._execution_days: set[date] = set()

    def _advance_trading_days(self, current_date: date, steps: int) -> date | None:
        if steps < 0:
            raise ValueError("steps must be non-negative")

        result = current_date
        for _ in range(steps):
            next_date = self.calendar.next_trading_day(result)
            if next_date is None:
                return None
            result = next_date
        return result

    def _monthly_signal_dates(self, start_date: date, end_date: date) -> List[date]:
        dates: List[date] = []
        current_year = start_date.year
        current_month = start_date.month

        while True:
            signal_date = self.calendar.get_month_end_trading_day(current_year, current_month)
            if signal_date and start_date <= signal_date <= end_date:
                dates.append(signal_date)

            if current_month == 12:
                current_year += 1
                current_month = 1
            else:
                current_month += 1

            if date(current_year, current_month, 1) > end_date:
                break

        return dates

    def _biweekly_signal_dates(self, start_date: date, end_date: date) -> List[date]:
        dates: List[date] = []
        current_year = start_date.year
        current_month = start_date.month

        while True:
            month_last_day = monthrange(current_year, current_month)[1]
            mid_anchor = date(current_year, current_month, min(15, month_last_day))
            mid_signal = self.calendar.get_last_trading_day_on_or_before(mid_anchor)
            month_end_signal = self.calendar.get_month_end_trading_day(current_year, current_month)

            for signal_date in [mid_signal, month_end_signal]:
                if signal_date and start_date <= signal_date <= end_date:
                    dates.append(signal_date)

            if current_month == 12:
                current_year += 1
                current_month = 1
            else:
                current_month += 1

            if date(current_year, current_month, 1) > end_date:
                break

        return sorted(set(dates))

    def build_signal_dates(self, start_date: date, end_date: date) -> List[date]:
        if self.policy.rebalance_frequency == "monthly":
            return self._monthly_signal_dates(start_date, end_date)
        return self._biweekly_signal_dates(start_date, end_date)

    def build_plan(self, start_date: date, end_date: date) -> List[RebalanceEvent]:
        signal_dates = self.build_signal_dates(start_date, end_date)
        events: List[RebalanceEvent] = []
        for signal_date in signal_dates:
            execution_date = self._advance_trading_days(signal_date, self.policy.execution_delay_trading_days)
            events.append(
                RebalanceEvent(
                    signal_date=signal_date,
                    execution_date=execution_date,
                )
            )

        self._events = events
        self._signal_days = set(signal_dates)
        self._execution_days = {item.execution_date for item in events if item.execution_date is not None}
        return events

    def is_signal_day(self, check_date: date) -> bool:
        return check_date in self._signal_days

    def is_execution_day(self, check_date: date) -> bool:
        return check_date in self._execution_days

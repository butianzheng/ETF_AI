"""交易日历模块"""
from datetime import date, datetime, timedelta
from typing import List, Optional
import pandas as pd
from src.core.logger import get_logger

logger = get_logger(__name__)


class TradingCalendar:
    """交易日历管理器"""

    def __init__(self):
        self._calendar: Optional[List[date]] = None
        self._calendar_set: Optional[set] = None

    def load_calendar(self, trading_days: List[date]):
        """
        加载交易日历

        Args:
            trading_days: 交易日列表
        """
        self._calendar = sorted(trading_days)
        self._calendar_set = set(trading_days)
        logger.info(f"Loaded calendar with {len(self._calendar)} trading days")

    def has_calendar(self) -> bool:
        return self._calendar_set is not None

    def is_trading_day(self, check_date: date) -> bool:
        """
        判断是否为交易日

        Args:
            check_date: 要检查的日期

        Returns:
            True if trading day
        """
        if self._calendar_set is None:
            # 简单判断：周末不是交易日
            return check_date.weekday() < 5

        return check_date in self._calendar_set

    def next_trading_day(self, current_date: date) -> Optional[date]:
        """
        获取下一个交易日

        Args:
            current_date: 当前日期

        Returns:
            下一个交易日，如果没有则返回None
        """
        if self._calendar is None:
            # 简单实现：跳过周末
            next_date = current_date + timedelta(days=1)
            while next_date.weekday() >= 5:
                next_date += timedelta(days=1)
            return next_date

        # 在日历中查找
        for trading_day in self._calendar:
            if trading_day > current_date:
                return trading_day

        return None

    def prev_trading_day(self, current_date: date) -> Optional[date]:
        """
        获取上一个交易日

        Args:
            current_date: 当前日期

        Returns:
            上一个交易日，如果没有则返回None
        """
        if self._calendar is None:
            # 简单实现：跳过周末
            prev_date = current_date - timedelta(days=1)
            while prev_date.weekday() >= 5:
                prev_date -= timedelta(days=1)
            return prev_date

        # 在日历中查找
        for trading_day in reversed(self._calendar):
            if trading_day < current_date:
                return trading_day

        return None

    def get_trading_days(self, start_date: date, end_date: date) -> List[date]:
        """
        获取日期范围内的所有交易日

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            交易日列表
        """
        if self._calendar is None:
            # 简单实现：生成日期范围并过滤周末
            days = []
            current = start_date
            while current <= end_date:
                if current.weekday() < 5:
                    days.append(current)
                current += timedelta(days=1)
            return days

        # 从日历中过滤
        return [d for d in self._calendar if start_date <= d <= end_date]

    def get_month_end_trading_day(self, year: int, month: int) -> Optional[date]:
        """
        获取指定月份的最后一个交易日

        Args:
            year: 年份
            month: 月份

        Returns:
            月末交易日
        """
        # 获取下个月第一天
        if month == 12:
            next_month_first = date(year + 1, 1, 1)
        else:
            next_month_first = date(year, month + 1, 1)

        # 当月最后一天
        month_last = next_month_first - timedelta(days=1)

        # 向前查找最后一个交易日
        current = month_last
        while current.month == month:
            if self.is_trading_day(current):
                return current
            current -= timedelta(days=1)

        return None

    def get_last_trading_day_on_or_before(self, anchor_date: date) -> Optional[date]:
        """获取同月、且不晚于 anchor_date 的最后一个交易日。"""
        month_start = date(anchor_date.year, anchor_date.month, 1)

        if self._calendar is None:
            current = anchor_date
            while current >= month_start:
                if current.weekday() < 5:
                    return current
                current -= timedelta(days=1)
            return None

        for trading_day in reversed(self._calendar):
            if trading_day < month_start:
                break
            if month_start <= trading_day <= anchor_date:
                return trading_day
        return None

# 全局交易日历实例
trading_calendar = TradingCalendar()

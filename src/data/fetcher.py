"""数据获取模块 - 封装akshare API"""
from datetime import date, datetime
from typing import Dict, List, Optional
import pandas as pd
import akshare as ak
import time
from src.core.logger import get_logger

logger = get_logger(__name__)


class DataFetcher:
    """ETF数据获取器"""

    def __init__(self, max_retries: int = 3, retry_delay: float = 2.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _retry_wrapper(self, func, *args, **kwargs):
        """重试包装器"""
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == self.max_retries - 1:
                    logger.error(f"Failed after {self.max_retries} attempts: {e}")
                    raise
                logger.warning(f"Attempt {attempt + 1} failed: {e}, retrying...")
                time.sleep(self.retry_delay * (attempt + 1))

    def fetch_etf_daily(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取ETF日线行情数据

        Args:
            symbol: ETF代码，如 "510300"
            start_date: 开始日期，格式 "20260101"
            end_date: 结束日期，格式 "20260312"

        Returns:
            DataFrame with columns: 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额
        """
        logger.info(f"Fetching daily data for {symbol} from {start_date} to {end_date}")

        def _fetch():
            df = ak.fund_etf_hist_em(
                symbol=symbol,
                period="daily",
                start_date=start_date or "19700101",
                end_date=end_date or "20500101",
                adjust="",
            )
            return df

        df = self._retry_wrapper(_fetch)

        # 双重兜底过滤日期范围，兼容不同数据源字段
        if start_date or end_date:
            date_col = "date" if "date" in df.columns else "日期"
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col])
                if start_date:
                    start_dt = pd.to_datetime(start_date)
                    df = df[df[date_col] >= start_dt]
                if end_date:
                    end_dt = pd.to_datetime(end_date)
                    df = df[df[date_col] <= end_dt]

        logger.info(f"Fetched {len(df)} records for {symbol}")
        return df

    def fetch_latest_price(self, symbols: List[str]) -> Dict[str, float]:
        """
        获取多个ETF的最新价格

        Args:
            symbols: ETF代码列表

        Returns:
            {symbol: latest_price}
        """
        logger.info(f"Fetching latest prices for {len(symbols)} symbols")
        result = {}

        for symbol in symbols:
            try:
                df = self.fetch_etf_daily(symbol)
                if not df.empty:
                    close_col = "close" if "close" in df.columns else "收盘"
                    latest_price = float(df.iloc[-1][close_col])
                    result[symbol] = latest_price
                    logger.debug(f"{symbol}: {latest_price}")
            except Exception as e:
                logger.error(f"Failed to fetch latest price for {symbol}: {e}")
                result[symbol] = None

        return result

    def is_trading_day(self, check_date: date) -> bool:
        """
        判断是否为交易日

        Args:
            check_date: 要检查的日期

        Returns:
            True if trading day, False otherwise
        """
        # 简单实现：周末不是交易日
        # 更完整的实现应该查询交易日历
        if check_date.weekday() >= 5:  # 周六、周日
            return False

        # TODO: 检查节假日
        return True

    def get_trading_calendar(
        self,
        start_date: str,
        end_date: str
    ) -> List[date]:
        """
        获取交易日历

        Args:
            start_date: 开始日期 "20260101"
            end_date: 结束日期 "20261231"

        Returns:
            交易日列表
        """
        logger.info(f"Getting trading calendar from {start_date} to {end_date}")

        def _fetch():
            # 使用akshare获取交易日历
            df = ak.tool_trade_date_hist_sina()
            return df

        df = self._retry_wrapper(_fetch)

        # 过滤日期范围
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)

        df = df[(df['trade_date'] >= start_dt) & (df['trade_date'] <= end_dt)]
        trading_days = df['trade_date'].dt.date.tolist()

        logger.info(f"Found {len(trading_days)} trading days")
        return trading_days

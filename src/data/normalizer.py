"""数据标准化模块"""
from datetime import date
from typing import List
import pandas as pd
import numpy as np
from src.core.logger import get_logger

logger = get_logger(__name__)


class DataNormalizer:
    """数据标准化器"""

    @staticmethod
    def normalize_price_data(df: pd.DataFrame) -> pd.DataFrame:
        """
        标准化价格数据格式

        输入格式（akshare）:
            date, open, close, high, low, volume, amount

        输出格式（内部标准）:
            trade_date, open, close, high, low, volume, amount

        Args:
            df: 原始DataFrame

        Returns:
            标准化后的DataFrame
        """
        logger.debug(f"Normalizing price data with {len(df)} records")

        # 复制数据避免修改原始数据
        df = df.copy()

        # 重命名列
        column_mapping = {
            'date': 'trade_date',
            '日期': 'trade_date',
            'open': 'open',
            '开盘': 'open',
            'close': 'close',
            '收盘': 'close',
            'high': 'high',
            '最高': 'high',
            'low': 'low',
            '最低': 'low',
            'volume': 'volume',
            '成交量': 'volume',
            'amount': 'amount',
            '成交额': 'amount',
        }

        # 应用列名映射
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns:
                df.rename(columns={old_col: new_col}, inplace=True)

        # 确保日期格式
        if 'trade_date' in df.columns:
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date

        # 确保数值类型
        numeric_columns = ['open', 'close', 'high', 'low', 'volume', 'amount']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # 按日期排序
        if 'trade_date' in df.columns:
            df = df.sort_values('trade_date').reset_index(drop=True)

        logger.debug(f"Normalized data shape: {df.shape}")
        return df

    @staticmethod
    def fill_missing_dates(
        df: pd.DataFrame,
        trading_calendar: List[date]
    ) -> pd.DataFrame:
        """
        填充缺失的交易日

        Args:
            df: 价格数据
            trading_calendar: 交易日历

        Returns:
            填充后的DataFrame
        """
        logger.debug(f"Filling missing dates, calendar has {len(trading_calendar)} days")

        # 创建完整日期范围的DataFrame
        full_dates = pd.DataFrame({'trade_date': trading_calendar})

        # 合并数据
        df = pd.merge(full_dates, df, on='trade_date', how='left')

        # 前向填充价格数据
        price_columns = ['open', 'close', 'high', 'low']
        df[price_columns] = df[price_columns].fillna(method='ffill')

        # 成交量和成交额缺失填0
        df['volume'] = df['volume'].fillna(0)
        df['amount'] = df['amount'].fillna(0)

        logger.debug(f"After filling, data shape: {df.shape}")
        return df

    @staticmethod
    def detect_outliers(df: pd.DataFrame, threshold: float = 0.15) -> pd.DataFrame:
        """
        检测价格异常跳变

        Args:
            df: 价格数据
            threshold: 涨跌幅阈值（默认15%）

        Returns:
            包含异常标记的DataFrame
        """
        logger.debug(f"Detecting outliers with threshold {threshold}")

        df = df.copy()

        # 计算日收益率
        df['return'] = df['close'].pct_change()

        # 标记异常
        df['is_outlier'] = np.abs(df['return']) > threshold

        outlier_count = df['is_outlier'].sum()
        if outlier_count > 0:
            logger.warning(f"Found {outlier_count} outliers")

        return df

    @staticmethod
    def remove_duplicates(df: pd.DataFrame) -> pd.DataFrame:
        """
        移除重复日期的数据

        Args:
            df: 价格数据

        Returns:
            去重后的DataFrame
        """
        before_count = len(df)
        df = df.drop_duplicates(subset=['trade_date'], keep='last')
        after_count = len(df)

        if before_count != after_count:
            logger.warning(f"Removed {before_count - after_count} duplicate records")

        return df

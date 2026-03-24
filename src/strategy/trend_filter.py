"""趋势过滤模块"""
from typing import Dict
import pandas as pd
import numpy as np
from src.core.logger import get_logger

logger = get_logger(__name__)


class TrendFilter:
    """趋势过滤器"""

    def __init__(self, ma_period: int = 120, ma_type: str = "sma"):
        """
        Args:
            ma_period: 移动平均周期
            ma_type: 移动平均类型 "sma" 或 "ema"
        """
        self.ma_period = ma_period
        self.ma_type = ma_type

    def calculate_ma(self, prices: pd.Series) -> float:
        """
        计算移动平均值

        Args:
            prices: 价格序列

        Returns:
            移动平均值，如果数据不足返回None
        """
        if len(prices) < self.ma_period:
            logger.warning(f"Insufficient data for MA{self.ma_period}: need {self.ma_period}, got {len(prices)}")
            return None

        if self.ma_type == "sma":
            # 简单移动平均
            ma_value = prices.iloc[-self.ma_period:].mean()
        elif self.ma_type == "ema":
            # 指数移动平均
            ma_value = prices.ewm(span=self.ma_period, adjust=False).mean().iloc[-1]
        else:
            raise ValueError(f"Unknown ma_type: {self.ma_type}")

        return ma_value

    def check_above_ma(self, current_price: float, ma_value: float) -> bool:
        """
        检查当前价格是否在MA之上

        Args:
            current_price: 当前价格
            ma_value: MA值

        Returns:
            True if above MA
        """
        if ma_value is None or pd.isna(ma_value):
            return False

        return current_price > ma_value

    def apply_trend_filter(
        self,
        price_data: Dict[str, pd.DataFrame]
    ) -> Dict[str, Dict]:
        """
        对多个标的应用趋势过滤

        Args:
            price_data: {symbol: DataFrame with 'close' column}

        Returns:
            {symbol: {'above_ma': bool, 'ma_value': float, 'current_price': float}}
        """
        logger.info(f"Applying trend filter (MA{self.ma_period}) to {len(price_data)} symbols")
        results = {}

        for symbol, df in price_data.items():
            if 'close' not in df.columns or len(df) == 0:
                logger.error(f"{symbol}: invalid data")
                results[symbol] = {
                    'above_ma': False,
                    'ma_value': None,
                    'current_price': None
                }
                continue

            # 计算MA
            ma_value = self.calculate_ma(df['close'])

            # 获取当前价格
            current_price = df['close'].iloc[-1]

            # 判断是否在MA之上
            above_ma = self.check_above_ma(current_price, ma_value)

            results[symbol] = {
                'above_ma': above_ma,
                'ma_value': ma_value,
                'current_price': current_price
            }

            ma_display = f"{ma_value:.3f}" if ma_value is not None else "None"
            logger.debug(f"{symbol}: price={current_price:.3f}, MA{self.ma_period}={ma_display}, above={above_ma}")

        return results

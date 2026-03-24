"""动量计算模块"""
from typing import Dict
import pandas as pd
import numpy as np
from src.core.logger import get_logger

logger = get_logger(__name__)


class MomentumCalculator:
    """动量计算器"""

    def __init__(self, return_20_weight: float = 0.5, return_60_weight: float = 0.5):
        """
        Args:
            return_20_weight: 20日收益率权重
            return_60_weight: 60日收益率权重
        """
        self.return_20_weight = return_20_weight
        self.return_60_weight = return_60_weight

    def calculate_return(self, prices: pd.Series, period: int) -> float:
        """
        计算指定周期的收益率

        Args:
            prices: 价格序列（按日期升序）
            period: 周期天数

        Returns:
            收益率，如果数据不足返回None
        """
        if len(prices) < period + 1:
            logger.warning(f"Insufficient data: need {period + 1} days, got {len(prices)}")
            return None

        current_price = prices.iloc[-1]
        past_price = prices.iloc[-(period + 1)]

        if past_price == 0 or pd.isna(past_price) or pd.isna(current_price):
            return None

        return_value = (current_price / past_price) - 1
        return return_value

    def calculate_momentum_score(
        self,
        prices: pd.Series,
        return_20_period: int = 20,
        return_60_period: int = 60
    ) -> Dict:
        """
        计算综合动量得分

        Args:
            prices: 价格序列
            return_20_period: 短期周期
            return_60_period: 中期周期

        Returns:
            {
                'score': 综合得分,
                'return_20': 20日收益率,
                'return_60': 60日收益率
            }
        """
        # 计算20日收益率
        return_20 = self.calculate_return(prices, return_20_period)

        # 计算60日收益率
        return_60 = self.calculate_return(prices, return_60_period)

        # 如果任一收益率无效，返回None
        if return_20 is None or return_60 is None:
            return {
                'score': None,
                'return_20': return_20,
                'return_60': return_60
            }

        # 计算加权得分
        score = (self.return_20_weight * return_20 +
                 self.return_60_weight * return_60)

        return {
            'score': score,
            'return_20': return_20,
            'return_60': return_60
        }

    def calculate_multi_symbol_scores(
        self,
        price_data: Dict[str, pd.DataFrame]
    ) -> Dict[str, Dict]:
        """
        计算多个标的的动量得分

        Args:
            price_data: {symbol: DataFrame with 'close' column}

        Returns:
            {symbol: score_dict}
        """
        logger.info(f"Calculating momentum scores for {len(price_data)} symbols")
        results = {}

        for symbol, df in price_data.items():
            if 'close' not in df.columns:
                logger.error(f"{symbol}: missing 'close' column")
                results[symbol] = {'score': None, 'return_20': None, 'return_60': None}
                continue

            score_dict = self.calculate_momentum_score(df['close'])
            results[symbol] = score_dict

            if score_dict['score'] is not None:
                logger.debug(f"{symbol}: score={score_dict['score']:.4f}, "
                           f"r20={score_dict['return_20']:.4f}, "
                           f"r60={score_dict['return_60']:.4f}")

        return results

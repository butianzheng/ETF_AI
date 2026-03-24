"""策略引擎核心模块"""
from datetime import date
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import pandas as pd

from src.strategy.momentum import MomentumCalculator
from src.strategy.trend_filter import TrendFilter
from src.strategy.selector import PositionSelector, ETFScore
from src.core.config import StrategyConfig
from src.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class StrategyResult:
    """策略运行结果"""
    trade_date: date
    strategy_version: str
    rebalance: bool
    current_position: Optional[str]
    target_position: Optional[str]
    scores: List[ETFScore]
    risk_mode: str = "normal"

    def to_dict(self) -> dict:
        """转换为字典"""
        result = asdict(self)
        # 转换日期为字符串
        result['trade_date'] = self.trade_date.isoformat()
        # 转换ETFScore列表
        result['scores'] = [asdict(score) for score in self.scores]
        return result


class StrategyEngine:
    """策略引擎"""

    def __init__(self, config: StrategyConfig, etf_names: Dict[str, str]):
        """
        Args:
            config: 策略配置
            etf_names: ETF名称映射 {code: name}
        """
        self.config = config
        self.etf_names = etf_names

        # 初始化各模块
        self.momentum_calculator = MomentumCalculator(
            return_20_weight=config.score_formula.return_20_weight,
            return_60_weight=config.score_formula.return_60_weight
        )

        self.trend_filter = TrendFilter(
            ma_period=config.trend_filter.ma_period,
            ma_type=config.trend_filter.ma_type
        ) if config.trend_filter.enabled else None

        self.selector = PositionSelector(
            hold_count=config.hold_count,
            allow_cash=config.allow_cash
        )

        logger.info(f"Strategy engine initialized: {config.name} v{config.version}")

    def run(
        self,
        trade_date: date,
        price_data: Dict[str, pd.DataFrame],
        current_position: Optional[str] = None
    ) -> StrategyResult:
        """
        运行策略计算

        Args:
            trade_date: 计算日期
            price_data: {symbol: DataFrame with OHLCV data}
            current_position: 当前持仓代码

        Returns:
            StrategyResult
        """
        logger.info(f"Running strategy for {trade_date}, current position: {current_position}")

        # 1. 计算动量得分
        scores = self.momentum_calculator.calculate_multi_symbol_scores(price_data)

        # 2. 应用趋势过滤
        if self.trend_filter:
            trend_status = self.trend_filter.apply_trend_filter(price_data)
        else:
            # 如果不启用趋势过滤，所有标的都通过
            trend_status = {
                symbol: {'above_ma': True, 'ma_value': None, 'current_price': df['close'].iloc[-1]}
                for symbol, df in price_data.items()
            }

        # 3. 选择目标持仓
        target_position = self.selector.select_target_position(
            scores=scores,
            trend_status=trend_status,
            etf_names=self.etf_names
        )

        # 4. 判断是否调仓
        rebalance = (target_position != current_position)

        # 5. 获取所有得分（用于报告）
        all_scores = self.selector.get_all_scores(
            scores=scores,
            trend_status=trend_status,
            etf_names=self.etf_names
        )

        # 6. 构建结果
        result = StrategyResult(
            trade_date=trade_date,
            strategy_version=f"{self.config.name}_v{self.config.version}",
            rebalance=rebalance,
            current_position=current_position,
            target_position=target_position,
            scores=all_scores,
            risk_mode="normal"
        )

        if rebalance:
            logger.info(f"Rebalance signal: {current_position} -> {target_position}")
        else:
            logger.info(f"Hold signal: {current_position}")

        return result

    def generate_signal_description(self, result: StrategyResult) -> str:
        """
        生成信号描述文本

        Args:
            result: 策略结果

        Returns:
            信号描述
        """
        if result.rebalance:
            if result.target_position is None:
                return f"SELL {result.current_position}, MOVE_TO_CASH"
            elif result.current_position is None:
                return f"BUY {result.target_position}"
            else:
                return f"SELL {result.current_position}, BUY {result.target_position}"
        else:
            if result.current_position is None:
                return "HOLD CASH"
            else:
                return f"HOLD {result.current_position}"

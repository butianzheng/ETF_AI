"""统一交易语义配置。"""
from typing import Literal

from pydantic import BaseModel


class TradePolicy(BaseModel):
    """交易执行相关的统一策略配置。"""

    rebalance_frequency: Literal["monthly", "biweekly"]
    execution_delay_trading_days: int = 1
    lot_size: int = 100
    fee_rate: float = 0.001

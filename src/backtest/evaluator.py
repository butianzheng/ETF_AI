"""回测评估模块（evaluator.py）

提供基于净值序列的常用回测指标计算函数。
"""
from datetime import date
from typing import Dict, Tuple
import pandas as pd
import numpy as np


def calculate_annual_return(nav: pd.Series) -> float:
    """计算年化收益率

    Args:
        nav: 净值序列，index 为日期（datetime.date）
    Returns:
        年化收益率（小数）
    """
    if nav.empty:
        return 0.0
    total_days = (nav.index[-1] - nav.index[0]).days
    if total_days == 0:
        return 0.0
    total_return = nav.iloc[-1] / nav.iloc[0] - 1
    # 年化公式 (1+r)^{365/days} - 1
    return (1 + total_return) ** (365 / total_days) - 1


def calculate_max_drawdown(nav: pd.Series) -> float:
    """计算最大回撤（负数）"""
    if nav.empty:
        return 0.0
    roll_max = nav.cummax()
    drawdown = (nav - roll_max) / roll_max
    return drawdown.min()


def calculate_sharpe_ratio(nav: pd.Series, risk_free_annual: float = 0.03) -> float:
    """计算年化夏普比率

    Args:
        nav: 净值序列
        risk_free_annual: 年化无风险利率（默认 3%）
    Returns:
        夏普比率
    """
    if len(nav) < 2:
        return 0.0
    # 日收益率
    daily_ret = nav.pct_change().dropna()
    # 日无风险利率
    risk_free_daily = (1 + risk_free_annual) ** (1 / 252) - 1
    excess = daily_ret - risk_free_daily
    if excess.std() == 0:
        return 0.0
    sharpe_daily = excess.mean() / excess.std()
    # 年化
    return sharpe_daily * np.sqrt(252)


def calculate_turnover(nav: pd.Series, trades: int) -> float:
    """计算换手率（简单模型）

    参数说明：
    - nav: 净值序列
    - trades: 回测期间的实际交易次数（买入或卖出计一次）
    """
    if nav.empty:
        return 0.0
    # 换手率 = 交易次数 / 持有天数
    days = len(nav)
    return trades / days if days > 0 else 0.0


def calculate_trade_stats(nav: pd.Series) -> Dict[str, float]:
    """统计交易相关指标

    - 调仓次数（信号变动次数）
    - 胜率（净值上涨的调仓日占比）
    - 收益回撤比（累计收益 / 最大回撤的绝对值）
    """
    if nav.empty:
        return {"trade_count": 0, "win_rate": 0.0, "profit_drawdown_ratio": 0.0}

    # 调仓次数：净值曲线转折点（从下降转为上升）或简单计数每日正收益？这里采用正收益天数作为近似
    daily_ret = nav.pct_change().fillna(0)
    trade_count = (daily_ret != 0).sum()
    win_days = (daily_ret > 0).sum()
    win_rate = win_days / trade_count if trade_count > 0 else 0.0

    # 累计收益
    total_return = nav.iloc[-1] / nav.iloc[0] - 1
    max_dd = calculate_max_drawdown(nav)
    profit_drawdown_ratio = total_return / abs(max_dd) if max_dd != 0 else float('inf')

    return {
        "trade_count": int(trade_count),
        "win_rate": win_rate,
        "profit_drawdown_ratio": profit_drawdown_ratio,
    }


def evaluate_backtest(nav: pd.Series, trades: int = 0) -> Dict[str, float]:
    """一次性返回所有回测指标"""
    metrics = {}
    metrics["annual_return"] = calculate_annual_return(nav)
    metrics["max_drawdown"] = calculate_max_drawdown(nav)
    metrics["sharpe"] = calculate_sharpe_ratio(nav)
    metrics["turnover"] = calculate_turnover(nav, trades)
    trade_stats = calculate_trade_stats(nav)
    metrics.update(trade_stats)
    return metrics

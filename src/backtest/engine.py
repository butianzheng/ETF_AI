"""回测引擎模块

核心思路：
- 使用已有的 StrategyEngine 进行每个调仓日的策略计算
- 依据持仓变化计算每日净值（简单的持仓收益模型）
- 支持手续费、滑点的简单模型（可在参数中配置）
"""
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from src.core.config import config_loader, StrategyConfig
from src.execution.schedule import RebalanceScheduleService
from src.execution.simulator import ExecutionSimulator, PortfolioSnapshot
from src.strategy.candidates.base import BaseCandidateStrategy
from src.strategy.engine import StrategyEngine, StrategyResult
from src.strategy.features import build_feature_snapshot
from src.storage.models import BacktestRun
from src.storage.repositories import PriceRepository, PortfolioRepository, BacktestRepository
from src.core.logger import get_logger

logger = get_logger(__name__)


class SimpleBacktestEngine:
    """基于月度调仓的简易回测引擎"""

    def __init__(
        self,
        config: StrategyConfig,
        start_date: date,
        end_date: date,
        initial_capital: float = 100000.0,
        fee_rate: float = 0.001,
        candidate_strategy: Optional[BaseCandidateStrategy] = None,
    ):
        self.config = config
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.trade_policy = config.trade_policy.model_copy(update={"fee_rate": fee_rate})
        self.fee_rate = self.trade_policy.fee_rate
        self.candidate_strategy = candidate_strategy
        self.price_repo = PriceRepository()
        self.portfolio_repo = PortfolioRepository()
        self.backtest_repo = BacktestRepository()
        self.simulator = ExecutionSimulator(self.trade_policy, price_repo=self.price_repo)
        # 获取ETF名称映射
        self.etf_names = {etf.code: etf.name for etf in config_loader.load_etf_pool()}
        self.engine = StrategyEngine(config=config, etf_names=self.etf_names)
        # 读取完整交易日历
        from src.data.calendar import trading_calendar
        self.calendar = trading_calendar
        calendar_lookback = max(self.config.trend_filter.ma_period * 2, 365)
        symbols = config_loader.get_enabled_etf_codes()
        if symbols:
            trading_days = self.price_repo.get_trading_dates(
                symbols[0],
                start_date - timedelta(days=calendar_lookback),
                end_date,
            )
            if trading_days:
                self.calendar.load_calendar(trading_days)
        self.schedule_service = RebalanceScheduleService(self.calendar, self.trade_policy)
        self.rebalance_dates = self.schedule_service.build_signal_dates(start_date, end_date)

    def _get_price_snapshot(self, symbols: List[str], trade_date: date) -> Dict[str, pd.DataFrame]:
        """获取调仓日之前一定窗口的行情用于策略计算"""
        # 使用更宽的自然日窗口，避免交易日不足导致 MA120 计算失败。
        lookback_days = max(self.config.trend_filter.ma_period * 2, 365)
        start = trade_date - timedelta(days=lookback_days)
        price_data = self.price_repo.get_multi_symbol_prices(symbols, start, trade_date)
        return price_data

    def run(self, persist_run: bool = True) -> Tuple[pd.Series, List[StrategyResult]]:
        """执行回测，返回净值序列和每日策略结果"""
        cash = self.initial_capital
        holdings: Dict[str, int] = {}
        nav_history = []
        results = []

        # 初始化净值为初始资金
        current_nav = cash
        last_date = None

        # 遍历所有交易日
        all_days = self.calendar.get_trading_days(self.start_date, self.end_date)
        rebalance_iter = iter(self.rebalance_dates)
        next_rebalance = next(rebalance_iter, None)

        for today in all_days:
            # 每日收盘后，如果是调仓日则重新计算目标持仓
            if next_rebalance and today == next_rebalance:
                # 取所有启用的ETF代码
                symbols = config_loader.get_enabled_etf_codes()
                price_snapshot = self._get_price_snapshot(symbols, today)
                # 当前持仓代码（若无持仓则为 None）
                current_position = list(holdings.keys())[0] if holdings else None
                # 运行策略：默认沿用旧 StrategyEngine；研究侧可注入 candidate_strategy 真正切换实现。
                if self.candidate_strategy is None:
                    result: StrategyResult = self.engine.run(
                        trade_date=today,
                        price_data=price_snapshot,
                        current_position=current_position
                    )
                else:
                    snapshot = build_feature_snapshot(price_snapshot, benchmark_data={})
                    proposal = self.candidate_strategy.generate(
                        snapshot=snapshot,
                        current_position=current_position,
                    )
                    result = StrategyResult(
                        trade_date=today,
                        strategy_version=f"{proposal.strategy_id}_research",
                        rebalance=proposal.target_etf != current_position,
                        current_position=current_position,
                        target_position=proposal.target_etf,
                        scores=[],
                        risk_mode="normal",
                    )
                results.append(result)
                # 根据策略信号更新持仓
                target = result.target_position
                current_shares = int(holdings.get(current_position, 0)) if current_position else 0
                fill = self.simulator.rebalance(
                    current_state=PortfolioSnapshot(
                        cash=cash,
                        holding_symbol=current_position,
                        holding_shares=current_shares,
                    ),
                    target_symbol=target,
                    trade_date=today,
                )
                cash = fill.cash_after
                holdings = fill.to_holdings_dict()

                # 更新调仓日期
                next_rebalance = next(rebalance_iter, None)

            # 计算当日净值（持仓市值 + 现金）
            daily_value = cash
            for sym, shares in holdings.items():
                # 使用当日收盘价
                df = self.price_repo.get_price_range(sym, today, today)
                if not df.empty:
                    close_price = df.iloc[0]['close']
                    daily_value += shares * close_price
            nav_history.append(daily_value)
            last_date = today

        # 创建 Series
        nav_series = pd.Series(data=nav_history, index=self.calendar.get_trading_days(self.start_date, self.end_date))

        if persist_run:
            backtest_run = BacktestRun(
                strategy_name=self.candidate_strategy.strategy_id if self.candidate_strategy else self.config.name,
                parameter_snapshot=self.config.model_dump(),
                start_date=self.start_date,
                end_date=self.end_date,
                annual_return=self._calc_annual_return(nav_series),
                max_drawdown=self._calc_max_drawdown(nav_series),
                sharpe=self._calc_sharpe(nav_series),
                turnover=self.fee_rate,  # 简化：仅使用手续费率作为 turnover 标记
            )
            self.backtest_repo.save_run(backtest_run)
        logger.info("Backtest completed")
        return nav_series, results

    # ----------------- 评价指标实现 -----------------
    def _calc_annual_return(self, nav: pd.Series) -> float:
        total_days = (nav.index[-1] - nav.index[0]).days
        if total_days == 0:
            return 0.0
        total_return = nav.iloc[-1] / nav.iloc[0] - 1
        return (1 + total_return) ** (365 / total_days) - 1

    def _calc_max_drawdown(self, nav: pd.Series) -> float:
        roll_max = nav.cummax()
        drawdown = (nav - roll_max) / roll_max
        return drawdown.min()

    def _calc_sharpe(self, nav: pd.Series, risk_free: float = 0.03) -> float:
        # 计算日收益率
        returns = nav.pct_change().dropna()
        if returns.empty:
            return 0.0
        excess = returns - risk_free / 252
        return excess.mean() / excess.std() * np.sqrt(252)

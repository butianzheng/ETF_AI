"""回测参数比较模块（comparator.py）

用于批量跑不同参数组合的回测，并返回对比表格。
"""
from copy import deepcopy
from datetime import date, timedelta
from typing import List, Dict, Tuple
import pandas as pd

from src.core.config import config_loader, StrategyConfig
from src.backtest.engine import SimpleBacktestEngine
from src.backtest.evaluator import evaluate_backtest
from src.storage.models import BacktestRun
from src.storage.repositories import BacktestRepository
from src.core.logger import get_logger

logger = get_logger(__name__)


def _apply_overrides(base_cfg: StrategyConfig, overrides: Dict) -> StrategyConfig:
    """在基准配置上应用参数覆盖，返回新的 StrategyConfig 实例"""
    # 将原对象转换为 dict，深拷贝后更新
    cfg_dict = deepcopy(base_cfg.model_dump())
    # 递归更新字典
    def _update(d, u):
        for k, v in u.items():
            if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                _update(d[k], v)
            else:
                d[k] = v
    _update(cfg_dict, overrides)
    return StrategyConfig(**cfg_dict)


def compare_params(
    param_overrides_list: List[Dict],
    start_date: date,
    end_date: date,
    initial_capital: float = 100000.0,
    fee_rate: float = 0.001
) -> pd.DataFrame:
    """批量运行回测并返回对比结果

    Args:
        param_overrides_list: 每个元素为参数覆盖 dict，例如
            [{"score_formula": {"return_20_weight": 0.6, "return_60_weight": 0.4}}, ...]
        start_date: 回测起始日期
        end_date: 回测结束日期
        initial_capital: 初始本金
        fee_rate: 手续费率（统一）

    Returns:
        DataFrame, 每行对应一次回测，列包括参数描述和指标
    """
    base_cfg = config_loader.load_strategy_config()
    repo = BacktestRepository()
    rows = []

    for idx, overrides in enumerate(param_overrides_list, start=1):
        cfg = _apply_overrides(base_cfg, overrides)
        logger.info(f"Running backtest #{idx} with overrides: {overrides}")
        engine = SimpleBacktestEngine(
            config=cfg,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            fee_rate=fee_rate
        )
        nav_series, _ = engine.run(persist_run=False)
        # 这里暂时不统计具体交易次数，设为 0
        metrics = evaluate_backtest(nav_series, trades=0)
        # 合并参数描述（简单 stringify）
        param_desc = ", ".join([f"{k}={v}" for k, v in overrides.items()])
        row = {
            "run_id": idx,
            "param_desc": param_desc,
            **metrics
        }
        rows.append(row)
        # 保存回测记录（可选）
        backtest_run = BacktestRun(
            strategy_name=cfg.name,
            parameter_snapshot=cfg.model_dump(),
            start_date=start_date,
            end_date=end_date,
            annual_return=metrics["annual_return"],
            max_drawdown=metrics["max_drawdown"],
            sharpe=metrics["sharpe"],
            turnover=metrics["turnover"]
        )
        repo.save_run(backtest_run)

    df = pd.DataFrame(rows)
    # 按年化收益降序排列
    df = df.sort_values(by="annual_return", ascending=False).reset_index(drop=True)
    return df

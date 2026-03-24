"""研究侧候选策略注册表。"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Type

from src.core.config import StrategyConfig
from src.strategy.candidates.base import BaseCandidateStrategy
from src.strategy.candidates.risk_adjusted_momentum import RiskAdjustedMomentumStrategy
from src.strategy.candidates.trend_momentum import TrendMomentumStrategy

STRATEGY_REGISTRY: Dict[str, Type[BaseCandidateStrategy]] = {
    "trend_momentum": TrendMomentumStrategy,
    "risk_adjusted_momentum": RiskAdjustedMomentumStrategy,
}


def split_candidate_overrides(overrides: Dict[str, Any] | None) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """拆分配置覆盖与策略构造参数。"""
    normalized = deepcopy(overrides or {})
    strategy_params = normalized.pop("strategy_params", {}) or {}
    if not isinstance(strategy_params, dict):
        raise ValueError("overrides.strategy_params must be a dict")
    return normalized, strategy_params


def build_candidate_strategy(
    strategy_id: str,
    strategy_config: StrategyConfig,
    strategy_params: Dict[str, Any] | None = None,
) -> BaseCandidateStrategy:
    """按注册表实例化候选策略。"""
    strategy_cls = STRATEGY_REGISTRY.get(strategy_id)
    if strategy_cls is None:
        raise ValueError(f"unsupported strategy_id: {strategy_id}")

    kwargs: Dict[str, Any] = {
        "return_20_weight": strategy_config.score_formula.return_20_weight,
        "return_60_weight": strategy_config.score_formula.return_60_weight,
        "allow_cash": strategy_config.allow_cash,
        "trend_filter_enabled": strategy_config.trend_filter.enabled,
        "trend_filter_ma_period": strategy_config.trend_filter.ma_period,
        "trend_filter_ma_type": strategy_config.trend_filter.ma_type,
    }
    if strategy_params:
        kwargs.update(strategy_params)
    return strategy_cls(**kwargs)

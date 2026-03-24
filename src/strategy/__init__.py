"""策略模块对外导出。"""

from src.strategy.candidates import BaseCandidateStrategy
from src.strategy.engine import StrategyEngine, StrategyResult
from src.strategy.features import FeatureSnapshot, SymbolFeatures, build_feature_snapshot
from src.strategy.momentum import MomentumCalculator
from src.strategy.proposal import StrategyProposal
from src.strategy.selector import PositionSelector
from src.strategy.trend_filter import TrendFilter

__all__ = [
    "BaseCandidateStrategy",
    "FeatureSnapshot",
    "MomentumCalculator",
    "PositionSelector",
    "StrategyEngine",
    "StrategyProposal",
    "StrategyResult",
    "SymbolFeatures",
    "TrendFilter",
    "build_feature_snapshot",
]

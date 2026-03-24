"""候选策略抽象基类。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.strategy.features import FeatureSnapshot
from src.strategy.proposal import StrategyProposal


class BaseCandidateStrategy(ABC):
    """候选策略最小接口。"""

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """返回策略唯一标识。"""

    @abstractmethod
    def generate(
        self,
        snapshot: FeatureSnapshot,
        current_position: str | None = None,
    ) -> StrategyProposal:
        """根据特征快照输出统一提案。"""

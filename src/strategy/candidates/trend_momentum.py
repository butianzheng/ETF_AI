"""趋势动量候选策略。"""
from __future__ import annotations

from src.strategy.candidates.base import BaseCandidateStrategy
from src.strategy.features import FeatureSnapshot, SymbolFeatures
from src.strategy.proposal import StrategyProposal


class TrendMomentumStrategy(BaseCandidateStrategy):
    """基于 20/60 动量与 MA120 趋势过滤的单标的策略。"""

    @property
    def strategy_id(self) -> str:
        return "trend_momentum"

    def __init__(
        self,
        return_20_weight: float = 0.5,
        return_60_weight: float = 0.5,
        allow_cash: bool = True,
        trend_filter_enabled: bool = True,
        trend_filter_ma_period: int = 120,
        trend_filter_ma_type: str = "sma",
    ):
        self.return_20_weight = return_20_weight
        self.return_60_weight = return_60_weight
        self.allow_cash = allow_cash
        self.trend_filter_enabled = trend_filter_enabled
        self.trend_filter_ma_period = trend_filter_ma_period
        self.trend_filter_ma_type = trend_filter_ma_type
        self._validate_trend_filter_config()

    def _validate_trend_filter_config(self) -> None:
        if not self.trend_filter_enabled:
            return
        if self.trend_filter_ma_period == 120 and self.trend_filter_ma_type == "sma":
            return
        raise ValueError(
            "TrendMomentumStrategy only supports trend_filter enabled with ma_period=120 and ma_type='sma' "
            f"for now, got ma_period={self.trend_filter_ma_period}, ma_type={self.trend_filter_ma_type}"
        )

    def _score_symbol(self, features: SymbolFeatures) -> float | None:
        if features.momentum_20 is None or features.momentum_60 is None:
            return None
        return self.return_20_weight * features.momentum_20 + self.return_60_weight * features.momentum_60

    def trend_passed(self, features: SymbolFeatures) -> bool:
        if not self.trend_filter_enabled:
            return True
        return (features.ma_distance_120 or 0.0) > 0

    def generate(
        self,
        snapshot: FeatureSnapshot,
        current_position: str | None = None,
    ) -> StrategyProposal:
        reason_codes: list[str] = []
        ranked: list[tuple[str, float, bool]] = []

        for symbol, features in snapshot.by_symbol.items():
            score = self._score_symbol(features)
            if score is None:
                continue
            trend_passed = self.trend_passed(features)
            ranked.append((symbol, score, trend_passed))

        ranked.sort(key=lambda item: item[1], reverse=True)
        qualified = [item for item in ranked if item[2]]

        target_etf: str | None
        score = 0.0
        confidence = 0.0

        if qualified:
            target_etf, score, _ = qualified[0]
            confidence = max(0.0, min(1.0, abs(score)))
            reason_codes.append("TOP_SCORE_SELECTED")
        elif ranked:
            reason_codes.append("TREND_FILTER_FAILED")
            if self.allow_cash:
                target_etf = None
                score = ranked[0][1]
                confidence = 0.5
                reason_codes.append("MOVE_TO_CASH")
            else:
                target_etf, score, _ = ranked[0]
                confidence = max(0.0, min(1.0, abs(score)))
                reason_codes.append("TOP_SCORE_SELECTED")
        else:
            target_etf = None
            reason_codes.append("NO_VALID_CANDIDATE")
            if self.allow_cash:
                reason_codes.append("MOVE_TO_CASH")

        if target_etf == current_position:
            reason_codes.append("HOLD_CURRENT")
        else:
            reason_codes.append("REBALANCE_REQUIRED")

        return StrategyProposal(
            strategy_id=self.strategy_id,
            trade_date=snapshot.trade_date,
            target_etf=target_etf,
            score=score,
            confidence=confidence,
            reason_codes=reason_codes,
        )

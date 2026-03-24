from __future__ import annotations

from datetime import date

import pytest

from src.strategy.candidates.risk_adjusted_momentum import RiskAdjustedMomentumStrategy
from src.strategy.features import FeatureSnapshot, SymbolFeatures


def test_risk_adjusted_strategy_penalizes_high_vol_symbol():
    snapshot = FeatureSnapshot(
        trade_date=date(2026, 3, 11),
        by_symbol={
            "510500": SymbolFeatures(momentum_20=0.15, momentum_60=0.12, volatility_20=0.16, ma_distance_120=0.02),
            "515180": SymbolFeatures(momentum_20=0.10, momentum_60=0.09, volatility_20=0.02, ma_distance_120=0.03),
        },
    )
    strategy = RiskAdjustedMomentumStrategy(volatility_penalty_weight=0.6)

    proposal = strategy.generate(snapshot, current_position=None)

    assert proposal.target_etf == "515180"
    assert proposal.strategy_id == "risk_adjusted_momentum"


def test_risk_adjusted_strategy_raises_for_unsupported_trend_filter_config():
    with pytest.raises(ValueError, match="only supports"):
        RiskAdjustedMomentumStrategy(
            trend_filter_enabled=True,
            trend_filter_ma_period=90,
            trend_filter_ma_type="sma",
        )

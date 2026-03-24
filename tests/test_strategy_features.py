from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.strategy.candidates import BaseCandidateStrategy
from src.strategy.features import FeatureSnapshot, SymbolFeatures, build_feature_snapshot
from src.strategy.proposal import StrategyProposal


def _build_price_series(values: list[float], end: str = "2026-03-20") -> pd.DataFrame:
    trade_dates = pd.date_range(end=end, periods=len(values), freq="B")
    return pd.DataFrame({"close": values}, index=trade_dates)


def _build_price_series_with_trade_date_column(values: list[float], end: str = "2026-03-20") -> pd.DataFrame:
    trade_dates = pd.date_range(end=end, periods=len(values), freq="B")
    return pd.DataFrame({"trade_date": trade_dates, "close": values})


def test_build_feature_snapshot_returns_expected_metrics():
    price_data = {
        "510500": _build_price_series([100 + i * 0.4 for i in range(130)]),
        "159949": _build_price_series([100 - i * 0.2 for i in range(130)]),
    }
    benchmark_data = {"000300": _build_price_series([3000 + i for i in range(130)])}

    snapshot = build_feature_snapshot(price_data, benchmark_data)

    assert isinstance(snapshot, FeatureSnapshot)
    assert snapshot.trade_date == date(2026, 3, 20)
    assert snapshot.by_symbol["510500"].momentum_60 > 0
    assert "volatility_20" in snapshot.by_symbol["510500"].model_dump()
    assert isinstance(snapshot.by_symbol["159949"], SymbolFeatures)


def test_build_feature_snapshot_supports_trade_date_column():
    price_data = {
        "510500": _build_price_series_with_trade_date_column([100 + i * 0.3 for i in range(130)], end="2026-03-23"),
    }

    snapshot = build_feature_snapshot(price_data, benchmark_data={})

    assert snapshot.trade_date == date(2026, 3, 23)
    assert snapshot.by_symbol["510500"].momentum_60 is not None


def test_strategy_proposal_uses_independent_default_lists():
    proposal_1 = StrategyProposal(
        strategy_id="trend_momentum",
        trade_date=date(2026, 3, 20),
        target_etf="510500",
        score=0.88,
        confidence=0.73,
    )
    proposal_2 = StrategyProposal(
        strategy_id="risk_adjusted_momentum",
        trade_date=date(2026, 3, 20),
        target_etf=None,
        score=0.42,
        confidence=0.6,
    )

    proposal_1.risk_flags.append("high_volatility")
    assert proposal_2.risk_flags == []
    assert proposal_1.reason_codes == []


def test_base_candidate_strategy_exposes_minimal_interface():
    class DummyStrategy(BaseCandidateStrategy):
        @property
        def strategy_id(self) -> str:
            return "dummy"

        def generate(
            self,
            snapshot: FeatureSnapshot,
            current_position: str | None = None,
        ) -> StrategyProposal:
            return StrategyProposal(
                strategy_id=self.strategy_id,
                trade_date=snapshot.trade_date,
                target_etf=current_position,
                score=0.0,
                confidence=0.0,
                reason_codes=["NO_SIGNAL"],
            )

    snapshot = FeatureSnapshot(trade_date=date(2026, 3, 20), by_symbol={})
    proposal = DummyStrategy().generate(snapshot, current_position="510500")
    assert proposal.strategy_id == "dummy"
    assert proposal.target_etf == "510500"
    assert proposal.reason_codes == ["NO_SIGNAL"]


def test_build_feature_snapshot_raises_when_symbol_dates_mismatch():
    price_data = {
        "510500": _build_price_series([100 + i * 0.2 for i in range(130)], end="2026-03-20"),
        "159949": _build_price_series([100 + i * 0.1 for i in range(130)], end="2026-03-19"),
    }

    with pytest.raises(ValueError, match="trade_date"):
        build_feature_snapshot(price_data, benchmark_data={})


def test_build_feature_snapshot_raises_when_no_valid_trade_date():
    price_data = {
        "510500": pd.DataFrame({"close": [1.0, 1.1, 1.2]}, index=[None, None, None]),
    }

    with pytest.raises(ValueError, match="trade_date"):
        build_feature_snapshot(price_data, benchmark_data={})

from datetime import date

import pandas as pd
import pytest

from src.core.config import ConfigLoader
from src.core.config import GovernanceRegimeGateConfig
from src.governance import regime_gate
from src.governance.regime_gate import evaluate_regime_gate, resolve_current_regime
from src.research.regime import RegimeSnapshot


def gate_config() -> GovernanceRegimeGateConfig:
    return GovernanceRegimeGateConfig(
        enabled=True,
        min_appearances=2,
        min_avg_observation_count=20.0,
    )


def build_snapshot(regime_label: str, reason_codes: list[str] | None = None) -> RegimeSnapshot:
    return RegimeSnapshot(
        trade_date=date(2026, 3, 24),
        regime_label=regime_label,  # type: ignore[arg-type]
        regime_score=0.0,
        reason_codes=reason_codes or [],
        metrics_snapshot={"coverage": 5},
    )


def _build_price_frame(closes: list[float], start_date: str = "2025-01-01") -> pd.DataFrame:
    trade_dates = pd.bdate_range(start=start_date, periods=len(closes))
    return pd.DataFrame({"trade_date": trade_dates, "close": closes})


def make_risk_off_price_data() -> dict[str, pd.DataFrame]:
    base = [100.0] * 90
    tail_a = [100.0, 96.0, 99.0, 93.0, 95.0, 89.0, 91.0, 84.0, 86.0, 80.0] * 5
    tail_b = [100.0, 97.0, 98.0, 92.0, 94.0, 88.0, 90.0, 85.0, 84.0, 79.0] * 5
    tail_c = [100.0, 99.0, 97.0, 96.0, 93.0, 91.0, 89.0, 87.0, 85.0, 83.0] * 5
    return {
        "510300": _build_price_frame(base + tail_a),
        "510500": _build_price_frame(base + tail_b),
        "159915": _build_price_frame(base + tail_c),
    }


def summary_with_candidate_regimes() -> dict:
    return {
        "candidate_regime_leaderboard": [
            {
                "strategy_id": "trend_momentum",
                "regime_label": "risk_on",
                "appearances": 4,
                "avg_observation_count": 60.0,
                "avg_annual_return": 0.18,
                "avg_sharpe": 1.2,
            },
            {
                "strategy_id": "trend_momentum",
                "regime_label": "neutral",
                "appearances": 3,
                "avg_observation_count": 45.0,
                "avg_annual_return": 0.03,
                "avg_sharpe": 0.4,
            },
            {
                "strategy_id": "trend_momentum",
                "regime_label": "risk_off",
                "appearances": 3,
                "avg_observation_count": 50.0,
                "avg_annual_return": -0.08,
                "avg_sharpe": -0.3,
            },
            {
                "strategy_id": "mean_reversion",
                "regime_label": "risk_off",
                "appearances": 4,
                "avg_observation_count": 55.0,
                "avg_annual_return": 0.02,
                "avg_sharpe": 0.1,
            },
        ]
    }


def summary_with_single_risk_off_sample() -> dict:
    return {
        "candidate_regime_leaderboard": [
            {
                "strategy_id": "trend_momentum",
                "regime_label": "risk_on",
                "appearances": 4,
                "avg_observation_count": 60.0,
                "avg_annual_return": 0.18,
                "avg_sharpe": 1.2,
            },
            {
                "strategy_id": "trend_momentum",
                "regime_label": "risk_off",
                "appearances": 1,
                "avg_observation_count": 8.0,
                "avg_annual_return": -0.15,
                "avg_sharpe": -0.5,
            },
        ]
    }


def summary_with_comparison_insufficient() -> dict:
    return {
        "candidate_regime_leaderboard": [
            {
                "strategy_id": "trend_momentum",
                "regime_label": "risk_off",
                "appearances": 4,
                "avg_observation_count": 30.0,
                "avg_annual_return": -0.03,
                "avg_sharpe": -0.1,
            },
            {
                "strategy_id": "trend_momentum",
                "regime_label": "risk_on",
                "appearances": 1,
                "avg_observation_count": 5.0,
                "avg_annual_return": 0.2,
                "avg_sharpe": 1.1,
            },
        ]
    }


def summary_with_missing_sharpe_in_worst_regime() -> dict:
    return {
        "candidate_regime_leaderboard": [
            {
                "strategy_id": "trend_momentum",
                "regime_label": "risk_off",
                "appearances": 3,
                "avg_observation_count": 30.0,
                "avg_annual_return": -0.12,
            },
            {
                "strategy_id": "trend_momentum",
                "regime_label": "risk_on",
                "appearances": 4,
                "avg_observation_count": 60.0,
                "avg_annual_return": 0.2,
                "avg_sharpe": 1.1,
            },
        ]
    }


def summary_with_tied_worst_regimes() -> dict:
    return {
        "candidate_regime_leaderboard": [
            {
                "strategy_id": "trend_momentum",
                "regime_label": "neutral",
                "appearances": 3,
                "avg_observation_count": 40.0,
                "avg_annual_return": -0.12,
                "avg_sharpe": -0.4,
            },
            {
                "strategy_id": "trend_momentum",
                "regime_label": "risk_off",
                "appearances": 3,
                "avg_observation_count": 45.0,
                "avg_annual_return": -0.12,
                "avg_sharpe": -0.2,
            },
            {
                "strategy_id": "trend_momentum",
                "regime_label": "risk_on",
                "appearances": 4,
                "avg_observation_count": 60.0,
                "avg_annual_return": 0.16,
                "avg_sharpe": 1.0,
            },
        ]
    }


def summary_with_missing_current_regime_stats() -> dict:
    return {
        "candidate_regime_leaderboard": [
            {
                "strategy_id": "trend_momentum",
                "regime_label": "risk_on",
                "appearances": 4,
                "avg_observation_count": 60.0,
                "avg_annual_return": 0.18,
                "avg_sharpe": 1.2,
            },
            {
                "strategy_id": "trend_momentum",
                "regime_label": "risk_off",
                "appearances": 3,
                "avg_observation_count": 50.0,
                "avg_annual_return": -0.08,
                "avg_sharpe": -0.3,
            },
        ]
    }


def test_regime_gate_blocks_when_selected_strategy_is_in_proven_bad_regime():
    result = evaluate_regime_gate(
        summary=summary_with_candidate_regimes(),
        selected_strategy_id="trend_momentum",
        current_regime_snapshot=build_snapshot("risk_off"),
        gate_config=gate_config(),
    )

    assert result.gate_status == "blocked"
    assert result.blocked_reason == "SELECTED_STRATEGY_REGIME_MISMATCH"


def test_regime_gate_skips_when_current_regime_sample_is_insufficient():
    result = evaluate_regime_gate(
        summary=summary_with_single_risk_off_sample(),
        selected_strategy_id="trend_momentum",
        current_regime_snapshot=build_snapshot("risk_off"),
        gate_config=gate_config(),
    )

    assert result.gate_status == "skipped"
    assert result.skip_reason == "SELECTED_STRATEGY_REGIME_SAMPLE_INSUFFICIENT"


def test_regime_gate_skips_when_current_regime_is_uncertain():
    result = evaluate_regime_gate(
        summary=summary_with_candidate_regimes(),
        selected_strategy_id="trend_momentum",
        current_regime_snapshot=build_snapshot("risk_off", reason_codes=["INSUFFICIENT_POOL_COVERAGE"]),
        gate_config=gate_config(),
    )

    assert result.gate_status == "skipped"
    assert result.skip_reason == "CURRENT_REGIME_UNCERTAIN"


def test_resolve_current_regime_passes_as_of_date_to_injected_loader():
    received: dict[str, object] = {}

    def injected_loader(*, as_of_date: date, lookback_days: int) -> dict[str, pd.DataFrame]:
        received["as_of_date"] = as_of_date
        received["lookback_days"] = lookback_days
        return make_risk_off_price_data()

    snapshot = resolve_current_regime(
        as_of_date=date(2026, 3, 24),
        load_price_data=injected_loader,
        regime_config=ConfigLoader().load_research_config().regime,
        lookback_days=365,
    )

    assert snapshot is not None
    assert snapshot.regime_label == "risk_off"
    assert received["as_of_date"] == date(2026, 3, 24)
    assert received["lookback_days"] == 365


def test_resolve_current_regime_clamps_lookback_days_for_injected_loader():
    received: dict[str, object] = {}

    def injected_loader(*, as_of_date: date, lookback_days: int) -> dict[str, pd.DataFrame]:
        received["as_of_date"] = as_of_date
        received["lookback_days"] = lookback_days
        return make_risk_off_price_data()

    snapshot = resolve_current_regime(
        as_of_date=date(2026, 3, 24),
        load_price_data=injected_loader,
        regime_config=ConfigLoader().load_research_config().regime,
        lookback_days=30,
    )

    assert snapshot is not None
    assert snapshot.regime_label == "risk_off"
    assert received["as_of_date"] == date(2026, 3, 24)
    assert received["lookback_days"] == 240


def test_resolve_current_regime_returns_none_when_no_snapshot():
    def injected_loader(*, as_of_date: date, lookback_days: int) -> dict[str, pd.DataFrame]:
        _ = as_of_date
        _ = lookback_days
        return {}

    snapshot = resolve_current_regime(
        as_of_date=date(2026, 3, 24),
        load_price_data=injected_loader,
        regime_config=ConfigLoader().load_research_config().regime,
        lookback_days=365,
    )

    assert snapshot is None


def test_load_price_data_for_regime_skips_failed_symbol(monkeypatch: pytest.MonkeyPatch):
    class StubETF:
        def __init__(self, code: str, enabled: bool = True):
            self.code = code
            self.enabled = enabled

    class StubConfigLoader:
        def load_etf_pool(self):
            return [StubETF("510300"), StubETF("159915")]

    class StubFetcher:
        def fetch_etf_daily(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
            if symbol == "510300":
                raise RuntimeError("boom")
            return pd.DataFrame(
                {
                    "trade_date": pd.bdate_range(start="2025-01-01", periods=5),
                    "close": [1, 2, 3, 4, 5],
                }
            )

    monkeypatch.setattr(regime_gate, "ConfigLoader", StubConfigLoader)
    monkeypatch.setattr(regime_gate, "DataFetcher", StubFetcher)

    price_data = regime_gate._load_price_data_for_regime(date(2026, 3, 24), 365)

    assert "510300" not in price_data
    assert "159915" in price_data


def test_load_price_data_for_regime_keeps_empty_symbol_without_error(monkeypatch: pytest.MonkeyPatch):
    class StubETF:
        def __init__(self, code: str, enabled: bool = True):
            self.code = code
            self.enabled = enabled

    class StubConfigLoader:
        def load_etf_pool(self):
            return [StubETF("510300"), StubETF("159915")]

    class StubFetcher:
        def fetch_etf_daily(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
            if symbol == "510300":
                return pd.DataFrame()
            return pd.DataFrame(
                {
                    "trade_date": pd.bdate_range(start="2025-01-01", periods=5),
                    "close": [1, 2, 3, 4, 5],
                }
            )

    monkeypatch.setattr(regime_gate, "ConfigLoader", StubConfigLoader)
    monkeypatch.setattr(regime_gate, "DataFetcher", StubFetcher)

    price_data = regime_gate._load_price_data_for_regime(date(2026, 3, 24), 365)

    assert "510300" in price_data
    assert price_data["510300"].empty
    assert set(["trade_date", "close"]).issubset(set(price_data["510300"].columns))
    assert "159915" in price_data


def test_regime_gate_skips_when_selected_strategy_regime_stats_missing():
    result = evaluate_regime_gate(
        summary=summary_with_missing_current_regime_stats(),
        selected_strategy_id="trend_momentum",
        current_regime_snapshot=build_snapshot("neutral"),
        gate_config=gate_config(),
    )

    assert result.gate_status == "skipped"
    assert result.skip_reason == "SELECTED_STRATEGY_REGIME_STATS_MISSING"


def test_regime_gate_skips_when_comparison_rows_are_insufficient():
    result = evaluate_regime_gate(
        summary=summary_with_comparison_insufficient(),
        selected_strategy_id="trend_momentum",
        current_regime_snapshot=build_snapshot("risk_off"),
        gate_config=gate_config(),
    )

    assert result.gate_status == "skipped"
    assert result.skip_reason == "SELECTED_STRATEGY_REGIME_COMPARISON_INSUFFICIENT"


def test_regime_gate_passes_when_current_regime_is_not_the_worst_state():
    result = evaluate_regime_gate(
        summary=summary_with_candidate_regimes(),
        selected_strategy_id="trend_momentum",
        current_regime_snapshot=build_snapshot("risk_on"),
        gate_config=gate_config(),
    )

    assert result.gate_status == "pass"
    assert result.blocked_reason is None


def test_regime_gate_does_not_block_when_worst_regime_has_missing_sharpe():
    result = evaluate_regime_gate(
        summary=summary_with_missing_sharpe_in_worst_regime(),
        selected_strategy_id="trend_momentum",
        current_regime_snapshot=build_snapshot("risk_off"),
        gate_config=gate_config(),
    )

    assert result.gate_status == "pass"
    assert result.blocked_reason is None


def test_regime_gate_blocks_when_current_regime_ties_for_worst_annual_return():
    result = evaluate_regime_gate(
        summary=summary_with_tied_worst_regimes(),
        selected_strategy_id="trend_momentum",
        current_regime_snapshot=build_snapshot("risk_off"),
        gate_config=gate_config(),
    )

    assert result.gate_status == "blocked"
    assert result.blocked_reason == "SELECTED_STRATEGY_REGIME_MISMATCH"


def test_regime_gate_skips_when_current_regime_conflicting_rules():
    result = evaluate_regime_gate(
        summary=summary_with_candidate_regimes(),
        selected_strategy_id="trend_momentum",
        current_regime_snapshot=build_snapshot("risk_off", reason_codes=["CONFLICTING_RULES"]),
        gate_config=gate_config(),
    )

    assert result.gate_status == "skipped"
    assert result.skip_reason == "CURRENT_REGIME_UNCERTAIN"

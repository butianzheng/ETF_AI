from datetime import date

from src.core.config import GovernanceRegimeGateConfig
from src.governance.regime_gate import evaluate_regime_gate
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

"""Regime gate 纯判定逻辑。"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from src.core.config import GovernanceRegimeGateConfig
from src.research.regime import RegimeSnapshot


UNCERTAIN_REASON_CODES = {"INSUFFICIENT_POOL_COVERAGE", "CONFLICTING_RULES"}


@dataclass(frozen=True)
class RegimeGateResult:
    gate_status: Literal["pass", "blocked", "skipped"]
    blocked_reason: str | None
    skip_reason: str | None
    current_regime: dict[str, Any]
    current_regime_stats: dict[str, Any] | None
    worst_regime_stats: dict[str, Any] | None


def evaluate_regime_gate(
    summary: dict[str, Any],
    selected_strategy_id: str,
    current_regime_snapshot: RegimeSnapshot,
    gate_config: GovernanceRegimeGateConfig,
) -> RegimeGateResult:
    if not gate_config.enabled:
        return _passed(current_regime_snapshot, None, None)

    strategy_rows = _selected_strategy_rows(summary, selected_strategy_id)
    current_regime_stats = _find_regime_stats(strategy_rows, current_regime_snapshot.regime_label)

    if _current_regime_is_uncertain(current_regime_snapshot):
        return _skipped(
            "CURRENT_REGIME_UNCERTAIN",
            current_regime_snapshot,
            current_regime_stats,
            None,
        )

    if current_regime_stats is None:
        return _skipped(
            "SELECTED_STRATEGY_REGIME_STATS_MISSING",
            current_regime_snapshot,
            None,
            None,
        )

    if not _sample_sufficient(current_regime_stats, gate_config):
        return _skipped(
            "SELECTED_STRATEGY_REGIME_SAMPLE_INSUFFICIENT",
            current_regime_snapshot,
            current_regime_stats,
            None,
        )

    comparison_rows = [row for row in strategy_rows if _sample_sufficient(row, gate_config)]
    if len(comparison_rows) < 2:
        return _skipped(
            "SELECTED_STRATEGY_REGIME_COMPARISON_INSUFFICIENT",
            current_regime_snapshot,
            current_regime_stats,
            None,
        )

    worst_regime_stats = min(comparison_rows, key=_avg_annual_return)
    min_annual_return = min(_avg_annual_return(row) for row in comparison_rows)
    if _is_proven_bad_regime(current_regime_stats, min_annual_return):
        return _blocked(
            "SELECTED_STRATEGY_REGIME_MISMATCH",
            current_regime_snapshot,
            current_regime_stats,
            worst_regime_stats,
        )

    return _passed(
        current_regime_snapshot,
        current_regime_stats,
        worst_regime_stats,
    )


def _selected_strategy_rows(summary: dict[str, Any], selected_strategy_id: str) -> list[dict[str, Any]]:
    leaderboard = summary.get("candidate_regime_leaderboard") or []
    return [
        dict(row)
        for row in leaderboard
        if row.get("strategy_id") == selected_strategy_id
    ]


def _find_regime_stats(
    strategy_rows: list[dict[str, Any]],
    regime_label: str,
) -> dict[str, Any] | None:
    for row in strategy_rows:
        if row.get("regime_label") == regime_label:
            return dict(row)
    return None


def _current_regime_is_uncertain(current_regime_snapshot: RegimeSnapshot) -> bool:
    return any(reason_code in UNCERTAIN_REASON_CODES for reason_code in current_regime_snapshot.reason_codes)


def _sample_sufficient(
    regime_stats: dict[str, Any],
    gate_config: GovernanceRegimeGateConfig,
) -> bool:
    appearances = int(regime_stats.get("appearances") or 0)
    avg_observation_count = float(regime_stats.get("avg_observation_count") or 0.0)
    return (
        appearances >= gate_config.min_appearances
        and avg_observation_count >= gate_config.min_avg_observation_count
    )


def _avg_annual_return(regime_stats: dict[str, Any]) -> float:
    value = regime_stats.get("avg_annual_return")
    if value is None:
        return float("inf")
    return float(value)


def _is_proven_bad_regime(
    current_regime_stats: dict[str, Any],
    min_annual_return: float,
) -> bool:
    avg_annual_return = current_regime_stats.get("avg_annual_return")
    if avg_annual_return is None:
        return False
    avg_sharpe = current_regime_stats.get("avg_sharpe")
    if avg_sharpe is None:
        return False
    current_annual_return = float(avg_annual_return)
    return current_annual_return == min_annual_return and current_annual_return <= 0.0 and float(avg_sharpe) <= 0.0


def _passed(
    current_regime_snapshot: RegimeSnapshot,
    current_regime_stats: dict[str, Any] | None,
    worst_regime_stats: dict[str, Any] | None,
) -> RegimeGateResult:
    return RegimeGateResult(
        gate_status="pass",
        blocked_reason=None,
        skip_reason=None,
        current_regime=asdict(current_regime_snapshot),
        current_regime_stats=current_regime_stats,
        worst_regime_stats=worst_regime_stats,
    )


def _blocked(
    reason: str,
    current_regime_snapshot: RegimeSnapshot,
    current_regime_stats: dict[str, Any] | None,
    worst_regime_stats: dict[str, Any] | None,
) -> RegimeGateResult:
    return RegimeGateResult(
        gate_status="blocked",
        blocked_reason=reason,
        skip_reason=None,
        current_regime=asdict(current_regime_snapshot),
        current_regime_stats=current_regime_stats,
        worst_regime_stats=worst_regime_stats,
    )


def _skipped(
    reason: str,
    current_regime_snapshot: RegimeSnapshot,
    current_regime_stats: dict[str, Any] | None,
    worst_regime_stats: dict[str, Any] | None,
) -> RegimeGateResult:
    return RegimeGateResult(
        gate_status="skipped",
        blocked_reason=None,
        skip_reason=reason,
        current_regime=asdict(current_regime_snapshot),
        current_regime_stats=current_regime_stats,
        worst_regime_stats=worst_regime_stats,
    )

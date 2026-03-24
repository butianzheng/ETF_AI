"""Regime gate 纯判定逻辑。"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any, Callable, Literal

import pandas as pd

from src.core.config import ConfigLoader, GovernanceRegimeGateConfig, ResearchRegimeConfig
from src.data.fetcher import DataFetcher
from src.data.normalizer import DataNormalizer
from src.research.regime import RegimeClassifier, RegimeSnapshot


UNCERTAIN_REASON_CODES = {"INSUFFICIENT_POOL_COVERAGE", "CONFLICTING_RULES"}
MIN_REGIME_LOOKBACK_DAYS = 240


def resolve_current_regime(
    as_of_date: date,
    regime_config: ResearchRegimeConfig,
    load_price_data: Callable[..., dict[str, pd.DataFrame]] | None = None,
    lookback_days: int = 365,
) -> RegimeSnapshot | None:
    """解析 as_of_date 对应的最新市场状态快照。"""
    effective_lookback_days = max(lookback_days, MIN_REGIME_LOOKBACK_DAYS)
    price_data = (load_price_data or _load_price_data_for_regime)(
        as_of_date=as_of_date,
        lookback_days=effective_lookback_days,
    )
    snapshots = RegimeClassifier(regime_config).classify(price_data)
    return snapshots[-1] if snapshots else None


def _load_price_data_for_regime(as_of_date: date, lookback_days: int) -> dict[str, pd.DataFrame]:
    config_loader = ConfigLoader()
    fetcher = DataFetcher()
    normalizer = DataNormalizer()
    start_date = as_of_date - timedelta(days=lookback_days)
    price_data: dict[str, pd.DataFrame] = {}
    for etf in config_loader.load_etf_pool():
        if not etf.enabled:
            continue
        try:
            raw_df = fetcher.fetch_etf_daily(
                symbol=etf.code,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=as_of_date.strftime("%Y%m%d"),
            )
        except Exception:
            continue
        if raw_df.empty:
            price_data[etf.code] = pd.DataFrame(columns=["trade_date", "close"])
            continue
        normalized_df = normalizer.normalize_price_data(raw_df)
        if normalized_df.empty and "trade_date" not in normalized_df.columns:
            price_data[etf.code] = pd.DataFrame(columns=["trade_date", "close"])
            continue
        deduped_df = normalizer.remove_duplicates(normalized_df)
        price_data[etf.code] = deduped_df
    return price_data


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

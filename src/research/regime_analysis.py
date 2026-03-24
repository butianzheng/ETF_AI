"""Regime 与样本切片分层分析。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping, Sequence

import pandas as pd

from src.backtest.evaluator import calculate_max_drawdown, evaluate_backtest
from src.research.regime import RegimeSnapshot


REGIME_LABELS = ("risk_on", "neutral", "risk_off")
SAMPLE_LABELS = ("in_sample", "out_of_sample")


def analyze_candidate_segments(
    candidate_name: str,
    nav_series: pd.Series,
    regime_snapshots: Sequence[RegimeSnapshot],
    sample_labels: dict[date, str],
    transition_window: int = 5,
) -> dict[str, Any]:
    normalized_nav = _normalize_nav_series(nav_series)
    regime_by_date = {
        snapshot.trade_date: snapshot.regime_label
        for snapshot in regime_snapshots
    }

    by_regime_metrics = {
        regime_label: _evaluate_segment(
            normalized_nav[
                [trade_date for trade_date in normalized_nav.index if regime_by_date.get(trade_date) == regime_label]
            ]
        )
        for regime_label in REGIME_LABELS
    }

    sample_metrics = {
        sample_label: _evaluate_segment(
            normalized_nav[
                [trade_date for trade_date in normalized_nav.index if sample_labels.get(trade_date) == sample_label]
            ]
        )
        for sample_label in SAMPLE_LABELS
    }

    by_regime_and_sample_metrics = {
        regime_label: {
            sample_label: _evaluate_segment(
                normalized_nav[
                    [
                        trade_date
                        for trade_date in normalized_nav.index
                        if regime_by_date.get(trade_date) == regime_label and sample_labels.get(trade_date) == sample_label
                    ]
                ]
            )
            for sample_label in SAMPLE_LABELS
        }
        for regime_label in REGIME_LABELS
    }

    return {
        "candidate_name": candidate_name,
        "overall_metrics": _evaluate_segment(normalized_nav),
        "by_regime_metrics": by_regime_metrics,
        "in_sample_metrics": sample_metrics["in_sample"],
        "out_of_sample_metrics": sample_metrics["out_of_sample"],
        "by_regime_and_sample_metrics": by_regime_and_sample_metrics,
        "regime_transition_metrics": _summarize_transitions(
            normalized_nav,
            regime_by_date,
            transition_window=transition_window,
        ),
    }


def _normalize_nav_series(nav_series: pd.Series) -> pd.Series:
    normalized = nav_series.copy()
    normalized.index = [_to_date(value) for value in normalized.index]
    normalized = normalized.sort_index()
    return normalized


def _to_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime().date()
    if isinstance(value, date):
        return value
    raise TypeError(f"unsupported trade_date type: {type(value)!r}")


def _evaluate_segment(nav_series: pd.Series) -> dict[str, float | int]:
    metrics = evaluate_backtest(nav_series, trades=0)
    metrics["observation_count"] = int(len(nav_series))
    return metrics


def _summarize_transitions(
    nav_series: pd.Series,
    regime_by_date: Mapping[date, str],
    transition_window: int,
) -> list[dict[str, Any]]:
    transition_stats: dict[str, dict[str, Any]] = {}
    ordered_dates = [trade_date for trade_date in nav_series.index if trade_date in regime_by_date]
    for idx in range(1, len(ordered_dates)):
        previous_label = regime_by_date[ordered_dates[idx - 1]]
        current_label = regime_by_date[ordered_dates[idx]]
        if previous_label == current_label:
            continue

        transition = f"{previous_label}->{current_label}"
        window = nav_series.iloc[idx : idx + transition_window]
        forward_return = _calculate_forward_return(window)
        forward_drawdown = _calculate_forward_drawdown(window)

        bucket = transition_stats.setdefault(
            transition,
            {
                "from_regime": previous_label,
                "to_regime": current_label,
                "transition": transition,
                "event_count": 0,
                "forward_returns": [],
                "forward_drawdowns": [],
            },
        )
        bucket["event_count"] += 1
        if forward_return is not None:
            bucket["forward_returns"].append(forward_return)
        if forward_drawdown is not None:
            bucket["forward_drawdowns"].append(forward_drawdown)

    return [
        {
            "from_regime": item["from_regime"],
            "to_regime": item["to_regime"],
            "transition": item["transition"],
            "event_count": item["event_count"],
            "avg_forward_return_5": _average(item["forward_returns"]),
            "avg_forward_drawdown_5": _average(item["forward_drawdowns"]),
        }
        for item in transition_stats.values()
    ]


def _calculate_forward_return(window: pd.Series) -> float | None:
    if len(window) < 2:
        return None
    return float(window.iloc[-1] / window.iloc[0] - 1.0)


def _calculate_forward_drawdown(window: pd.Series) -> float | None:
    if window.empty:
        return None
    return float(calculate_max_drawdown(window))


def _average(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return float(sum(values) / len(values))

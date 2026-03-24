from datetime import date, timedelta

import pandas as pd

from src.research.regime import RegimeSnapshot
from src.research.regime_analysis import analyze_candidate_segments
from src.research.segmentation import build_sample_split_labels


def _make_trade_dates(count: int) -> list[date]:
    start = date(2025, 1, 2)
    return [start + timedelta(days=idx) for idx in range(count)]


def _make_nav_series() -> pd.Series:
    trade_dates = _make_trade_dates(10)
    return pd.Series(
        [1.0, 1.01, 0.99, 0.97, 0.98, 1.00, 1.02, 1.01, 1.03, 1.05],
        index=trade_dates,
    )


def _make_regime_snapshots() -> list[RegimeSnapshot]:
    labels = [
        "neutral",
        "neutral",
        "risk_off",
        "risk_off",
        "risk_off",
        "risk_on",
        "risk_on",
        "neutral",
        "neutral",
        "risk_on",
    ]
    return [
        RegimeSnapshot(
            trade_date=trade_date,
            regime_label=label,
            regime_score=0.0,
            reason_codes=[],
            metrics_snapshot={"coverage": 3},
        )
        for trade_date, label in zip(_make_trade_dates(10), labels)
    ]


def test_build_sample_split_labels_uses_trade_day_ratio():
    trade_dates = _make_trade_dates(10)

    labels = build_sample_split_labels(trade_dates, in_sample_ratio=0.7)

    assert [labels[trade_date] for trade_date in trade_dates[:7]] == ["in_sample"] * 7
    assert [labels[trade_date] for trade_date in trade_dates[7:]] == ["out_of_sample"] * 3


def test_analyze_candidate_segments_returns_regime_and_sample_metrics():
    nav_series = _make_nav_series()
    analysis = analyze_candidate_segments(
        candidate_name="baseline_trend",
        nav_series=nav_series,
        regime_snapshots=_make_regime_snapshots(),
        sample_labels=build_sample_split_labels(list(nav_series.index), in_sample_ratio=0.7),
    )

    assert analysis["candidate_name"] == "baseline_trend"
    assert analysis["overall_metrics"]["observation_count"] == 10
    assert analysis["by_regime_metrics"]["risk_on"]["observation_count"] == 3
    assert analysis["in_sample_metrics"]["observation_count"] == 7
    assert analysis["out_of_sample_metrics"]["observation_count"] == 3
    assert analysis["by_regime_and_sample_metrics"]["risk_off"]["in_sample"]["observation_count"] == 3
    assert analysis["regime_transition_metrics"][0]["transition"] == "neutral->risk_off"
    assert analysis["regime_transition_metrics"][0]["event_count"] == 1
    assert "avg_forward_return_5" in analysis["regime_transition_metrics"][0]
    assert "avg_forward_drawdown_5" in analysis["regime_transition_metrics"][0]

from datetime import date

import pandas as pd

from src.core.config import ConfigLoader
from src.research.regime import RegimeClassifier


def _build_price_frame(closes: list[float], start_date: str = "2025-01-01") -> pd.DataFrame:
    trade_dates = pd.bdate_range(start=start_date, periods=len(closes))
    return pd.DataFrame({"trade_date": trade_dates, "close": closes})


def _make_risk_on_price_data() -> dict[str, pd.DataFrame]:
    base = [100.0] * 90
    tail_c = list(range(100, 121)) + list(range(119, 90, -1))
    return {
        "510300": _build_price_frame(base + list(range(101, 151))),
        "510500": _build_price_frame(base + list(range(100, 150))),
        "159915": _build_price_frame(base + tail_c),
    }


def _make_risk_off_price_data() -> dict[str, pd.DataFrame]:
    base = [100.0] * 90
    tail_a = [100.0, 96.0, 99.0, 93.0, 95.0, 89.0, 91.0, 84.0, 86.0, 80.0] * 5
    tail_b = [100.0, 97.0, 98.0, 92.0, 94.0, 88.0, 90.0, 85.0, 84.0, 79.0] * 5
    tail_c = [100.0, 99.0, 97.0, 96.0, 93.0, 91.0, 89.0, 87.0, 85.0, 83.0] * 5
    return {
        "510300": _build_price_frame(base + tail_a),
        "510500": _build_price_frame(base + tail_b),
        "159915": _build_price_frame(base + tail_c),
    }


def _make_insufficient_coverage_price_data() -> dict[str, pd.DataFrame]:
    base = [100.0] * 90
    return {
        "510300": _build_price_frame(base + list(range(101, 151))),
        "510500": _build_price_frame(base + list(range(100, 150))),
    }


def test_research_config_loads_regime_policy():
    research_config = ConfigLoader().load_research_config()

    assert research_config.regime.enabled is True
    assert research_config.regime.min_pool_coverage == 3
    assert research_config.regime.min_volatility_20 == 0.18
    assert research_config.regime.risk_on.breadth_above_ma120_min == 0.60
    assert research_config.regime.risk_off.breadth_above_ma120_max == 0.35
    assert research_config.sample_split.in_sample_ratio == 0.70


def test_regime_classifier_labels_risk_on_and_risk_off():
    classifier = RegimeClassifier(
        ConfigLoader().load_research_config().regime,
    )

    risk_on_snapshots = classifier.classify(_make_risk_on_price_data())
    assert isinstance(risk_on_snapshots, list)
    assert risk_on_snapshots
    risk_on = risk_on_snapshots[-1]
    assert risk_on.trade_date == date(2025, 7, 15)
    assert risk_on.regime_label == "risk_on"
    assert risk_on.reason_codes == []
    assert risk_on.metrics_snapshot["pool_breadth_above_ma120"] == 2 / 3
    assert -1.0 <= risk_on.regime_score <= 1.0

    risk_off_snapshots = classifier.classify(_make_risk_off_price_data())
    assert isinstance(risk_off_snapshots, list)
    assert risk_off_snapshots
    risk_off = risk_off_snapshots[-1]
    assert risk_off.trade_date == date(2025, 7, 15)
    assert risk_off.regime_label == "risk_off"
    assert risk_off.reason_codes == []
    assert risk_off.metrics_snapshot["pool_breadth_above_ma120"] == 0.0
    assert -1.0 <= risk_off.regime_score <= 1.0


def test_regime_classifier_returns_neutral_when_pool_coverage_is_insufficient():
    classifier = RegimeClassifier(
        ConfigLoader().load_research_config().regime,
    )

    snapshots = classifier.classify(_make_insufficient_coverage_price_data())
    assert isinstance(snapshots, list)
    assert snapshots

    snapshot = snapshots[-1]
    assert snapshot.trade_date == date(2025, 7, 15)
    assert snapshot.regime_label == "neutral"
    assert snapshot.reason_codes == ["INSUFFICIENT_POOL_COVERAGE"]
    assert snapshot.metrics_snapshot["coverage"] == 2
    assert snapshot.regime_score == 0.0

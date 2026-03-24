"""规则型 Regime 分类器。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Literal, Mapping

import pandas as pd

from src.core.config import ResearchRegimeConfig, ResearchRegimeRuleConfig


RegimeLabel = Literal["risk_on", "neutral", "risk_off"]
FEATURE_COLUMNS = (
    "pool_return_20",
    "pool_return_60",
    "pool_ma_distance_120",
    "pool_breadth_above_ma120",
    "pool_volatility_20",
    "pool_drawdown_60",
)


@dataclass(frozen=True)
class RegimeSnapshot:
    """聚合后的池级市场状态快照。"""

    trade_date: date
    regime_label: RegimeLabel
    regime_score: float
    reason_codes: list[str]
    metrics_snapshot: dict[str, float | int]


class RegimeClassifier:
    """基于 ETF 池横截面特征的规则分类器。"""

    def __init__(self, config: ResearchRegimeConfig):
        self.config = config

    def classify(self, price_data: dict[str, pd.DataFrame]) -> list[RegimeSnapshot]:
        feature_frame = self.build_pool_feature_frame(price_data)
        snapshots: list[RegimeSnapshot] = []
        for trade_date, row in feature_frame.iterrows():
            snapshots.append(self._classify_from_metrics(trade_date, row.to_dict()))
        return snapshots

    def build_pool_feature_frame(self, price_data: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
        feature_tables = {
            symbol: self._build_symbol_features(frame)
            for symbol, frame in price_data.items()
        }
        all_dates = sorted(
            {
                trade_date
                for features in feature_tables.values()
                for trade_date in features.index
            }
        )
        rows = []
        for trade_date in all_dates:
            valid_rows = []
            for features in feature_tables.values():
                if trade_date not in features.index:
                    continue
                values = features.loc[trade_date].to_dict()
                if self._is_valid_row(values):
                    valid_rows.append(values)
            rows.append(
                {
                    "trade_date": trade_date.date(),
                    **self._aggregate_features(valid_rows),
                }
            )

        if not rows:
            return pd.DataFrame(columns=["coverage", *FEATURE_COLUMNS])
        return pd.DataFrame(rows).set_index("trade_date")

    def _build_symbol_features(self, frame: pd.DataFrame) -> pd.DataFrame:
        normalized = frame.copy()
        if "trade_date" in normalized.columns:
            normalized["trade_date"] = pd.to_datetime(normalized["trade_date"])
            normalized = normalized.sort_values("trade_date").set_index("trade_date")
        else:
            normalized.index = pd.to_datetime(normalized.index)
            normalized = normalized.sort_index()

        close = normalized["close"].astype(float)
        returns = close.pct_change()
        feature_frame = pd.DataFrame(index=normalized.index)
        feature_frame["return_20"] = close / close.shift(20) - 1.0
        feature_frame["return_60"] = close / close.shift(60) - 1.0
        ma120 = close.rolling(120, min_periods=120).mean()
        feature_frame["ma_distance_120"] = close / ma120 - 1.0
        feature_frame["above_ma120"] = close > ma120
        feature_frame["volatility_20"] = returns.rolling(20, min_periods=20).std() * (252 ** 0.5)
        feature_frame["drawdown_60"] = close / close.rolling(60, min_periods=60).max() - 1.0
        return feature_frame

    def _classify_from_metrics(self, trade_date: date, features: Mapping[str, float | int]) -> RegimeSnapshot:
        coverage = int(features["coverage"])
        if coverage < self.config.min_pool_coverage:
            return RegimeSnapshot(
                trade_date=trade_date,
                regime_label="neutral",
                regime_score=0.0,
                reason_codes=["INSUFFICIENT_POOL_COVERAGE"],
                metrics_snapshot=features,
            )

        risk_on = self._matches_rule(features, self.config.risk_on)
        risk_off = self._matches_risk_off(features, self.config.risk_off)

        regime_label: RegimeLabel = "neutral"
        if risk_on and risk_off:
            return RegimeSnapshot(
                trade_date=trade_date,
                regime_label="neutral",
                regime_score=self._compute_regime_score(features),
                reason_codes=["CONFLICTING_RULES"],
                metrics_snapshot=features,
            )
        if risk_on and not risk_off:
            regime_label = "risk_on"
        elif risk_off and not risk_on:
            regime_label = "risk_off"

        return RegimeSnapshot(
            trade_date=trade_date,
            regime_label=regime_label,
            regime_score=self._compute_regime_score(features),
            reason_codes=[],
            metrics_snapshot=features,
        )

    def _aggregate_features(self, rows: list[Mapping[str, float | bool]]) -> dict[str, float | int]:
        coverage = len(rows)
        if not rows:
            return {
                "coverage": coverage,
                "pool_return_20": 0.0,
                "pool_return_60": 0.0,
                "pool_ma_distance_120": 0.0,
                "pool_breadth_above_ma120": 0.0,
                "pool_volatility_20": 0.0,
                "pool_drawdown_60": 0.0,
            }

        return {
            "coverage": coverage,
            "pool_return_20": float(median(float(row["return_20"]) for row in rows)),
            "pool_return_60": float(median(float(row["return_60"]) for row in rows)),
            "pool_ma_distance_120": float(median(float(row["ma_distance_120"]) for row in rows)),
            "pool_breadth_above_ma120": sum(bool(row["above_ma120"]) for row in rows) / len(rows),
            "pool_volatility_20": float(median(float(row["volatility_20"]) for row in rows)),
            "pool_drawdown_60": float(median(float(row["drawdown_60"]) for row in rows)),
        }

    def _is_valid_row(self, row: Mapping[str, float | bool | None]) -> bool:
        for key in (
            "return_20",
            "return_60",
            "ma_distance_120",
            "above_ma120",
            "volatility_20",
            "drawdown_60",
        ):
            value = row.get(key)
            if value is None or pd.isna(value):
                return False
        return True

    def _matches_rule(self, features: Mapping[str, float | int], rule: ResearchRegimeRuleConfig) -> bool:
        thresholds = {
            "pool_breadth_above_ma120": (
                rule.breadth_above_ma120_min,
                rule.breadth_above_ma120_max,
            ),
            "pool_return_20": (rule.return_20_min, rule.return_20_max),
            "pool_return_60": (rule.return_60_min, rule.return_60_max),
            "pool_drawdown_60": (rule.drawdown_60_min, rule.drawdown_60_max),
            "pool_ma_distance_120": (rule.ma_distance_120_min, rule.ma_distance_120_max),
            "pool_volatility_20": (
                self._resolve_min_volatility(rule.volatility_20_min),
                rule.volatility_20_max,
            ),
        }

        for feature_name, (min_value, max_value) in thresholds.items():
            current = float(features[feature_name])
            if min_value is not None and current < min_value:
                return False
            if max_value is not None and current > max_value:
                return False
        return True

    def _matches_risk_off(self, features: Mapping[str, float | int], rule: ResearchRegimeRuleConfig) -> bool:
        if (
            rule.breadth_above_ma120_max is not None
            and float(features["pool_breadth_above_ma120"]) <= rule.breadth_above_ma120_max
        ):
            return True

        if self._matches_threshold_group(
            features,
            {
                "pool_return_20": (None, rule.return_20_max),
                "pool_return_60": (None, rule.return_60_max),
                "pool_drawdown_60": (None, rule.drawdown_60_max),
            },
        ):
            return True

        return self._matches_threshold_group(
            features,
            {
                "pool_ma_distance_120": (None, rule.ma_distance_120_max),
                "pool_volatility_20": (
                    self._resolve_min_volatility(rule.volatility_20_min),
                    None,
                ),
            },
        )

    def _matches_threshold_group(
        self,
        features: Mapping[str, float | int],
        thresholds: Mapping[str, tuple[float | None, float | None]],
    ) -> bool:
        active_thresholds = [
            (feature_name, min_value, max_value)
            for feature_name, (min_value, max_value) in thresholds.items()
            if min_value is not None or max_value is not None
        ]
        if not active_thresholds:
            return False

        for feature_name, min_value, max_value in active_thresholds:
            current = float(features[feature_name])
            if min_value is not None and current < min_value:
                return False
            if max_value is not None and current > max_value:
                return False
        return True

    def _resolve_min_volatility(self, rule_min: float | None) -> float | None:
        if rule_min is None:
            return None
        return max(rule_min, self.config.min_volatility_20)

    def _compute_regime_score(self, features: Mapping[str, float | int]) -> float:
        score = 0.0
        score += self._clamp_component(float(features["pool_return_20"]) / 0.08)
        score += self._clamp_component(float(features["pool_return_60"]) / 0.15)
        score += self._clamp_component(float(features["pool_ma_distance_120"]) / 0.06)
        score += self._clamp_component((float(features["pool_breadth_above_ma120"]) - 0.5) / 0.25)
        score += self._clamp_component((self.config.min_volatility_20 - float(features["pool_volatility_20"])) / 0.08)
        score += self._clamp_component((float(features["pool_drawdown_60"]) + 0.10) / 0.08)
        return self._clamp_component(score / 6.0)

    def _clamp_component(self, value: float) -> float:
        return max(-1.0, min(1.0, float(value)))

"""策略特征快照。"""
from __future__ import annotations

from datetime import date
from typing import Mapping

import pandas as pd
from pydantic import BaseModel


class SymbolFeatures(BaseModel):
    """单个标的的最小特征集。"""

    momentum_20: float | None = None
    momentum_60: float | None = None
    momentum_120: float | None = None
    ma_distance_120: float | None = None
    volatility_20: float | None = None


class FeatureSnapshot(BaseModel):
    """策略特征快照。"""

    trade_date: date
    by_symbol: dict[str, SymbolFeatures]


def _calc_momentum(closes: pd.Series, period: int) -> float | None:
    if len(closes) < period + 1:
        return None
    current_price = closes.iloc[-1]
    past_price = closes.iloc[-(period + 1)]
    if pd.isna(current_price) or pd.isna(past_price) or past_price == 0:
        return None
    return float((current_price / past_price) - 1)


def _calc_ma_distance_120(closes: pd.Series) -> float | None:
    if len(closes) < 120:
        return None
    current_price = closes.iloc[-1]
    ma_120 = closes.iloc[-120:].mean()
    if pd.isna(current_price) or pd.isna(ma_120) or ma_120 == 0:
        return None
    return float((current_price / ma_120) - 1)


def _calc_volatility_20(closes: pd.Series) -> float | None:
    if len(closes) < 21:
        return None
    returns = closes.pct_change().dropna()
    if len(returns) < 20:
        return None
    return float(returns.iloc[-20:].std(ddof=0))


def _normalize_trade_date(raw: object) -> date:
    if isinstance(raw, pd.Timestamp):
        if pd.isna(raw):
            raise ValueError("invalid trade_date value")
        return raw.date()
    if isinstance(raw, date):
        return raw
    normalized = pd.Timestamp(raw)
    if pd.isna(normalized):
        raise ValueError("invalid trade_date value")
    return normalized.date()


def _extract_trade_date(frame: pd.DataFrame) -> date:
    if "trade_date" in frame.columns and len(frame["trade_date"]) > 0:
        return _normalize_trade_date(frame["trade_date"].iloc[-1])
    return _normalize_trade_date(frame.index[-1])


def build_feature_snapshot(
    price_data: Mapping[str, pd.DataFrame],
    benchmark_data: Mapping[str, pd.DataFrame] | None = None,
) -> FeatureSnapshot:
    """构建最小统一特征快照。"""
    _ = benchmark_data  # 预留后续相对指标扩展

    by_symbol: dict[str, SymbolFeatures] = {}
    symbol_trade_dates: dict[str, date] = {}

    for symbol, frame in price_data.items():
        if frame.empty or "close" not in frame.columns:
            by_symbol[symbol] = SymbolFeatures()
            continue

        closes = frame["close"]
        by_symbol[symbol] = SymbolFeatures(
            momentum_20=_calc_momentum(closes, 20),
            momentum_60=_calc_momentum(closes, 60),
            momentum_120=_calc_momentum(closes, 120),
            ma_distance_120=_calc_ma_distance_120(closes),
            volatility_20=_calc_volatility_20(closes),
        )

        symbol_trade_dates[symbol] = _extract_trade_date(frame)

    if not symbol_trade_dates:
        raise ValueError("no valid trade_date found in price_data")

    unique_trade_dates = set(symbol_trade_dates.values())
    if len(unique_trade_dates) != 1:
        raise ValueError(f"inconsistent trade_date across symbols: {symbol_trade_dates}")

    snapshot_trade_date = next(iter(unique_trade_dates))

    return FeatureSnapshot(
        trade_date=snapshot_trade_date,
        by_symbol=by_symbol,
    )

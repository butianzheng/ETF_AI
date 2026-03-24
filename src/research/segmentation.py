"""研究窗口切片工具。"""
from __future__ import annotations

from datetime import date
from typing import Literal, Sequence


SampleLabel = Literal["in_sample", "out_of_sample"]


def build_sample_split_labels(
    trade_dates: Sequence[date],
    in_sample_ratio: float = 0.7,
) -> dict[date, SampleLabel]:
    ordered_dates = sorted(dict.fromkeys(trade_dates))
    if not ordered_dates:
        return {}
    if len(ordered_dates) == 1:
        return {ordered_dates[0]: "in_sample"}

    cutoff = int(len(ordered_dates) * in_sample_ratio)
    cutoff = max(1, min(len(ordered_dates) - 1, cutoff))
    return {
        trade_date: "in_sample" if idx < cutoff else "out_of_sample"
        for idx, trade_date in enumerate(ordered_dates)
    }

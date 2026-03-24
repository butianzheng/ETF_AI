"""策略候选输出结构。"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class StrategyProposal(BaseModel):
    """候选策略统一提案。"""

    strategy_id: str
    trade_date: date
    target_etf: str | None
    score: float
    confidence: float
    risk_flags: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)

"""治理层领域模型。"""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class GovernanceDecision(BaseModel):
    """治理评审结果。"""

    id: int | None = None
    decision_date: date
    current_strategy_id: str | None
    selected_strategy_id: str
    previous_strategy_id: str | None = None
    fallback_strategy_id: str
    decision_type: Literal["keep", "switch", "fallback"]
    status: Literal["draft", "approved", "published", "rolled_back"] = "draft"
    approved_by: str | None = None
    summary_hash: str | None = None
    source_report_date: str | None = None
    review_status: Literal["pending", "ready", "blocked"] = "pending"
    blocked_reasons: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class GovernanceIncident(BaseModel):
    """治理巡检或自动化门禁发现的事件。"""

    id: int | None = None
    incident_date: date
    incident_type: Literal[
        "SUMMARY_STALE",
        "PUBLISH_COOLDOWN",
        "RISK_BREACH",
        "STRATEGY_DRIFT",
        "EXECUTION_FAILURE",
        "GOVERNANCE_STALE",
    ]
    severity: Literal["info", "warning", "critical"]
    status: Literal["open", "resolved"] = "open"
    strategy_id: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)

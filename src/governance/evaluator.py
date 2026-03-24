"""治理评估器。"""
from __future__ import annotations

from datetime import date
from typing import Any

from src.core.config import GovernanceConfig
from src.governance.models import GovernanceDecision


def _metric(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def _governance_score(candidate: dict[str, Any]) -> float:
    return (
        0.45 * _metric(candidate.get("avg_sharpe"))
        + 0.35 * _metric(candidate.get("avg_annual_return"))
        - 0.20 * abs(_metric(candidate.get("avg_max_drawdown")))
    )


def _find_candidate(summary: dict[str, Any], strategy_id: str | None) -> dict[str, Any] | None:
    if strategy_id is None:
        return None
    for candidate in summary.get("candidate_leaderboard", []):
        if candidate.get("strategy_id") == strategy_id:
            return candidate
    return None


def evaluate_governance(
    summary: dict[str, Any],
    current_strategy_id: str | None,
    policy: GovernanceConfig,
) -> GovernanceDecision:
    leaderboard = summary.get("candidate_leaderboard", [])
    decision_date = date.today()

    if not leaderboard:
        return GovernanceDecision(
            decision_date=decision_date,
            current_strategy_id=current_strategy_id,
            selected_strategy_id=policy.fallback_strategy_id,
            previous_strategy_id=current_strategy_id,
            fallback_strategy_id=policy.fallback_strategy_id,
            decision_type="fallback",
            reason_codes=["NO_CANDIDATE_DATA"],
            evidence={"report_count": summary.get("report_count", 0)},
        )

    leader = leaderboard[0]
    current_candidate = _find_candidate(summary, current_strategy_id)
    if current_strategy_id and current_candidate is None:
        return GovernanceDecision(
            decision_date=decision_date,
            current_strategy_id=current_strategy_id,
            selected_strategy_id=policy.fallback_strategy_id,
            previous_strategy_id=current_strategy_id,
            fallback_strategy_id=policy.fallback_strategy_id,
            decision_type="fallback",
            reason_codes=["CURRENT_STRATEGY_MISSING"],
            evidence={"leader_strategy_id": leader.get("strategy_id")},
        )

    if leader.get("strategy_id") == current_strategy_id:
        return GovernanceDecision(
            decision_date=decision_date,
            current_strategy_id=current_strategy_id,
            selected_strategy_id=current_strategy_id or policy.fallback_strategy_id,
            previous_strategy_id=current_strategy_id,
            fallback_strategy_id=policy.fallback_strategy_id,
            decision_type="keep",
            reason_codes=["CURRENT_STRATEGY_STILL_LEADING"],
            evidence={"governance_score": _governance_score(leader)},
        )

    if _metric(leader.get("appearances")) < policy.champion_min_appearances:
        return GovernanceDecision(
            decision_date=decision_date,
            current_strategy_id=current_strategy_id,
            selected_strategy_id=current_strategy_id or policy.fallback_strategy_id,
            previous_strategy_id=current_strategy_id,
            fallback_strategy_id=policy.fallback_strategy_id,
            decision_type="keep",
            reason_codes=["LEADER_INSUFFICIENT_APPEARANCES"],
            evidence={"leader_appearances": leader.get("appearances")},
        )

    if _metric(leader.get("top1_count")) < policy.challenger_min_top1:
        return GovernanceDecision(
            decision_date=decision_date,
            current_strategy_id=current_strategy_id,
            selected_strategy_id=current_strategy_id or policy.fallback_strategy_id,
            previous_strategy_id=current_strategy_id,
            fallback_strategy_id=policy.fallback_strategy_id,
            decision_type="keep",
            reason_codes=["LEADER_INSUFFICIENT_TOP1"],
            evidence={"leader_top1_count": leader.get("top1_count")},
        )

    leader_score = _governance_score(leader)
    current_score = _governance_score(current_candidate or {})
    score_margin = leader_score - current_score

    if score_margin < policy.challenger_min_score_margin:
        return GovernanceDecision(
            decision_date=decision_date,
            current_strategy_id=current_strategy_id,
            selected_strategy_id=current_strategy_id or policy.fallback_strategy_id,
            previous_strategy_id=current_strategy_id,
            fallback_strategy_id=policy.fallback_strategy_id,
            decision_type="keep",
            reason_codes=["LEADER_SCORE_MARGIN_TOO_SMALL"],
            evidence={
                "leader_score": leader_score,
                "current_score": current_score,
                "score_margin": score_margin,
            },
        )

    return GovernanceDecision(
        decision_date=decision_date,
        current_strategy_id=current_strategy_id,
        selected_strategy_id=leader["strategy_id"],
        previous_strategy_id=current_strategy_id,
        fallback_strategy_id=policy.fallback_strategy_id,
        decision_type="switch",
        reason_codes=["CHALLENGER_PROMOTED"],
        evidence={
            "leader_strategy_id": leader["strategy_id"],
            "leader_score": leader_score,
            "current_score": current_score,
            "score_margin": score_margin,
        },
    )

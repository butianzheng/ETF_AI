from src.core.config import GovernanceConfig


def _summary(leaderboard):
    return {
        "candidate_leaderboard": leaderboard,
        "report_count": 4,
    }


def test_evaluator_switches_when_challenger_wins_consistently():
    from src.governance.evaluator import evaluate_governance

    decision = evaluate_governance(
        summary=_summary(
            [
                {
                    "name": "risk_adjusted",
                    "strategy_id": "risk_adjusted_momentum",
                    "appearances": 4,
                    "top1_count": 3,
                    "avg_annual_return": 0.24,
                    "avg_sharpe": 1.42,
                    "avg_max_drawdown": -0.08,
                },
                {
                    "name": "baseline",
                    "strategy_id": "trend_momentum",
                    "appearances": 4,
                    "top1_count": 1,
                    "avg_annual_return": 0.16,
                    "avg_sharpe": 1.05,
                    "avg_max_drawdown": -0.10,
                },
            ]
        ),
        current_strategy_id="trend_momentum",
        policy=GovernanceConfig(),
    )

    assert decision.decision_type == "switch"
    assert decision.selected_strategy_id == "risk_adjusted_momentum"
    assert decision.status == "draft"


def test_evaluator_keeps_current_when_leader_lacks_minimum_evidence():
    from src.governance.evaluator import evaluate_governance

    decision = evaluate_governance(
        summary=_summary(
            [
                {
                    "name": "risk_adjusted",
                    "strategy_id": "risk_adjusted_momentum",
                    "appearances": 2,
                    "top1_count": 2,
                    "avg_annual_return": 0.25,
                    "avg_sharpe": 1.45,
                    "avg_max_drawdown": -0.08,
                },
                {
                    "name": "baseline",
                    "strategy_id": "trend_momentum",
                    "appearances": 4,
                    "top1_count": 2,
                    "avg_annual_return": 0.17,
                    "avg_sharpe": 1.02,
                    "avg_max_drawdown": -0.09,
                },
            ]
        ),
        current_strategy_id="trend_momentum",
        policy=GovernanceConfig(),
    )

    assert decision.decision_type == "keep"
    assert decision.selected_strategy_id == "trend_momentum"


def test_evaluator_falls_back_when_current_strategy_is_missing():
    from src.governance.evaluator import evaluate_governance

    decision = evaluate_governance(
        summary=_summary(
            [
                {
                    "name": "risk_adjusted",
                    "strategy_id": "risk_adjusted_momentum",
                    "appearances": 4,
                    "top1_count": 3,
                    "avg_annual_return": 0.20,
                    "avg_sharpe": 1.20,
                    "avg_max_drawdown": -0.15,
                }
            ]
        ),
        current_strategy_id="retired_strategy",
        policy=GovernanceConfig(),
    )

    assert decision.decision_type == "fallback"
    assert decision.selected_strategy_id == "trend_momentum"

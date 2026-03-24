from datetime import date

from src.core.config import config_loader


def test_strategy_config_loads_governance_policy():
    strategy_config = config_loader.load_strategy_config()

    assert strategy_config.governance.enabled is True
    assert strategy_config.governance.manual_approval_required is True
    assert strategy_config.governance.fallback_strategy_id == "trend_momentum"


def test_governance_decision_defaults_to_draft_status():
    from src.governance.models import GovernanceDecision

    decision = GovernanceDecision(
        decision_date=date(2026, 3, 24),
        current_strategy_id="trend_momentum",
        selected_strategy_id="risk_adjusted_momentum",
        fallback_strategy_id="trend_momentum",
        decision_type="switch",
    )

    assert decision.status == "draft"
    assert decision.reason_codes == []
    assert decision.evidence == {}

from src.core.config import GovernanceAutomationConfig


def test_governance_automation_config_defaults():
    config = GovernanceAutomationConfig()

    assert config.enabled is True
    assert config.max_summary_age_days == 7

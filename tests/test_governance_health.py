from datetime import date

from src.governance.models import GovernanceIncident


def test_governance_incident_defaults_to_open():
    incident = GovernanceIncident(
        incident_date=date(2026, 3, 24),
        incident_type="SUMMARY_STALE",
        severity="warning",
    )

    assert incident.status == "open"
    assert incident.reason_codes == []

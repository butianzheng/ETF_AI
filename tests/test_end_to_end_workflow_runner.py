import json

import pytest


def _stub_pipeline_result() -> dict:
    return {
        "research_result": {"report_paths": {"json": "reports/research/2026-03-24.json"}},
        "summary_result": {"output_paths": {"json": "reports/research/summary/research_summary.json"}},
        "cycle_result": type(
            "CycleResult",
            (),
            {
                "decision": type(
                    "Decision",
                    (),
                    {"id": 12, "review_status": "ready", "blocked_reasons": []},
                )()
            },
        )(),
        "pipeline_summary_path": "reports/governance/pipeline/2026-03-24.json",
        "exit_code": 0,
    }


def test_workflow_runner_requires_approved_by_when_publish_enabled(tmp_path, monkeypatch):
    import scripts.run_end_to_end_workflow as cli

    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        cli.main(["--start-date", "2025-12-01", "--end-date", "2026-03-24", "--publish"])


def test_workflow_runner_happy_path_defaults_to_no_publish(tmp_path, monkeypatch, capsys):
    import scripts.run_end_to_end_workflow as cli

    calls: list[tuple[str, object]] = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli,
        "run_research_governance_pipeline",
        lambda **kwargs: calls.append(("research_governance", kwargs)) or _stub_pipeline_result(),
    )
    monkeypatch.setattr(
        cli,
        "check_governance_health",
        lambda **kwargs: calls.append(("health", kwargs))
        or type("HealthResult", (), {"incidents": [], "rollback_recommendation": None})(),
    )
    monkeypatch.setattr(cli, "_write_health_report", lambda result: "reports/governance/health/2026-03-24.json")

    exit_code = cli.main(["--start-date", "2025-12-01", "--end-date", "2026-03-24"])

    stdout = capsys.readouterr().out
    summary_path = tmp_path / "reports" / "workflow" / "end_to_end_workflow_summary.json"
    assert exit_code == 0
    assert [name for name, _ in calls] == ["research_governance", "health"]
    assert "publish_executed=false" in stdout
    assert summary_path.exists()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["publish_result"]["executed"] is False
    assert payload["exit_code"] == 0


def test_workflow_runner_forwards_create_rollback_draft_only_to_health_check(tmp_path, monkeypatch):
    import scripts.run_end_to_end_workflow as cli

    calls: list[tuple[str, object]] = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli,
        "run_research_governance_pipeline",
        lambda **kwargs: calls.append(("research_governance", kwargs)) or _stub_pipeline_result(),
    )
    monkeypatch.setattr(
        cli,
        "check_governance_health",
        lambda **kwargs: calls.append(("health", kwargs))
        or type("HealthResult", (), {"incidents": [], "rollback_recommendation": None})(),
    )
    monkeypatch.setattr(cli, "_write_health_report", lambda result: "reports/governance/health/2026-03-24.json")

    exit_code = cli.main(
        [
            "--start-date",
            "2025-12-01",
            "--end-date",
            "2026-03-24",
            "--create-rollback-draft",
        ]
    )

    assert exit_code == 0
    assert calls[0][0] == "research_governance"
    assert "create_rollback_draft" not in calls[0][1]
    assert calls[1][0] == "health"
    assert calls[1][1]["create_rollback_draft"] is True


def test_workflow_runner_writes_stable_research_governance_summary(tmp_path, monkeypatch):
    import scripts.run_end_to_end_workflow as cli

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_write_health_report", lambda result: "reports/governance/health/2026-03-24.json")
    monkeypatch.setattr(
        cli,
        "run_research_governance_pipeline",
        lambda **kwargs: {
            "research_result": {"report_paths": {"json": "reports/research/2026-03-24.json"}},
            "summary_result": {"output_paths": {"json": "reports/research/summary/research_summary.json"}},
            "cycle_result": type(
                "CycleResult",
                (),
                {
                    "decision": type(
                        "Decision",
                        (),
                        {"id": 42, "review_status": "blocked", "blocked_reasons": ["REGIME_MISMATCH"]},
                    )()
                },
            )(),
            "pipeline_summary_path": "reports/governance/pipeline/2026-03-24.json",
            "exit_code": 0,
        },
    )
    monkeypatch.setattr(
        cli,
        "check_governance_health",
        lambda **kwargs: type("HealthResult", (), {"incidents": [], "rollback_recommendation": None})(),
    )

    exit_code = cli.main(["--start-date", "2025-12-01", "--end-date", "2026-03-24"])

    assert exit_code == 0
    summary_path = tmp_path / "reports" / "workflow" / "end_to_end_workflow_summary.json"
    text = summary_path.read_text(encoding="utf-8")
    payload = json.loads(text)
    research = payload["research_governance_result"]
    assert research["decision_id"] == 42
    assert research["review_status"] == "blocked"
    assert research["blocked_reasons"] == ["REGIME_MISMATCH"]
    assert research["pipeline_summary"] == "reports/governance/pipeline/2026-03-24.json"
    assert "cycle_result" not in research
    assert "object at 0x" not in text

import json
from types import SimpleNamespace

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


def _blocked_pipeline_result(exit_code: int = 0) -> dict:
    return {
        "research_result": {"report_paths": {"json": "reports/research/2026-03-24.json"}},
        "summary_result": {"output_paths": {"json": "reports/research/summary/research_summary.json"}},
        "cycle_result": SimpleNamespace(
            decision=SimpleNamespace(
                id=21,
                review_status="blocked",
                blocked_reasons=["SELECTED_STRATEGY_REGIME_MISMATCH"],
            )
        ),
        "pipeline_summary_path": "reports/governance/pipeline/2026-03-24.json",
        "exit_code": exit_code,
    }


def _stub_daily_pipeline_result() -> dict:
    return {
        "status": "ok",
        "report_paths": {
            "json": "reports/daily/2026-03-24.json",
            "markdown": "reports/daily/2026-03-24.md",
        },
        "portal_paths": {"json": "reports/daily/portal/index.json"},
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
    monkeypatch.setattr(
        cli,
        "_write_health_report",
        lambda result, **kwargs: "reports/governance/health/2026-03-24.json",
    )

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
    monkeypatch.setattr(
        cli,
        "_write_health_report",
        lambda result, **kwargs: "reports/governance/health/2026-03-24.json",
    )

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
    monkeypatch.setattr(
        cli,
        "_write_health_report",
        lambda result, **kwargs: "reports/governance/health/2026-03-24.json",
    )
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


def test_workflow_runner_blocked_fail_on_blocked_returns_two(tmp_path, monkeypatch):
    import scripts.run_end_to_end_workflow as cli

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "run_research_governance_pipeline", lambda **kwargs: _blocked_pipeline_result(exit_code=0))
    monkeypatch.setattr(
        cli,
        "check_governance_health",
        lambda **kwargs: SimpleNamespace(incidents=[], rollback_recommendation=None),
    )
    monkeypatch.setattr(
        cli,
        "_write_health_report",
        lambda result, **kwargs: "reports/governance/health/2026-03-24.json",
    )

    exit_code = cli.main(
        [
            "--start-date",
            "2025-12-01",
            "--end-date",
            "2026-03-24",
            "--fail-on-blocked",
        ]
    )

    assert exit_code == 2
    summary_path = tmp_path / "reports" / "workflow" / "end_to_end_workflow_summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["exit_code"] == 2


def test_workflow_runner_failed_summary_for_research_governance_fatal(tmp_path, monkeypatch):
    import scripts.run_end_to_end_workflow as cli

    monkeypatch.chdir(tmp_path)

    def _raise_fatal(**kwargs):
        raise RuntimeError("research pipeline exploded")

    monkeypatch.setattr(cli, "run_research_governance_pipeline", _raise_fatal)

    exit_code = cli.main(["--start-date", "2025-12-01", "--end-date", "2026-03-24"])

    assert exit_code == 1
    summary_path = tmp_path / "reports" / "workflow" / "end_to_end_workflow_summary.json"
    assert summary_path.exists()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["failed_step"] == "research_governance"
    assert payload["error"]["message"] == "research pipeline exploded"


def test_workflow_runner_health_fatal_overrides_blocked_exit_code(tmp_path, monkeypatch):
    import scripts.run_end_to_end_workflow as cli

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "run_research_governance_pipeline", lambda **kwargs: _blocked_pipeline_result(exit_code=2))

    def _raise_health_fatal(**kwargs):
        raise RuntimeError("health check crashed")

    monkeypatch.setattr(cli, "check_governance_health", _raise_health_fatal)

    exit_code = cli.main(
        [
            "--start-date",
            "2025-12-01",
            "--end-date",
            "2026-03-24",
            "--fail-on-blocked",
        ]
    )

    assert exit_code == 1
    summary_path = tmp_path / "reports" / "workflow" / "end_to_end_workflow_summary.json"
    assert summary_path.exists()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["failed_step"] == "health_check"
    assert payload["error"]["message"] == "health check crashed"


def test_workflow_runner_health_report_write_fatal_keeps_computed_health_payload(tmp_path, monkeypatch):
    import scripts.run_end_to_end_workflow as cli

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "run_research_governance_pipeline", lambda **kwargs: _stub_pipeline_result())
    monkeypatch.setattr(
        cli,
        "check_governance_health",
        lambda **kwargs: SimpleNamespace(
            incidents=[{"incident_type": "RISK_BREACH", "severity": "critical"}],
            rollback_recommendation={"id": 99, "review_status": "ready"},
        ),
    )

    def _raise_on_write(_result):
        raise RuntimeError("health report write failed")

    monkeypatch.setattr(cli, "_write_health_report", _raise_on_write)

    exit_code = cli.main(["--start-date", "2025-12-01", "--end-date", "2026-03-24"])

    assert exit_code == 1
    summary_path = tmp_path / "reports" / "workflow" / "end_to_end_workflow_summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["failed_step"] == "health_check"
    assert payload["error"]["message"] == "health report write failed"
    assert payload["health_check_result"]["executed"] is True
    assert payload["health_check_result"]["incidents"] == [
        {"incident_type": "RISK_BREACH", "severity": "critical"}
    ]
    assert payload["health_check_result"]["rollback_recommendation"] == {"id": 99, "review_status": "ready"}


def test_workflow_runner_blocked_publish_is_skipped_with_reason(tmp_path, monkeypatch):
    import scripts.run_end_to_end_workflow as cli

    calls: list[tuple[str, object]] = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli,
        "run_research_governance_pipeline",
        lambda **kwargs: calls.append(("research_governance", kwargs)) or _blocked_pipeline_result(exit_code=0),
    )
    monkeypatch.setattr(
        cli,
        "check_governance_health",
        lambda **kwargs: calls.append(("health", kwargs))
        or SimpleNamespace(incidents=[], rollback_recommendation=None),
    )
    monkeypatch.setattr(
        cli,
        "publish_decision",
        lambda **kwargs: pytest.fail("publish should be skipped when review_status is blocked"),
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "_write_health_report",
        lambda result, **kwargs: "reports/governance/health/2026-03-24.json",
    )

    exit_code = cli.main(
        [
            "--start-date",
            "2025-12-01",
            "--end-date",
            "2026-03-24",
            "--publish",
            "--approved-by",
            "reviewer-a",
        ]
    )

    assert exit_code == 0
    assert [name for name, _ in calls] == ["research_governance", "health"]
    summary_path = tmp_path / "reports" / "workflow" / "end_to_end_workflow_summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["publish_result"]["executed"] is False
    assert payload["publish_result"]["publish_blocked_reason"] == "governance_review_status_blocked"


def test_workflow_runner_run_daily_before_research_governance(tmp_path, monkeypatch):
    import scripts.run_end_to_end_workflow as cli

    calls: list[tuple[str, object]] = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli,
        "run_daily_pipeline",
        lambda **kwargs: calls.append(("daily", kwargs)) or _stub_daily_pipeline_result(),
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "run_research_governance_pipeline",
        lambda **kwargs: calls.append(("research_governance", kwargs)) or _stub_pipeline_result(),
    )
    monkeypatch.setattr(
        cli,
        "check_governance_health",
        lambda **kwargs: calls.append(("health", kwargs))
        or SimpleNamespace(incidents=[], rollback_recommendation=None),
    )
    monkeypatch.setattr(
        cli,
        "_write_health_report",
        lambda result, **kwargs: "reports/governance/health/2026-03-24.json",
    )

    exit_code = cli.main(
        [
            "--start-date",
            "2025-12-01",
            "--end-date",
            "2026-03-24",
            "--run-daily",
            "--daily-date",
            "2026-03-24",
            "--daily-execute",
            "--daily-manual-approve",
            "--daily-available-cash",
            "88888",
        ]
    )

    assert exit_code == 0
    assert [name for name, _ in calls][:2] == ["daily", "research_governance"]
    assert calls[0][1]["as_of_date"].isoformat() == "2026-03-24"
    assert calls[0][1]["execute_trade"] is True
    assert calls[0][1]["manual_approved"] is True
    assert calls[0][1]["available_cash"] == 88888
    summary_path = tmp_path / "reports" / "workflow" / "end_to_end_workflow_summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["daily_result"]["executed"] is True


def test_workflow_runner_publish_path_runs_post_publish_health_check(tmp_path, monkeypatch):
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
        or SimpleNamespace(incidents=[], rollback_recommendation=None),
    )
    monkeypatch.setattr(
        cli,
        "publish_decision",
        lambda **kwargs: calls.append(("publish", kwargs))
        or SimpleNamespace(id=12, status="published", review_status="ready"),
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "_write_health_report",
        lambda result, **kwargs: "reports/governance/health/2026-03-24.json",
    )

    exit_code = cli.main(
        [
            "--start-date",
            "2025-12-01",
            "--end-date",
            "2026-03-24",
            "--publish",
            "--approved-by",
            "reviewer-a",
        ]
    )

    assert exit_code == 0
    assert [name for name, _ in calls] == ["research_governance", "health", "publish", "health"]
    assert calls[2][1]["decision_id"] == 12
    assert calls[2][1]["approved_by"] == "reviewer-a"
    summary_path = tmp_path / "reports" / "workflow" / "end_to_end_workflow_summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["daily_result"]["executed"] is False
    assert payload["publish_result"]["executed"] is True
    assert payload["publish_result"]["decision"]["id"] == 12
    assert payload["post_publish_health_check_result"]["executed"] is True


def test_workflow_runner_publish_health_reports_use_distinct_files(tmp_path, monkeypatch):
    import scripts.run_end_to_end_workflow as cli

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "run_research_governance_pipeline", lambda **kwargs: _stub_pipeline_result())

    health_call_count = {"value": 0}

    def _stub_health(**kwargs):
        health_call_count["value"] += 1
        stage = "pre" if health_call_count["value"] == 1 else "post"
        return SimpleNamespace(
            incidents=[{"stage": stage, "severity": "info"}],
            rollback_recommendation=None,
        )

    monkeypatch.setattr(cli, "check_governance_health", _stub_health)
    monkeypatch.setattr(
        cli,
        "publish_decision",
        lambda **kwargs: SimpleNamespace(id=12, status="published", review_status="ready"),
        raising=False,
    )

    exit_code = cli.main(
        [
            "--start-date",
            "2025-12-01",
            "--end-date",
            "2026-03-24",
            "--publish",
            "--approved-by",
            "reviewer-a",
        ]
    )

    assert exit_code == 0
    assert health_call_count["value"] == 2
    summary_path = tmp_path / "reports" / "workflow" / "end_to_end_workflow_summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    pre_path = payload["health_check_result"]["report_path"]
    post_path = payload["post_publish_health_check_result"]["report_path"]
    assert pre_path is not None
    assert post_path is not None
    assert pre_path != post_path
    assert (tmp_path / pre_path).exists()
    assert (tmp_path / post_path).exists()

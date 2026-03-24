import json
import re
from datetime import date
from pathlib import Path


def _write_candidate_config(path: Path) -> Path:
    path.write_text(
        """
research:
  candidates:
    - name: baseline_trend
      strategy_id: trend_momentum
      description: baseline
      overrides: {}
""".strip(),
        encoding="utf-8",
    )
    return path


def _write_minimal_research_report(base_dir: Path, report_date: str = "2026-03-24") -> dict[str, str]:
    report_dir = base_dir / "reports" / "research"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"{report_date}.json"
    md_path = report_dir / f"{report_date}.md"
    csv_path = report_dir / f"{report_date}.csv"

    json_path.write_text(
        json.dumps(
            {
                "comparison_rows": [
                    {
                        "name": "baseline_trend",
                        "candidate_name": "baseline_trend",
                        "strategy_id": "trend_momentum",
                        "description": "baseline",
                        "overrides": {},
                        "annual_return": 0.18,
                        "sharpe": 1.2,
                        "max_drawdown": -0.08,
                        "composite_score": 1.2,
                    }
                ],
                "research_output": {
                    "ranked_candidates": [
                        {
                            "name": "baseline_trend",
                            "candidate_name": "baseline_trend",
                            "strategy_id": "trend_momentum",
                            "description": "baseline",
                            "overrides": {},
                            "annual_return": 0.18,
                            "sharpe": 1.2,
                            "max_drawdown": -0.08,
                            "composite_score": 1.2,
                        }
                    ],
                    "recommendation": "继续观察 baseline_trend",
                    "overfit_risk": "low",
                    "summary": "smoke happy path",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    md_path.write_text("# Smoke Research Report", encoding="utf-8")
    csv_path.write_text("name,annual_return\nbaseline_trend,0.18\n", encoding="utf-8")
    return {"markdown": str(md_path), "json": str(json_path), "csv": str(csv_path)}


def _install_research_pipeline_stub(monkeypatch, pipeline_module, tmp_path: Path) -> None:
    def fake_run_research_pipeline(**kwargs):
        assert kwargs["candidate_specs"] == [
            {
                "name": "baseline_trend",
                "strategy_id": "trend_momentum",
                "description": "baseline",
                "overrides": {},
            }
        ]
        report_paths = _write_minimal_research_report(tmp_path, report_date="2026-03-24")
        return {"report_paths": report_paths, "portal_paths": {}}

    monkeypatch.setattr(pipeline_module, "run_research_pipeline", fake_run_research_pipeline)


def _install_governance_cycle_stub(
    monkeypatch,
    pipeline_module,
    *,
    run_date_cls,
    review_status: str,
    blocked_reasons: list[str],
    summary_hash: str,
) -> None:
    from src.governance.automation import GovernanceCycleResult
    from src.governance.models import GovernanceDecision

    def fake_run_governance_cycle(**kwargs):
        assert Path(kwargs["summary_path"]).exists()
        draft = GovernanceDecision(
            decision_date=run_date_cls.today(),
            current_strategy_id="trend_momentum",
            selected_strategy_id="risk_adjusted_momentum",
            previous_strategy_id="trend_momentum",
            fallback_strategy_id="trend_momentum",
            decision_type="switch",
            review_status=review_status,
            blocked_reasons=blocked_reasons,
            reason_codes=["REGIME_GATE_BLOCKED"] if blocked_reasons else ["CHALLENGER_PROMOTED"],
        )
        saved = kwargs["repo"].save_draft(draft)
        return GovernanceCycleResult(
            decision=saved,
            summary_hash=summary_hash,
            created_new=True,
        )

    monkeypatch.setattr(pipeline_module, "run_governance_cycle", fake_run_governance_cycle)


def _install_smoke_env(
    tmp_path: Path,
    monkeypatch,
    pipeline_module,
    fake_date_cls,
    *,
    review_status: str = "ready",
    blocked_reasons: list[str] | None = None,
    summary_hash: str = "summary-hash-smoke",
) -> None:
    class DummyGovernanceConfig:
        pass

    class DummyStrategyConfig:
        governance = DummyGovernanceConfig()

    normalized_blocked_reasons = list(blocked_reasons or [])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pipeline_module, "date", fake_date_cls)
    _install_research_pipeline_stub(monkeypatch, pipeline_module, tmp_path)
    _install_governance_cycle_stub(
        monkeypatch,
        pipeline_module,
        run_date_cls=fake_date_cls,
        review_status=review_status,
        blocked_reasons=normalized_blocked_reasons,
        summary_hash=summary_hash,
    )
    monkeypatch.setattr(
        pipeline_module.config_loader,
        "load_strategy_config",
        lambda: DummyStrategyConfig(),
    )
    monkeypatch.setattr(
        pipeline_module.config_loader,
        "load_production_strategy_id",
        lambda: "trend_momentum",
    )


def test_research_governance_pipeline_cli_smoke_happy_path(tmp_path, monkeypatch, capsys):
    import scripts.run_research_governance_pipeline as cli
    import src.governance_pipeline as pipeline
    from src.governance.automation import GovernanceCycleResult
    from src.governance.models import GovernanceDecision

    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 24)

    class DummyGovernanceConfig:
        pass

    class DummyStrategyConfig:
        governance = DummyGovernanceConfig()

    candidate_config = _write_candidate_config(tmp_path / "research_candidates.yaml")

    def fake_run_research_pipeline(**kwargs):
        assert kwargs["candidate_specs"] == [
            {
                "name": "baseline_trend",
                "strategy_id": "trend_momentum",
                "description": "baseline",
                "overrides": {},
            }
        ]
        report_paths = _write_minimal_research_report(tmp_path, report_date="2026-03-24")
        return {"report_paths": report_paths, "portal_paths": {}}

    def fake_run_governance_cycle(**kwargs):
        assert Path(kwargs["summary_path"]).exists()
        draft = GovernanceDecision(
            decision_date=FakeDate.today(),
            current_strategy_id="trend_momentum",
            selected_strategy_id="risk_adjusted_momentum",
            previous_strategy_id="trend_momentum",
            fallback_strategy_id="trend_momentum",
            decision_type="switch",
            review_status="ready",
            blocked_reasons=[],
            reason_codes=["CHALLENGER_PROMOTED"],
        )
        saved = kwargs["repo"].save_draft(draft)
        return GovernanceCycleResult(
            decision=saved,
            summary_hash="summary-hash-smoke-happy",
            created_new=True,
        )

    _install_smoke_env(tmp_path, monkeypatch, pipeline, FakeDate)
    monkeypatch.setattr(
        pipeline,
        "run_research_pipeline",
        fake_run_research_pipeline,
    )
    monkeypatch.setattr(
        pipeline,
        "run_governance_cycle",
        fake_run_governance_cycle,
    )
    monkeypatch.setattr(
        pipeline.config_loader,
        "load_strategy_config",
        lambda: DummyStrategyConfig(),
    )
    monkeypatch.setattr(
        pipeline.config_loader,
        "load_production_strategy_id",
        lambda: "trend_momentum",
    )

    exit_code = cli.main(
        [
            "--start-date",
            "2025-12-01",
            "--end-date",
            "2026-03-24",
            "--candidate-config",
            str(candidate_config),
        ]
    )

    stdout = capsys.readouterr().out
    assert exit_code == 0
    assert "research_report=" in stdout
    assert "summary_json=" in stdout
    assert re.search(r"decision_id=\d+ review_status=ready blocked_reasons=\[\]", stdout)
    assert "pipeline_summary=" in stdout
    assert (tmp_path / "reports" / "research" / "2026-03-24.json").exists()
    assert (tmp_path / "reports" / "research" / "2026-03-24.md").exists()
    assert (tmp_path / "reports" / "research" / "2026-03-24.csv").exists()
    assert (tmp_path / "reports" / "research" / "summary" / "research_summary.json").exists()
    assert (tmp_path / "reports" / "governance" / "cycle" / "2026-03-24.json").exists()
    assert (tmp_path / "reports" / "governance" / "2026-03-24.json").exists()
    assert (tmp_path / "reports" / "governance" / "pipeline" / "2026-03-24.json").exists()
    assert (tmp_path / "reports" / "portal_summary.json").exists()

    pipeline_summary_payload = json.loads(
        (tmp_path / "reports" / "governance" / "pipeline" / "2026-03-24.json").read_text(
            encoding="utf-8"
        )
    )
    assert pipeline_summary_payload["final_decision"]["review_status"] == "ready"


def test_research_governance_pipeline_cli_smoke_blocked_returns_zero_by_default(
    tmp_path,
    monkeypatch,
):
    import scripts.run_research_governance_pipeline as cli
    import src.governance_pipeline as pipeline

    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 24)

    candidate_config = _write_candidate_config(tmp_path / "research_candidates.yaml")
    _install_smoke_env(
        tmp_path,
        monkeypatch,
        pipeline,
        FakeDate,
        review_status="blocked",
        blocked_reasons=["SELECTED_STRATEGY_REGIME_MISMATCH"],
        summary_hash="summary-hash-smoke-blocked-default",
    )

    exit_code = cli.main(
        [
            "--start-date",
            "2025-12-01",
            "--end-date",
            "2026-03-24",
            "--candidate-config",
            str(candidate_config),
        ]
    )

    assert exit_code == 0
    assert Path("reports/research/2026-03-24.json").exists()
    assert Path("reports/research/2026-03-24.md").exists()
    assert Path("reports/research/2026-03-24.csv").exists()
    assert Path("reports/research/summary/research_summary.json").exists()
    assert Path("reports/governance/cycle/2026-03-24.json").exists()
    assert Path("reports/governance/2026-03-24.json").exists()
    assert Path("reports/governance/pipeline/2026-03-24.json").exists()
    assert Path("reports/portal_summary.json").exists()
    payload = json.loads(
        Path("reports/governance/pipeline/2026-03-24.json").read_text(encoding="utf-8")
    )
    assert payload["final_decision"]["review_status"] == "blocked"
    assert payload["final_decision"]["blocked_reasons"] == ["SELECTED_STRATEGY_REGIME_MISMATCH"]


def test_research_governance_pipeline_cli_smoke_blocked_returns_two_with_fail_flag(
    tmp_path,
    monkeypatch,
):
    import scripts.run_research_governance_pipeline as cli
    import src.governance_pipeline as pipeline

    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 24)

    candidate_config = _write_candidate_config(tmp_path / "research_candidates.yaml")
    _install_smoke_env(
        tmp_path,
        monkeypatch,
        pipeline,
        FakeDate,
        review_status="blocked",
        blocked_reasons=["SELECTED_STRATEGY_REGIME_MISMATCH"],
        summary_hash="summary-hash-smoke-blocked-fail-flag",
    )

    exit_code = cli.main(
        [
            "--start-date",
            "2025-12-01",
            "--end-date",
            "2026-03-24",
            "--candidate-config",
            str(candidate_config),
            "--fail-on-blocked",
        ]
    )

    assert exit_code == 2
    assert Path("reports/research/2026-03-24.json").exists()
    assert Path("reports/research/2026-03-24.md").exists()
    assert Path("reports/research/2026-03-24.csv").exists()
    assert Path("reports/research/summary/research_summary.json").exists()
    assert Path("reports/governance/cycle/2026-03-24.json").exists()
    assert Path("reports/governance/2026-03-24.json").exists()
    assert Path("reports/governance/pipeline/2026-03-24.json").exists()
    assert Path("reports/portal_summary.json").exists()
    payload = json.loads(
        Path("reports/governance/pipeline/2026-03-24.json").read_text(encoding="utf-8")
    )
    assert payload["final_decision"]["review_status"] == "blocked"
    assert payload["final_decision"]["blocked_reasons"] == ["SELECTED_STRATEGY_REGIME_MISMATCH"]

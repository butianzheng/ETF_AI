import json
from datetime import date
from pathlib import Path


def test_run_research_governance_pipeline_happy_path(tmp_path, monkeypatch):
    from src.governance.automation import GovernanceCycleResult
    from src.governance.models import GovernanceDecision
    import src.governance_pipeline as pipeline

    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 24)

    class DummyGovernanceConfig:
        pass

    class DummyStrategyConfig:
        governance = DummyGovernanceConfig()

    calls: list[tuple[str, object]] = []

    research_json = tmp_path / "reports" / "research" / "2026-03-11.json"
    research_md = research_json.with_suffix(".md")
    research_csv = research_json.with_suffix(".csv")
    research_json.parent.mkdir(parents=True, exist_ok=True)
    research_json.write_text("{}", encoding="utf-8")
    research_md.write_text("# research", encoding="utf-8")
    research_csv.write_text("name\nbaseline", encoding="utf-8")

    summary_json = tmp_path / "reports" / "research" / "summary" / "research_summary.json"
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text(json.dumps({"report_count": 2}, ensure_ascii=False), encoding="utf-8")

    portal_json = tmp_path / "reports" / "portal_summary.json"
    portal_html = tmp_path / "reports" / "index.html"
    portal_json.parent.mkdir(parents=True, exist_ok=True)
    portal_json.write_text("{}", encoding="utf-8")
    portal_html.write_text("<html></html>", encoding="utf-8")

    decision = GovernanceDecision(
        id=12,
        decision_date=FakeDate.today(),
        current_strategy_id="trend_momentum",
        selected_strategy_id="risk_adjusted_momentum",
        previous_strategy_id="trend_momentum",
        fallback_strategy_id="trend_momentum",
        decision_type="switch",
        review_status="ready",
        blocked_reasons=[],
        reason_codes=["CHALLENGER_PROMOTED"],
        evidence={"source": "cycle"},
    )

    def fake_run_research_pipeline(**kwargs):
        calls.append(("research", kwargs))
        assert kwargs["start_date"] == date(2025, 12, 1)
        assert kwargs["end_date"] == date(2026, 3, 11)
        return {
            "report_paths": {
                "markdown": str(research_md),
                "json": str(research_json),
                "csv": str(research_csv),
            },
            "portal_paths": {
                "html": str(portal_html),
                "json": str(portal_json),
            },
        }

    def fake_aggregate_research_reports(**kwargs):
        calls.append(("summary", kwargs))
        assert kwargs == {
            "report_dir": Path("reports/research"),
            "output_dir": Path("reports/research/summary"),
        }
        return {
            "report_summaries": [
                {"report_date": "2026-03-10"},
                {"report_date": "2026-03-11"},
            ],
            "candidate_leaderboard": [{"name": "risk_adjusted_baseline"}],
            "candidate_observations": [],
            "candidate_regime_leaderboard": [],
            "output_paths": {
                "json": str(summary_json),
                "html": str(summary_json.with_name("index.html")),
            },
        }

    def fake_build_report_portal(**kwargs):
        calls.append(("portal", kwargs))
        assert kwargs == {
            "daily_dir": Path("reports/daily"),
            "research_dir": Path("reports/research"),
            "output_dir": Path("reports"),
        }
        return {
            "output_paths": {
                "html": str(portal_html),
                "json": str(portal_json),
            }
        }

    def fake_run_governance_cycle(**kwargs):
        calls.append(("governance_cycle", kwargs))
        assert kwargs["summary_path"] == summary_json
        assert kwargs["current_strategy_id"] == "trend_momentum"
        assert isinstance(kwargs["repo"], DummyRepo)
        assert kwargs["policy"] is DummyStrategyConfig.governance
        return GovernanceCycleResult(
            decision=decision,
            summary_hash="summary-hash-001",
            created_new=True,
        )

    class DummyRepo:
        def close(self):
            calls.append(("repo_close", None))

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pipeline, "date", FakeDate)
    monkeypatch.setattr(pipeline, "run_research_pipeline", fake_run_research_pipeline)
    monkeypatch.setattr(pipeline, "aggregate_research_reports", fake_aggregate_research_reports)
    monkeypatch.setattr(pipeline, "build_report_portal", fake_build_report_portal)
    monkeypatch.setattr(pipeline, "run_governance_cycle", fake_run_governance_cycle)
    monkeypatch.setattr(pipeline, "GovernanceRepository", DummyRepo)
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

    result = pipeline.run_research_governance_pipeline(
        start_date=date(2025, 12, 1),
        end_date=date(2026, 3, 11),
    )

    assert [item[0] for item in calls] == [
        "research",
        "summary",
        "portal",
        "governance_cycle",
        "repo_close",
    ]
    assert result["research_result"]["report_paths"]["json"] == str(research_json)
    assert result["summary_result"]["output_paths"]["json"] == str(summary_json)
    assert result["portal_result"]["output_paths"]["json"] == str(portal_json)
    assert result["cycle_result"].decision is decision
    assert result["exit_code"] == 0

    governance_cycle_path = Path(result["governance_cycle_path"])
    governance_review_path = Path(result["governance_review_path"])
    pipeline_summary_path = Path(result["pipeline_summary_path"])

    assert governance_cycle_path == tmp_path / "reports" / "governance" / "cycle" / "2026-03-24.json"
    assert governance_review_path == tmp_path / "reports" / "governance" / "2026-03-24.json"
    assert pipeline_summary_path == tmp_path / "reports" / "governance" / "pipeline" / "2026-03-24.json"

    cycle_payload = json.loads(governance_cycle_path.read_text(encoding="utf-8"))
    assert cycle_payload == {
        "decision": decision.model_dump(mode="json"),
        "summary_hash": "summary-hash-001",
        "created_new": True,
        "blocked_reasons": [],
    }

    review_payload = json.loads(governance_review_path.read_text(encoding="utf-8"))
    assert review_payload == decision.model_dump(mode="json")

    pipeline_payload = json.loads(pipeline_summary_path.read_text(encoding="utf-8"))
    assert pipeline_payload["research_end_date"] == "2026-03-11"
    assert pipeline_payload["governance_run_date"] == "2026-03-24"
    assert pipeline_payload["steps"] == {
        "research": {
            "status": "completed",
            "output_paths": {
                "markdown": str(research_md),
                "json": str(research_json),
                "csv": str(research_csv),
            },
        },
        "summary": {
            "status": "completed",
            "output_paths": {
                "json": str(summary_json),
            },
        },
        "governance_cycle": {
            "status": "completed",
            "review_status": "ready",
            "decision_id": 12,
            "created_new": True,
            "summary_hash": "summary-hash-001",
        },
        "governance_review": {
            "status": "completed",
            "output_path": str(governance_review_path),
        },
    }
    assert pipeline_payload["final_decision"] == {
        "decision_id": 12,
        "review_status": "ready",
        "blocked_reasons": [],
        "created_new": True,
        "summary_hash": "summary-hash-001",
    }


def test_run_research_governance_pipeline_governance_sequence(tmp_path, monkeypatch):
    from src.governance.automation import GovernanceCycleResult
    from src.governance.models import GovernanceDecision
    import src.governance_pipeline as pipeline

    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 24)

    class DummyGovernanceConfig:
        pass

    class DummyStrategyConfig:
        governance = DummyGovernanceConfig()

    summary_json = tmp_path / "reports" / "research" / "summary" / "research_summary.json"
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text("{}", encoding="utf-8")

    decision = GovernanceDecision(
        id=1,
        decision_date=FakeDate.today(),
        current_strategy_id="trend_momentum",
        selected_strategy_id="risk_adjusted_momentum",
        previous_strategy_id="trend_momentum",
        fallback_strategy_id="trend_momentum",
        decision_type="switch",
        review_status="ready",
        blocked_reasons=[],
        reason_codes=["CHALLENGER_PROMOTED"],
        evidence={"source": "cycle"},
    )

    order: list[str] = []

    def fake_run_governance_cycle(**kwargs):
        order.append("governance_cycle")
        return GovernanceCycleResult(
            decision=decision,
            summary_hash="summary-hash-001",
            created_new=True,
        )

    governance_cycle_artifact_path = tmp_path / "reports" / "governance" / "cycle" / "hook.json"
    governance_review_artifact_path = tmp_path / "reports" / "governance" / "hook.json"
    pipeline_summary_artifact_path = tmp_path / "reports" / "governance" / "pipeline" / "hook.json"

    def fake_write_governance_cycle_artifact(run_date, cycle_result):
        order.append("governance_cycle_artifact")
        assert run_date == FakeDate.today()
        assert cycle_result.decision is decision
        return governance_cycle_artifact_path

    def fake_write_governance_review_artifact(run_date, decision_payload):
        order.append("governance_review_artifact")
        assert run_date == FakeDate.today()
        assert decision_payload is decision
        return governance_review_artifact_path

    def fake_write_pipeline_summary_artifact(
        research_end_date,
        governance_run_date,
        research_result,
        summary_result,
        cycle_result,
        governance_review_path,
    ):
        order.append("pipeline_summary_artifact")
        assert research_end_date == date(2026, 3, 11)
        assert governance_run_date == FakeDate.today()
        assert cycle_result.decision is decision
        assert governance_review_path == governance_review_artifact_path
        return pipeline_summary_artifact_path

    class DummyRepo:
        def close(self):
            pass

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pipeline, "date", FakeDate)
    monkeypatch.setattr(
        pipeline,
        "run_research_pipeline",
        lambda **kwargs: {"report_paths": {}, "portal_paths": {}},
    )
    monkeypatch.setattr(
        pipeline,
        "aggregate_research_reports",
        lambda **kwargs: {"output_paths": {"json": str(summary_json)}},
    )
    monkeypatch.setattr(
        pipeline,
        "build_report_portal",
        lambda **kwargs: {"output_paths": {}},
    )
    monkeypatch.setattr(pipeline, "run_governance_cycle", fake_run_governance_cycle)
    monkeypatch.setattr(
        pipeline,
        "_write_governance_cycle_artifact",
        fake_write_governance_cycle_artifact,
    )
    monkeypatch.setattr(
        pipeline,
        "_write_governance_review_artifact",
        fake_write_governance_review_artifact,
    )
    monkeypatch.setattr(
        pipeline,
        "_write_pipeline_summary_artifact",
        fake_write_pipeline_summary_artifact,
    )
    monkeypatch.setattr(pipeline, "GovernanceRepository", DummyRepo)
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

    pipeline.run_research_governance_pipeline(
        start_date=date(2025, 12, 1),
        end_date=date(2026, 3, 11),
    )

    assert order.index("governance_cycle") < order.index("governance_review_artifact")
    assert order.index("governance_review_artifact") < order.index("pipeline_summary_artifact")
    assert order == [
        "governance_cycle",
        "governance_cycle_artifact",
        "governance_review_artifact",
        "pipeline_summary_artifact",
    ]

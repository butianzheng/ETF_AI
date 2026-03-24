import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest


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
        "portal",
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

    def fake_run_research_pipeline(**kwargs):
        pipeline.date.today()
        return {"report_paths": {}, "portal_paths": {}}

    monkeypatch.setattr(
        pipeline,
        "run_research_pipeline",
        fake_run_research_pipeline,
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


def test_run_research_governance_pipeline_portal_reflects_current_decision(tmp_path, monkeypatch):
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

    research_json = tmp_path / "reports" / "research" / "2026-03-11.json"
    research_json.parent.mkdir(parents=True, exist_ok=True)
    research_json.write_text("{}", encoding="utf-8")

    summary_json = tmp_path / "reports" / "research" / "summary" / "research_summary.json"
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text("{}", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pipeline, "date", FakeDate)
    monkeypatch.setattr(
        pipeline,
        "run_research_pipeline",
        lambda **kwargs: {
            "report_paths": {
                "json": str(research_json),
            },
            "portal_paths": {},
        },
    )
    monkeypatch.setattr(
        pipeline,
        "aggregate_research_reports",
        lambda **kwargs: {
            "output_paths": {
                "json": str(summary_json),
            }
        },
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

    def fake_run_governance_cycle(**kwargs):
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
            evidence={"source": "cycle"},
        )
        saved = kwargs["repo"].save_draft(draft)
        return GovernanceCycleResult(
            decision=saved,
            summary_hash="summary-hash-portal-001",
            created_new=True,
        )

    monkeypatch.setattr(pipeline, "run_governance_cycle", fake_run_governance_cycle)

    result = pipeline.run_research_governance_pipeline(
        start_date=date(2025, 12, 1),
        end_date=date(2026, 3, 11),
    )

    decision_id = result["cycle_result"].decision.id
    assert decision_id is not None
    assert result["portal_result"]["governance_summary"]["latest_decision"]["id"] == decision_id
    assert result["portal_result"]["governance_summary"]["latest_decision"]["review_status"] == "ready"

    portal_summary_path = Path(result["portal_result"]["output_paths"]["json"])
    portal_payload = json.loads(portal_summary_path.read_text(encoding="utf-8"))
    assert portal_payload["governance_summary"]["latest_decision"]["id"] == decision_id
    assert portal_payload["governance_summary"]["latest_decision"]["review_status"] == "ready"


def test_run_research_governance_pipeline_blocked_writes_all_artifacts_and_exit_zero(
    tmp_path, monkeypatch
):
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

    research_json = tmp_path / "reports" / "research" / "2026-03-11.json"
    research_json.parent.mkdir(parents=True, exist_ok=True)
    research_json.write_text("{}", encoding="utf-8")

    summary_json = tmp_path / "reports" / "research" / "summary" / "research_summary.json"
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text("{}", encoding="utf-8")

    portal_json = tmp_path / "reports" / "portal_summary.json"
    portal_html = tmp_path / "reports" / "index.html"
    portal_json.write_text("{}", encoding="utf-8")
    portal_html.write_text("<html></html>", encoding="utf-8")

    decision = GovernanceDecision(
        id=9,
        decision_date=FakeDate.today(),
        current_strategy_id="trend_momentum",
        selected_strategy_id="risk_adjusted_momentum",
        previous_strategy_id="trend_momentum",
        fallback_strategy_id="trend_momentum",
        decision_type="keep",
        review_status="blocked",
        blocked_reasons=["SELECTED_STRATEGY_REGIME_MISMATCH"],
        reason_codes=["REGIME_GATE_BLOCKED"],
        evidence={"source": "cycle"},
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pipeline, "date", FakeDate)
    monkeypatch.setattr(
        pipeline,
        "run_research_pipeline",
        lambda **kwargs: {
            "report_paths": {"json": str(research_json)},
            "portal_paths": {},
        },
    )
    monkeypatch.setattr(
        pipeline,
        "aggregate_research_reports",
        lambda **kwargs: {"output_paths": {"json": str(summary_json)}},
    )
    monkeypatch.setattr(
        pipeline,
        "build_report_portal",
        lambda **kwargs: {
            "output_paths": {
                "json": str(portal_json),
                "html": str(portal_html),
            }
        },
    )
    monkeypatch.setattr(
        pipeline,
        "run_governance_cycle",
        lambda **kwargs: GovernanceCycleResult(
            decision=decision,
            summary_hash="summary-hash-blocked",
            created_new=False,
        ),
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

    result = pipeline.run_research_governance_pipeline(
        start_date=date(2025, 12, 1),
        end_date=date(2026, 3, 11),
        fail_on_blocked=False,
    )

    assert result["exit_code"] == 0
    assert Path(result["governance_cycle_path"]).exists()
    assert Path(result["governance_review_path"]).exists()
    assert Path(result["pipeline_summary_path"]).exists()

    pipeline_payload = json.loads(Path(result["pipeline_summary_path"]).read_text(encoding="utf-8"))
    assert pipeline_payload["final_decision"]["review_status"] == "blocked"
    assert pipeline_payload["final_decision"]["blocked_reasons"] == [
        "SELECTED_STRATEGY_REGIME_MISMATCH"
    ]


def test_run_research_governance_pipeline_blocked_exit_two_when_fail_on_blocked_enabled(
    tmp_path, monkeypatch
):
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
        id=10,
        decision_date=FakeDate.today(),
        current_strategy_id="trend_momentum",
        selected_strategy_id="risk_adjusted_momentum",
        previous_strategy_id="trend_momentum",
        fallback_strategy_id="trend_momentum",
        decision_type="keep",
        review_status="blocked",
        blocked_reasons=["SELECTED_STRATEGY_REGIME_MISMATCH"],
        reason_codes=["REGIME_GATE_BLOCKED"],
        evidence={"source": "cycle"},
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pipeline, "date", FakeDate)

    def fake_run_research_pipeline(**kwargs):
        pipeline.date.today()
        return {"report_paths": {}, "portal_paths": {}}

    monkeypatch.setattr(
        pipeline,
        "run_research_pipeline",
        fake_run_research_pipeline,
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
    monkeypatch.setattr(
        pipeline,
        "run_governance_cycle",
        lambda **kwargs: GovernanceCycleResult(
            decision=decision,
            summary_hash="summary-hash-blocked",
            created_new=False,
        ),
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

    result = pipeline.run_research_governance_pipeline(
        start_date=date(2025, 12, 1),
        end_date=date(2026, 3, 11),
        fail_on_blocked=True,
    )

    assert result["exit_code"] == 2
    governance_cycle_path = Path(result["governance_cycle_path"])
    governance_review_path = Path(result["governance_review_path"])
    pipeline_summary_path = Path(result["pipeline_summary_path"])

    assert governance_cycle_path.exists()
    assert governance_review_path.exists()
    assert pipeline_summary_path.exists()

    pipeline_payload = json.loads(pipeline_summary_path.read_text(encoding="utf-8"))
    assert pipeline_payload["final_decision"]["review_status"] == "blocked"
    assert pipeline_payload["final_decision"]["blocked_reasons"] == [
        "SELECTED_STRATEGY_REGIME_MISMATCH"
    ]


def test_run_research_governance_pipeline_writes_partial_summary_before_raising_fatal(
    tmp_path, monkeypatch
):
    import src.governance_pipeline as pipeline

    class FakeDate(date):
        _today_values = [
            date(2026, 3, 24),
            date(2026, 3, 25),
        ]

        @classmethod
        def today(cls):
            if cls._today_values:
                return cls._today_values.pop(0)
            return date(2026, 3, 25)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pipeline, "date", FakeDate)

    def fake_run_research_pipeline(**kwargs):
        pipeline.date.today()
        return {"report_paths": {}, "portal_paths": {}}

    monkeypatch.setattr(
        pipeline,
        "run_research_pipeline",
        fake_run_research_pipeline,
    )

    def raise_summary_error(**kwargs):
        raise RuntimeError("summary step fatal")

    monkeypatch.setattr(pipeline, "aggregate_research_reports", raise_summary_error)

    with pytest.raises(RuntimeError, match="summary step fatal"):
        pipeline.run_research_governance_pipeline(
            start_date=date(2025, 12, 1),
            end_date=date(2026, 3, 11),
        )

    partial_summary_path = tmp_path / "reports" / "governance" / "pipeline" / "2026-03-25.json"
    assert partial_summary_path.exists()
    payload = json.loads(partial_summary_path.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["failed_step"] == "summary"
    assert payload["error"]["type"] == "RuntimeError"
    assert payload["error"]["message"] == "summary step fatal"
    assert payload["governance_run_date"] == "2026-03-25"

    assert not (tmp_path / "reports" / "governance" / "cycle" / "2026-03-25.json").exists()
    assert not (tmp_path / "reports" / "governance" / "2026-03-25.json").exists()


def test_run_research_governance_pipeline_cross_midnight_uses_governance_stage_date_for_artifacts(
    tmp_path, monkeypatch
):
    from src.governance.automation import GovernanceCycleResult
    from src.governance.models import GovernanceDecision
    import src.governance_pipeline as pipeline

    class FakeDate(date):
        _today_values = [
            date(2026, 3, 24),
            date(2026, 3, 25),
        ]

        @classmethod
        def today(cls):
            if cls._today_values:
                return cls._today_values.pop(0)
            return date(2026, 3, 25)

    class DummyGovernanceConfig:
        pass

    class DummyStrategyConfig:
        governance = DummyGovernanceConfig()

    summary_json = tmp_path / "reports" / "research" / "summary" / "research_summary.json"
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text("{}", encoding="utf-8")

    decision = GovernanceDecision(
        id=21,
        decision_date=date(2026, 3, 25),
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

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pipeline, "date", FakeDate)

    def fake_run_research_pipeline(**kwargs):
        pipeline.date.today()
        return {"report_paths": {}, "portal_paths": {}}

    monkeypatch.setattr(
        pipeline,
        "run_research_pipeline",
        fake_run_research_pipeline,
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
    monkeypatch.setattr(
        pipeline,
        "run_governance_cycle",
        lambda **kwargs: GovernanceCycleResult(
            decision=decision,
            summary_hash="summary-hash-midnight",
            created_new=True,
        ),
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

    result = pipeline.run_research_governance_pipeline(
        start_date=date(2025, 12, 1),
        end_date=date(2026, 3, 11),
    )

    assert Path(result["governance_cycle_path"]).name == "2026-03-25.json"
    assert Path(result["governance_review_path"]).name == "2026-03-25.json"
    assert Path(result["pipeline_summary_path"]).name == "2026-03-25.json"
    payload = json.loads(Path(result["pipeline_summary_path"]).read_text(encoding="utf-8"))
    assert payload["governance_run_date"] == "2026-03-25"


def test_run_research_governance_pipeline_post_governance_fatal_uses_governance_run_date_for_partial_summary(
    tmp_path, monkeypatch
):
    from src.governance.automation import GovernanceCycleResult
    from src.governance.models import GovernanceDecision
    import src.governance_pipeline as pipeline

    class FakeDate(date):
        _today_values = [
            date(2026, 3, 24),
            date(2026, 3, 25),
            date(2026, 3, 26),
        ]

        @classmethod
        def today(cls):
            if cls._today_values:
                return cls._today_values.pop(0)
            return date(2026, 3, 26)

    class DummyGovernanceConfig:
        pass

    class DummyStrategyConfig:
        governance = DummyGovernanceConfig()

    summary_json = tmp_path / "reports" / "research" / "summary" / "research_summary.json"
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text("{}", encoding="utf-8")

    decision = GovernanceDecision(
        id=22,
        decision_date=date(2026, 3, 25),
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

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pipeline, "date", FakeDate)

    def fake_run_research_pipeline(**kwargs):
        pipeline.date.today()
        return {"report_paths": {}, "portal_paths": {}}

    monkeypatch.setattr(
        pipeline,
        "run_research_pipeline",
        fake_run_research_pipeline,
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
    monkeypatch.setattr(
        pipeline,
        "run_governance_cycle",
        lambda **kwargs: GovernanceCycleResult(
            decision=decision,
            summary_hash="summary-hash-post-fatal",
            created_new=True,
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "_write_governance_cycle_artifact",
        lambda run_date, cycle_result: tmp_path / "reports" / "governance" / "cycle" / "ok.json",
    )

    def raise_review_artifact_error(run_date, decision_payload):
        raise RuntimeError("review artifact fatal")

    monkeypatch.setattr(
        pipeline,
        "_write_governance_review_artifact",
        raise_review_artifact_error,
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

    with pytest.raises(RuntimeError, match="review artifact fatal"):
        pipeline.run_research_governance_pipeline(
            start_date=date(2025, 12, 1),
            end_date=date(2026, 3, 11),
        )

    partial_summary_path = tmp_path / "reports" / "governance" / "pipeline" / "2026-03-25.json"
    assert partial_summary_path.exists()
    payload = json.loads(partial_summary_path.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["failed_step"] == "governance_review_artifact"
    assert payload["error"]["type"] == "RuntimeError"
    assert payload["error"]["message"] == "review artifact fatal"
    assert payload["governance_run_date"] == "2026-03-25"


def test_research_governance_pipeline_cli_main_stdout_and_exit_zero(monkeypatch, capsys):
    import scripts.run_research_governance_pipeline as cli

    calls: dict[str, object] = {}

    def fake_run_research_governance_pipeline(**kwargs):
        calls.update(kwargs)
        return {
            "research_result": {
                "report_paths": {"json": "reports/research/2026-03-24.json"},
            },
            "summary_result": {
                "output_paths": {"json": "reports/research/summary/research_summary.json"},
            },
            "cycle_result": SimpleNamespace(
                decision=SimpleNamespace(
                    id=88,
                    review_status="ready",
                    blocked_reasons=[],
                )
            ),
            "pipeline_summary_path": "reports/governance/pipeline/2026-03-24.json",
            "exit_code": 0,
        }

    monkeypatch.setattr(cli, "run_research_governance_pipeline", fake_run_research_governance_pipeline)

    exit_code = cli.main(["--start-date", "2025-12-01", "--end-date", "2026-03-24"])

    assert exit_code == 0
    assert calls["start_date"] == date(2025, 12, 1)
    assert calls["end_date"] == date(2026, 3, 24)

    stdout = capsys.readouterr().out
    assert "research_report=reports/research/2026-03-24.json" in stdout
    assert "summary_json=reports/research/summary/research_summary.json" in stdout
    assert "decision_id=88 review_status=ready blocked_reasons=[]" in stdout
    assert "pipeline_summary=reports/governance/pipeline/2026-03-24.json" in stdout


def test_research_governance_pipeline_cli_main_returns_two_when_fail_on_blocked(monkeypatch):
    import scripts.run_research_governance_pipeline as cli

    calls: dict[str, object] = {}

    def fake_run_research_governance_pipeline(**kwargs):
        calls.update(kwargs)
        return {
            "research_result": {"report_paths": {}},
            "summary_result": {"output_paths": {}},
            "cycle_result": SimpleNamespace(
                decision=SimpleNamespace(
                    id=89,
                    review_status="blocked",
                    blocked_reasons=["SELECTED_STRATEGY_REGIME_MISMATCH"],
                )
            ),
            "pipeline_summary_path": "reports/governance/pipeline/2026-03-24.json",
            "exit_code": 2,
        }

    monkeypatch.setattr(cli, "run_research_governance_pipeline", fake_run_research_governance_pipeline)

    exit_code = cli.main(
        [
            "--start-date",
            "2025-12-01",
            "--end-date",
            "2026-03-24",
            "--fail-on-blocked",
        ]
    )

    assert calls["fail_on_blocked"] is True
    assert exit_code == 2


def test_research_governance_pipeline_cli_main_returns_one_on_fatal_exception(monkeypatch):
    import scripts.run_research_governance_pipeline as cli

    def raise_fatal(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "run_research_governance_pipeline", raise_fatal)

    exit_code = cli.main(["--start-date", "2025-12-01", "--end-date", "2026-03-24"])

    assert exit_code == 1


def test_research_governance_pipeline_cli_main_loads_candidate_config_and_forwards_runtime_args(
    tmp_path, monkeypatch
):
    import scripts.run_research_governance_pipeline as cli

    candidate_config = tmp_path / "research_candidates.yaml"
    candidate_config.write_text(
        """
research:
  candidates:
    - name: baseline_trend
      strategy_id: trend_momentum
      description: baseline
      overrides: {}
    - name: fast_turn
      strategy_id: risk_adjusted_momentum
      description: fast
      overrides:
        strategy_params:
          rebalance_frequency: biweekly
          hold_count: 2
""".strip(),
        encoding="utf-8",
    )

    calls: dict[str, object] = {}

    def fake_run_research_governance_pipeline(**kwargs):
        calls.update(kwargs)
        return {
            "research_result": {"report_paths": {}},
            "summary_result": {"output_paths": {}},
            "cycle_result": SimpleNamespace(
                decision=SimpleNamespace(id=90, review_status="ready", blocked_reasons=[])
            ),
            "pipeline_summary_path": "reports/governance/pipeline/2026-03-24.json",
            "exit_code": 0,
        }

    monkeypatch.setattr(cli, "run_research_governance_pipeline", fake_run_research_governance_pipeline)

    exit_code = cli.main(
        [
            "--start-date",
            "2025-12-01",
            "--end-date",
            "2026-03-24",
            "--candidate-config",
            str(candidate_config),
            "--initial-capital",
            "123456.78",
            "--fee-rate",
            "0.0025",
            "--log-level",
            "DEBUG",
        ]
    )

    assert exit_code == 0
    assert calls["candidate_specs"] == [
        {
            "name": "baseline_trend",
            "strategy_id": "trend_momentum",
            "description": "baseline",
            "overrides": {},
        },
        {
            "name": "fast_turn",
            "strategy_id": "risk_adjusted_momentum",
            "description": "fast",
            "overrides": {
                "strategy_params": {
                    "rebalance_frequency": "biweekly",
                    "hold_count": 2,
                }
            },
        },
    ]
    assert calls["initial_capital"] == pytest.approx(123456.78)
    assert calls["fee_rate"] == pytest.approx(0.0025)
    assert calls["log_level"] == "DEBUG"

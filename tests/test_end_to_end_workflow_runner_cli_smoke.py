import json
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace


def _parse_stdout_kv(stdout: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            result[key] = value
    return result


def test_end_to_end_workflow_runner_cli_smoke_publish_path_has_artifacts_and_stdout_contract(
    tmp_path,
    monkeypatch,
    capsys,
):
    import scripts.run_end_to_end_workflow as cli

    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 24)

    class DummyGovernanceConfig:
        pass

    class DummyStrategyConfig:
        governance = DummyGovernanceConfig()

    class DummyConfigLoader:
        def __init__(self, _root: str):
            pass

        def load_strategy_config(self):
            return DummyStrategyConfig()

    class DummyRepo:
        def close(self):
            return None

    health_call_count = {"value": 0}

    def _stub_health(**_kwargs):
        health_call_count["value"] += 1
        stage = "pre" if health_call_count["value"] == 1 else "post"
        return SimpleNamespace(
            incidents=[{"stage": stage, "severity": "info"}],
            rollback_recommendation=None,
        )

    def _stub_pipeline(**_kwargs):
        report_dir = tmp_path / "reports" / "research"
        report_dir.mkdir(parents=True, exist_ok=True)
        summary_dir = report_dir / "summary"
        summary_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "2026-03-24.json").write_text("{}", encoding="utf-8")
        (summary_dir / "research_summary.json").write_text("{}", encoding="utf-8")
        pipeline_dir = tmp_path / "reports" / "governance" / "pipeline"
        pipeline_dir.mkdir(parents=True, exist_ok=True)
        (pipeline_dir / "2026-03-24.json").write_text("{}", encoding="utf-8")
        return {
            "research_result": {"report_paths": {"json": "reports/research/2026-03-24.json"}},
            "summary_result": {"output_paths": {"json": "reports/research/summary/research_summary.json"}},
            "cycle_result": SimpleNamespace(
                decision=SimpleNamespace(id=12, review_status="ready", blocked_reasons=[])
            ),
            "pipeline_summary_path": "reports/governance/pipeline/2026-03-24.json",
            "exit_code": 0,
        }

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "date", FakeDate)
    monkeypatch.setattr(
        cli,
        "run_workflow_preflight",
        lambda **_kwargs: {"status": "passed", "checks": [], "failed_checks": []},
    )
    monkeypatch.setattr(cli, "load_candidate_specs", lambda _path: [])
    monkeypatch.setattr(cli, "run_research_governance_pipeline", _stub_pipeline)
    monkeypatch.setattr(cli, "check_governance_health", _stub_health)
    monkeypatch.setattr(
        cli,
        "publish_decision",
        lambda **_kwargs: SimpleNamespace(id=12, status="published", review_status="ready"),
        raising=False,
    )
    monkeypatch.setattr(cli, "GovernanceRepository", lambda: DummyRepo())
    monkeypatch.setattr(cli, "ConfigLoader", DummyConfigLoader)

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

    stdout = capsys.readouterr().out
    kv = _parse_stdout_kv(stdout)

    assert exit_code == 0
    assert kv["workflow_status"] in {"preflight_only", "succeeded", "blocked", "failed"}
    assert kv["publish_executed"] == "true"
    assert re.match(r"^\d{8}T\d{6}Z-[a-z0-9]{8}$", kv["run_id"])

    manifest_path = tmp_path / Path(kv["workflow_manifest"])
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["run_id"] == kv["run_id"]
    assert payload["workflow_manifest_path"] == kv["workflow_manifest"]
    assert payload["status"] == kv["workflow_status"]
    assert payload["publish_result"]["executed"] is True

    legacy_summary_path = tmp_path / "reports" / "workflow" / "end_to_end_workflow_summary.json"
    assert legacy_summary_path.exists()
    legacy_payload = json.loads(legacy_summary_path.read_text(encoding="utf-8"))
    assert legacy_payload == payload

    pre_health_path = payload["health_check_result"]["report_path"]
    post_health_path = payload["post_publish_health_check_result"]["report_path"]
    assert pre_health_path is not None
    assert post_health_path is not None
    assert pre_health_path != post_health_path
    assert (tmp_path / pre_health_path).exists()
    assert (tmp_path / post_health_path).exists()

    pre_health_payload = json.loads((tmp_path / pre_health_path).read_text(encoding="utf-8"))
    post_health_payload = json.loads((tmp_path / post_health_path).read_text(encoding="utf-8"))
    assert pre_health_payload["incidents"][0]["stage"] == "pre"
    assert post_health_payload["incidents"][0]["stage"] == "post"

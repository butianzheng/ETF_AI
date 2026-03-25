from pathlib import Path


def test_run_workflow_preflight_returns_passed_with_all_checks(tmp_path, monkeypatch):
    from src.workflow.preflight import run_workflow_preflight

    result = run_workflow_preflight(
        start_date="2025-12-01",
        end_date="2026-03-24",
        daily_date=None,
        candidate_config=None,
        workflow_root=tmp_path / "reports" / "workflow",
        health_root=tmp_path / "reports" / "governance" / "health",
    )

    assert result["status"] == "passed"
    assert result["failed_checks"] == []
    assert {item["name"] for item in result["checks"]} >= {
        "date_args",
        "strategy_config",
        "candidate_config",
        "governance_repository",
        "workflow_output_dir",
        "health_output_dir",
    }


def test_run_workflow_preflight_collects_failed_checks(monkeypatch, tmp_path):
    import src.workflow.preflight as preflight

    monkeypatch.setattr(
        preflight,
        "_check_strategy_config",
        lambda *_args, **_kwargs: {"name": "strategy_config", "status": "failed", "detail": "boom"},
    )

    result = preflight.run_workflow_preflight(
        start_date="2025-12-01",
        end_date="2026-03-24",
        daily_date=None,
        candidate_config=None,
        workflow_root=tmp_path / "reports" / "workflow",
        health_root=tmp_path / "reports" / "governance" / "health",
    )

    assert result["status"] == "failed"
    assert result["failed_checks"] == [{"name": "strategy_config", "detail": "boom"}]


def test_run_workflow_preflight_maps_candidate_config_parse_error(monkeypatch, tmp_path):
    import src.workflow.preflight as preflight

    monkeypatch.setattr(
        preflight,
        "load_candidate_specs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("bad candidate yaml")),
    )

    result = preflight.run_workflow_preflight(
        start_date="2025-12-01",
        end_date="2026-03-24",
        daily_date=None,
        candidate_config="bad.yaml",
        workflow_root=tmp_path / "reports" / "workflow",
        health_root=tmp_path / "reports" / "governance" / "health",
    )

    failed_names = [item["name"] for item in result["failed_checks"]]
    assert "candidate_config" in failed_names


def test_run_workflow_preflight_checks_workflow_and_health_dirs_independently(monkeypatch, tmp_path):
    import src.workflow.preflight as preflight

    def _fake_output_check(path: Path, *, name: str):
        if name == "workflow_output_dir":
            return {"name": name, "status": "failed", "detail": "workflow not writable"}
        return {"name": name, "status": "passed", "detail": None}

    monkeypatch.setattr(preflight, "_check_output_dir_writable", _fake_output_check)

    result = preflight.run_workflow_preflight(
        start_date="2025-12-01",
        end_date="2026-03-24",
        daily_date=None,
        candidate_config=None,
        workflow_root=tmp_path / "reports" / "workflow",
        health_root=tmp_path / "reports" / "governance" / "health",
    )

    failed_checks = {item["name"] for item in result["failed_checks"]}
    check_names = {item["name"] for item in result["checks"]}
    assert check_names >= {"workflow_output_dir", "health_output_dir"}
    assert failed_checks == {"workflow_output_dir"}

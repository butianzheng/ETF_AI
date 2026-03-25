import json
from pathlib import Path
from subprocess import CompletedProcess


def _write_manifest(tmp_path: Path, *, status: str, exit_code: int, failed_step: str | None = None) -> Path:
    manifest_path = (
        tmp_path / "reports" / "workflow" / "runs" / "20260325T010203Z-abcd1234" / "workflow_manifest.json"
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "run_id": "20260325T010203Z-abcd1234",
        "status": status,
        "exit_code": exit_code,
        "health_check_result": {"report_path": None},
        "post_publish_health_check_result": {"report_path": None},
        "research_governance_result": {"pipeline_summary": None},
    }
    if failed_step is not None:
        payload["failed_step"] = failed_step
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    return manifest_path


def test_workflow_automation_runner_writes_latest_run_for_success(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    _write_manifest(tmp_path, status="preflight_only", exit_code=0)

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=(
                "run_id=20260325T010203Z-abcd1234\n"
                "workflow_manifest=reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json\n"
                "workflow_status=preflight_only\n"
                "publish_executed=false\n"
            ),
            stderr="",
        ),
    )

    exit_code = cli.main(["--workdir", str(tmp_path), "--", "--preflight-only"])

    assert exit_code == 0
    assert (tmp_path / "reports" / "workflow" / "automation" / "latest_run.json").exists()


def test_workflow_automation_runner_returns_one_and_writes_attention_on_contract_error(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="workflow_status=succeeded\npublish_executed=false\n",
            stderr="boom",
        ),
    )

    exit_code = cli.main(["--workdir", str(tmp_path), "--", "--preflight-only"])

    assert exit_code == 1
    assert (tmp_path / "reports" / "workflow" / "automation" / "latest_attention.json").exists()
    assert (tmp_path / "reports" / "workflow" / "automation" / "latest_run.json").exists()
    history_path = tmp_path / "reports" / "workflow" / "automation" / "run_history.jsonl"
    assert history_path.exists()
    assert "automation_run_id" in history_path.read_text(encoding="utf-8")
    assert list((tmp_path / "reports" / "workflow" / "automation" / "runs").glob("*/runner_stdout.log"))
    assert list((tmp_path / "reports" / "workflow" / "automation" / "runs").glob("*/runner_stderr.log"))


def test_workflow_automation_runner_inherits_blocked_exit_code(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    _write_manifest(tmp_path, status="blocked", exit_code=2)

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=2,
            stdout=(
                "run_id=20260325T010203Z-abcd1234\n"
                "workflow_manifest=reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json\n"
                "workflow_status=blocked\n"
                "publish_executed=false\n"
            ),
            stderr="",
        ),
    )

    exit_code = cli.main(["--workdir", str(tmp_path), "--", "--fail-on-blocked"])

    assert exit_code == 2
    assert (tmp_path / "reports" / "workflow" / "automation" / "latest_attention.json").exists()


def test_workflow_automation_runner_keeps_blocked_exit_zero_when_runner_returns_zero(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    _write_manifest(tmp_path, status="blocked", exit_code=0)

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=(
                "run_id=20260325T010203Z-abcd1234\n"
                "workflow_manifest=reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json\n"
                "workflow_status=blocked\n"
                "publish_executed=false\n"
            ),
            stderr="",
        ),
    )

    assert cli.main(["--workdir", str(tmp_path), "--"]) == 0
    assert (tmp_path / "reports" / "workflow" / "automation" / "latest_attention.json").exists()


def test_workflow_automation_runner_inherits_failed_exit_code(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    _write_manifest(tmp_path, status="failed", exit_code=1, failed_step="preflight")

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=1,
            stdout=(
                "run_id=20260325T010203Z-abcd1234\n"
                "workflow_manifest=reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json\n"
                "workflow_status=failed\n"
                "publish_executed=false\n"
            ),
            stderr="",
        ),
    )

    assert cli.main(["--workdir", str(tmp_path), "--", "--preflight-only"]) == 1


def test_workdir_creates_config_symlink(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    _write_manifest(tmp_path, status="preflight_only", exit_code=0)

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=(
                "run_id=20260325T010203Z-abcd1234\n"
                "workflow_manifest=reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json\n"
                "workflow_status=preflight_only\n"
                "publish_executed=false\n"
            ),
            stderr="",
        ),
    )

    assert cli.main(["--workdir", str(tmp_path), "--", "--preflight-only"]) == 0
    config_link = tmp_path / "config"
    assert config_link.exists()
    assert config_link.is_symlink()
    assert config_link.resolve() == (Path(cli.PROJECT_ROOT) / "config").resolve()


def test_success_does_not_overwrite_existing_attention(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    # First run: contract error => writes attention.
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="workflow_status=succeeded\npublish_executed=false\n",
            stderr="boom",
        ),
    )
    assert cli.main(["--workdir", str(tmp_path), "--", "--preflight-only"]) == 1
    attention_path = tmp_path / "reports" / "workflow" / "automation" / "latest_attention.json"
    attention_before = attention_path.read_text(encoding="utf-8")

    # Second run: success => must not override attention.
    _write_manifest(tmp_path, status="preflight_only", exit_code=0)
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=(
                "run_id=20260325T010203Z-abcd1234\n"
                "workflow_manifest=reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json\n"
                "workflow_status=preflight_only\n"
                "publish_executed=false\n"
            ),
            stderr="",
        ),
    )
    assert cli.main(["--workdir", str(tmp_path), "--", "--preflight-only"]) == 0
    assert attention_path.read_text(encoding="utf-8") == attention_before


def test_wrapper_self_failure_returns_one_and_writes_attention(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    def _boom(*args, **kwargs):
        raise OSError("subprocess failed")

    monkeypatch.setattr(cli.subprocess, "run", _boom)

    assert cli.main(["--workdir", str(tmp_path), "--", "--preflight-only"]) == 1
    assert (tmp_path / "reports" / "workflow" / "automation" / "latest_run.json").exists()
    assert (tmp_path / "reports" / "workflow" / "automation" / "latest_attention.json").exists()
    assert list((tmp_path / "reports" / "workflow" / "automation" / "runs").glob("*/runner_stdout.log"))
    assert list((tmp_path / "reports" / "workflow" / "automation" / "runs").glob("*/runner_stderr.log"))

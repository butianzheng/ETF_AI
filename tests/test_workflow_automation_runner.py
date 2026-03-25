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

    calls: dict[str, object] = {}

    def _run(*args, **kwargs):
        calls["cmd"] = args[0]
        calls["kwargs"] = kwargs
        return CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=(
                "run_id=20260325T010203Z-abcd1234\n"
                "workflow_manifest=reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json\n"
                "workflow_status=preflight_only\n"
                "publish_executed=false\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        _run,
    )

    exit_code = cli.main(["--workdir", str(tmp_path), "--", "--preflight-only"])

    assert exit_code == 0
    assert (tmp_path / "reports" / "workflow" / "automation" / "latest_run.json").exists()
    cmd = calls["cmd"]
    kwargs = calls["kwargs"]
    assert isinstance(cmd, list)
    assert cmd[1] == str(cli.RUNNER_SCRIPT)
    assert Path(cmd[1]).is_absolute()
    assert "--" not in cmd
    assert kwargs["cwd"] == str(tmp_path)


def test_workflow_automation_runner_writes_artifact_index_and_backfills_pointer(tmp_path, monkeypatch):
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

    latest = json.loads((tmp_path / "reports/workflow/automation/latest_run.json").read_text(encoding="utf-8"))
    assert "artifact_index_path" in latest

    artifact_index = tmp_path / str(latest["artifact_index_path"])
    assert artifact_index.exists()
    payload = json.loads(artifact_index.read_text(encoding="utf-8"))
    assert payload["manifest_path"] == "reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json"
    assert payload["effective_workdir"] == str(tmp_path)


def test_workflow_automation_runner_rebuilds_artifact_index_after_primary_write_failure(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cli, "PROJECT_ROOT", repo_root)
    monkeypatch.setattr(cli, "RUNNER_SCRIPT", (repo_root / "scripts" / "run_end_to_end_workflow.py").resolve())

    workdir = tmp_path / "wd"
    workdir.mkdir(parents=True, exist_ok=True)
    manifest_path = _write_manifest(workdir, status="preflight_only", exit_code=0)

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=(
                "run_id=20260325T010203Z-abcd1234\n"
                f"workflow_manifest={manifest_path.relative_to(workdir)}\n"
                "workflow_status=preflight_only\n"
                "publish_executed=false\n"
            ),
            stderr="",
        ),
    )

    real_write = cli.write_artifact_index
    calls = {"count": 0}

    def _flaky_write(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("primary root write failed")
        return real_write(*args, **kwargs)

    monkeypatch.setattr(cli, "write_artifact_index", _flaky_write)

    assert cli.main(["--workdir", str(workdir), "--", "--preflight-only"]) == 0

    latest = json.loads((repo_root / "reports/workflow/automation/latest_run.json").read_text(encoding="utf-8"))
    assert latest["outputs_fallback_used"] is True
    assert latest["effective_workdir"] == str(repo_root.resolve())

    artifact_index = repo_root / str(latest["artifact_index_path"])
    assert artifact_index.exists()


def test_workflow_automation_runner_returns_one_when_final_artifact_index_write_fails(tmp_path, monkeypatch):
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
    monkeypatch.setattr(cli, "write_artifact_index", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("index failed")))

    assert cli.main(["--workdir", str(tmp_path), "--", "--preflight-only"]) == 1
    latest_run = json.loads((tmp_path / "reports/workflow/automation/latest_run.json").read_text(encoding="utf-8"))
    attention = json.loads((tmp_path / "reports/workflow/automation/latest_attention.json").read_text(encoding="utf-8"))
    assert latest_run["failed_step"] == "automation_contract_error"
    assert "index failed" in str(latest_run["suggested_next_action"])
    assert attention["attention_type"] == "automation_contract_error"


def test_outputs_failure_overwrites_latest_and_history_without_artifact_index_pointer(tmp_path, monkeypatch):
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

    real_write_latest = cli._write_latest_run_json
    calls = {"count": 0}

    def _flaky_latest(record, *, path: Path):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("latest write failed")
        return real_write_latest(record, path=path)

    monkeypatch.setattr(cli, "_write_latest_run_json", _flaky_latest)

    assert cli.main(["--workdir", str(tmp_path), "--", "--preflight-only"]) == 1

    root = tmp_path / "reports" / "workflow" / "automation"
    latest = json.loads((root / "latest_run.json").read_text(encoding="utf-8"))
    assert latest["failed_step"] == "automation_contract_error"
    assert "artifact_index_path" not in latest

    lines = [line for line in (root / "run_history.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    history = json.loads(lines[0])
    assert history["automation_run_id"] == latest["automation_run_id"]
    assert history["failed_step"] == "automation_contract_error"
    assert "artifact_index_path" not in history

    # Query layer must not be redirected to the stale per-run index.
    from src.workflow.automation_index import find_run_view, load_latest_run_view

    view = load_latest_run_view(tmp_path)
    assert view is not None
    assert view["source"] != "artifact_index"

    by_id = find_run_view(tmp_path, run_id=str(latest["automation_run_id"]))
    assert by_id is not None
    assert by_id["source"] != "artifact_index"


def test_repo_nested_workdir_fallback_error_record_does_not_double_rebase_paths(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cli, "PROJECT_ROOT", repo_root)
    monkeypatch.setattr(cli, "RUNNER_SCRIPT", (repo_root / "scripts" / "run_end_to_end_workflow.py").resolve())

    workdir = repo_root / "subdir"
    workdir.mkdir(parents=True, exist_ok=True)
    manifest_path = _write_manifest(workdir, status="preflight_only", exit_code=0)

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=(
                "run_id=20260325T010203Z-abcd1234\n"
                f"workflow_manifest={manifest_path.relative_to(workdir)}\n"
                "workflow_status=preflight_only\n"
                "publish_executed=false\n"
            ),
            stderr="",
        ),
    )

    real_write_index = cli.write_artifact_index

    def _flaky_index(payload, *, effective_workdir):
        if Path(effective_workdir).resolve() == workdir.resolve():
            raise OSError("primary index failed")
        return real_write_index(payload, effective_workdir=effective_workdir)

    monkeypatch.setattr(cli, "write_artifact_index", _flaky_index)

    real_write_latest = cli._write_latest_run_json
    calls = {"count": 0}

    def _flaky_latest(record, *, path: Path):
        # Fail the first outputs attempt on repo_root so wrapper writes the error record on the same root.
        if path.resolve() == (repo_root / "reports" / "workflow" / "automation" / "latest_run.json").resolve():
            calls["count"] += 1
            if calls["count"] == 1:
                raise OSError("latest write failed")
        return real_write_latest(record, path=path)

    monkeypatch.setattr(cli, "_write_latest_run_json", _flaky_latest)

    assert cli.main(["--workdir", str(workdir), "--", "--preflight-only"]) == 1

    latest = json.loads((repo_root / "reports" / "workflow" / "automation" / "latest_run.json").read_text("utf-8"))
    stdout_path = str(latest["runner_stdout_path"])
    assert "subdir/subdir" not in stdout_path.replace("\\", "/")
    assert stdout_path.startswith("subdir/")
    assert "artifact_index_path" not in latest


def test_fallback_root_outputs_failure_does_not_write_error_back_to_original_workdir(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cli, "PROJECT_ROOT", repo_root)
    monkeypatch.setattr(cli, "RUNNER_SCRIPT", (repo_root / "scripts" / "run_end_to_end_workflow.py").resolve())

    workdir = tmp_path / "wd"
    workdir.mkdir(parents=True, exist_ok=True)
    manifest_path = _write_manifest(workdir, status="preflight_only", exit_code=0)

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=(
                "run_id=20260325T010203Z-abcd1234\n"
                f"workflow_manifest={manifest_path.relative_to(workdir)}\n"
                "workflow_status=preflight_only\n"
                "publish_executed=false\n"
            ),
            stderr="",
        ),
    )

    real_write_index = cli.write_artifact_index

    def _flaky_index_write(payload, *, effective_workdir):
        if Path(effective_workdir).resolve() == workdir.resolve():
            raise OSError("primary root index failed")
        return real_write_index(payload, effective_workdir=effective_workdir)

    monkeypatch.setattr(cli, "write_artifact_index", _flaky_index_write)

    real_write_latest = cli._write_latest_run_json

    def _flaky_latest(record, *, path: Path):
        if path.resolve() == (repo_root / "reports" / "workflow" / "automation" / "latest_run.json").resolve():
            raise OSError("fallback outputs failed")
        return real_write_latest(record, path=path)

    monkeypatch.setattr(cli, "_write_latest_run_json", _flaky_latest)

    # Index lands under repo_root, but outputs fail there; wrapper must not write error outputs back to workdir.
    assert cli.main(["--workdir", str(workdir), "--", "--preflight-only"]) == 1

    assert not (workdir / "reports" / "workflow" / "automation" / "latest_run.json").exists()
    assert not (workdir / "reports" / "workflow" / "automation" / "latest_attention.json").exists()

    indexes = list((repo_root / "reports" / "workflow" / "automation" / "runs").glob("*/artifact_index.json"))
    assert indexes
    assert not (repo_root / "reports" / "workflow" / "automation" / "latest_run.json").exists()


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


def test_workdir_mkdir_failure_still_writes_latest_run_history_and_attention(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    # Isolate PROJECT_ROOT to tmp_path so test doesn't write into repo checkout.
    monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cli, "RUNNER_SCRIPT", (tmp_path / "scripts" / "run_end_to_end_workflow.py").resolve())

    workdir = (tmp_path / "bad_workdir").resolve()
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)

    orig_mkdir = Path.mkdir

    def _mkdir(self, *args, **kwargs):
        if self.resolve() == workdir:
            raise PermissionError("no permission")
        return orig_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", _mkdir)
    monkeypatch.setattr(cli.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))

    assert cli.main(["--workdir", str(workdir), "--", "--preflight-only"]) == 1
    root = tmp_path / "reports" / "workflow" / "automation"
    assert (root / "latest_run.json").exists()
    assert (root / "run_history.jsonl").exists()
    assert (root / "latest_attention.json").exists()
    latest = json.loads((root / "latest_run.json").read_text("utf-8"))
    assert latest["requested_workdir"] == str(workdir)
    assert latest["effective_workdir"] == str(tmp_path.resolve())


def test_config_symlink_failure_still_writes_latest_run_history_and_attention(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    # Isolate PROJECT_ROOT to tmp_path so fallback writes stay inside tmp_path.
    monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cli, "RUNNER_SCRIPT", (tmp_path / "scripts" / "run_end_to_end_workflow.py").resolve())
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)

    workdir = (tmp_path / "wd").resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    orig_symlink_to = Path.symlink_to

    def _symlink_to(self, *args, **kwargs):
        if self == workdir / "config":
            raise OSError("symlink failed")
        return orig_symlink_to(self, *args, **kwargs)

    monkeypatch.setattr(Path, "symlink_to", _symlink_to)
    monkeypatch.setattr(cli.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))

    assert cli.main(["--workdir", str(workdir), "--", "--preflight-only"]) == 1
    root = tmp_path / "reports" / "workflow" / "automation"
    assert (root / "latest_run.json").exists()
    assert (root / "run_history.jsonl").exists()
    assert (root / "latest_attention.json").exists()
    latest = json.loads((root / "latest_run.json").read_text("utf-8"))
    assert latest["requested_workdir"] == str(workdir)
    assert latest["effective_workdir"] == str(tmp_path.resolve())


def test_write_runner_logs_failure_is_captured_and_still_writes_latest_and_attention(tmp_path, monkeypatch):
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

    monkeypatch.setattr(cli, "write_runner_logs", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")))

    assert cli.main(["--workdir", str(tmp_path), "--", "--preflight-only"]) == 1
    assert (tmp_path / "reports" / "workflow" / "automation" / "latest_run.json").exists()
    assert (tmp_path / "reports" / "workflow" / "automation" / "latest_attention.json").exists()


def test_rel_to_workdir_does_not_resolve_relative_paths_against_process_cwd(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    _write_manifest(tmp_path, status="preflight_only", exit_code=0)
    other = tmp_path / "other"
    other.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(other)

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

    monkeypatch.setattr(
        cli,
        "write_runner_logs",
        lambda *args, **kwargs: {
            "runner_stdout_path": "reports/workflow/automation/runs/x/runner_stdout.log",
            "runner_stderr_path": "reports/workflow/automation/runs/x/runner_stderr.log",
        },
    )

    assert cli.main(["--workdir", str(tmp_path), "--", "--preflight-only"]) == 0
    latest = json.loads((tmp_path / "reports" / "workflow" / "automation" / "latest_run.json").read_text("utf-8"))
    assert latest["runner_stdout_path"] == "reports/workflow/automation/runs/x/runner_stdout.log"
    assert latest["runner_stderr_path"] == "reports/workflow/automation/runs/x/runner_stderr.log"


def test_negative_runner_exit_code_is_mapped_to_non_negative_wrapper_exit_code(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    _write_manifest(tmp_path, status="preflight_only", exit_code=-9)

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=-9,
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
    assert exit_code == 137
    latest = json.loads((tmp_path / "reports" / "workflow" / "automation" / "latest_run.json").read_text("utf-8"))
    assert latest["runner_process_exit_code"] == -9
    assert latest["wrapper_exit_code"] == 137


def test_manifest_read_error_keeps_exception_message_in_attention(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    manifest_path = tmp_path / "reports" / "workflow" / "runs" / "20260325T010203Z-abcd1234" / "workflow_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{", encoding="utf-8")  # invalid JSON

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

    assert cli.main(["--workdir", str(tmp_path), "--", "--preflight-only"]) == 1
    attention = json.loads(
        (tmp_path / "reports" / "workflow" / "automation" / "latest_attention.json").read_text("utf-8")
    )
    assert "suggested_next_action" in attention
    assert "Expecting" in attention["suggested_next_action"] or "JSON" in attention["suggested_next_action"]


def test_write_automation_outputs_failure_does_not_fallback_after_index_written(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cli, "PROJECT_ROOT", repo_root)
    monkeypatch.setattr(cli, "RUNNER_SCRIPT", (repo_root / "scripts" / "run_end_to_end_workflow.py").resolve())

    workdir = tmp_path / "wd"
    workdir.mkdir(parents=True, exist_ok=True)

    manifest_path = _write_manifest(workdir, status="preflight_only", exit_code=0)

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=(
                "run_id=20260325T010203Z-abcd1234\n"
                f"workflow_manifest={manifest_path.relative_to(workdir)}\n"
                "workflow_status=preflight_only\n"
                "publish_executed=false\n"
            ),
            stderr="",
        ),
    )

    real_write_latest = cli._write_latest_run_json

    def _flaky_latest(record, *, path: Path):
        if path.resolve() == (workdir / "reports" / "workflow" / "automation" / "latest_run.json").resolve():
            raise OSError("workdir reports not writable")
        return real_write_latest(record, path=path)

    monkeypatch.setattr(cli, "_write_latest_run_json", _flaky_latest)

    # Index is written to the primary root before outputs. Once index exists, outputs must not be written
    # to a different root, so wrapper returns 1 instead of falling back.
    assert cli.main(["--workdir", str(workdir), "--", "--preflight-only"]) == 1

    indexes = list((workdir / "reports" / "workflow" / "automation" / "runs").glob("*/artifact_index.json"))
    assert indexes
    assert not (repo_root / "reports" / "workflow" / "automation" / "latest_run.json").exists()

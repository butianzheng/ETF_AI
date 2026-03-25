import json
import subprocess
import sys
from pathlib import Path


def _run_wrapper(*, workdir: Path, runner_args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    repo_root = Path(__file__).resolve().parents[1]
    wrapper = repo_root / "scripts" / "run_workflow_automation.py"
    cmd = [sys.executable, str(wrapper), "--workdir", str(workdir), "--", *runner_args]
    return subprocess.run(
        cmd,
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def _resolve_from_workdir(path_value: str, *, workdir: Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else (workdir / path)


def test_workflow_automation_wrapper_cli_smoke_failed_then_success_retains_attention(tmp_path):
    workdir = tmp_path / "wd"
    workdir.mkdir(parents=True, exist_ok=True)

    # 1) failed preflight
    failed = _run_wrapper(
        workdir=workdir,
        runner_args=[
            "--preflight-only",
            "--start-date",
            "2026-03-02",
            "--end-date",
            "2026-03-01",
        ],
    )
    assert failed.returncode == 1

    root = workdir / "reports" / "workflow" / "automation"
    latest_attention_json = root / "latest_attention.json"
    latest_attention_md = root / "latest_attention.md"
    latest_run_json = root / "latest_run.json"
    run_history_jsonl = root / "run_history.jsonl"

    assert latest_attention_json.exists()
    assert latest_attention_md.exists()
    assert latest_run_json.exists()
    assert run_history_jsonl.exists()

    first_attention = json.loads(latest_attention_json.read_text(encoding="utf-8"))
    first_run = json.loads(latest_run_json.read_text(encoding="utf-8"))
    failed_automation_run_id = first_run["automation_run_id"]
    assert first_run["wrapper_exit_code"] == 1
    assert first_attention["automation_run_id"] == failed_automation_run_id
    assert first_run["workflow_manifest"]
    failed_manifest_path = _resolve_from_workdir(str(first_run["workflow_manifest"]), workdir=workdir)
    assert failed_manifest_path.exists()

    # 2) success preflight
    succeeded = _run_wrapper(
        workdir=workdir,
        runner_args=[
            "--preflight-only",
            "--start-date",
            "2026-03-01",
            "--end-date",
            "2026-03-02",
        ],
    )
    assert succeeded.returncode == 0

    second_run = json.loads(latest_run_json.read_text(encoding="utf-8"))
    retained_attention = json.loads(latest_attention_json.read_text(encoding="utf-8"))
    history_lines = [line for line in run_history_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert second_run["wrapper_exit_code"] == 0
    assert len(history_lines) == 2
    assert retained_attention["automation_run_id"] == failed_automation_run_id
    assert second_run["automation_run_id"] != failed_automation_run_id
    assert retained_attention["workflow_manifest"]
    retained_manifest_path = _resolve_from_workdir(str(retained_attention["workflow_manifest"]), workdir=workdir)
    assert retained_manifest_path.exists()

    history_records = [json.loads(line) for line in history_lines]
    for item in history_records:
        assert item["workflow_manifest"]
        manifest_path = _resolve_from_workdir(str(item["workflow_manifest"]), workdir=workdir)
        assert manifest_path.exists()

    stdout_path = _resolve_from_workdir(str(retained_attention["runner_stdout_path"]), workdir=workdir)
    stderr_path = _resolve_from_workdir(str(retained_attention["runner_stderr_path"]), workdir=workdir)
    assert stdout_path.exists()
    assert stderr_path.exists()

    attention_md_text = latest_attention_md.read_text(encoding="utf-8")
    assert failed_automation_run_id in attention_md_text
    assert str(retained_attention["workflow_manifest"]) in attention_md_text
    assert not (workdir / ".workflow_automation_bootstrap").exists()

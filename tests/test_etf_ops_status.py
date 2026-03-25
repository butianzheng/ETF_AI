from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRY = REPO_ROOT / "scripts" / "etf_ops.py"


def _run_entry(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ENTRY), *args],
        cwd=str(cwd or REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _make_artifact_index(*, automation_run_id: str, run_id: str, status: str) -> dict:
    return {
        "source": "artifact_index",
        "automation_run_id": automation_run_id,
        "run_id": run_id,
        "workflow_status": status,
        "automation_started_at": "2026-03-25T08:00:00Z",
        "automation_finished_at": "2026-03-25T08:01:00Z",
        "wrapper_exit_code": 0,
        "runner_process_exit_code": 0,
        "manifest_path": f"reports/workflow/runs/{run_id}/workflow_manifest.json",
        "runner_stdout_path": f"reports/workflow/automation/runs/{automation_run_id}/stdout.log",
        "runner_stderr_path": f"reports/workflow/automation/runs/{automation_run_id}/stderr.log",
        "health_check_report_path": None,
        "post_publish_health_check_report_path": None,
        "research_governance_pipeline_summary_path": None,
        "blocked_reasons": [],
        "failed_step": None,
        "suggested_next_action": None,
        "publish_executed": True,
        "created_at": "2026-03-25T08:01:00Z",
        "requested_workdir": str(Path("/tmp/requested")),
        "effective_workdir": str(Path("/tmp/effective")),
        "outputs_fallback_used": False,
    }


def test_status_latest_prefers_automation_latest_run(tmp_path):
    root = tmp_path / "artifacts"
    _write_json(
        root / "reports/workflow/automation/latest_run.json",
        {
            "automation_run_id": "auto-001",
            "run_id": "auto-001",
            "workflow_status": "succeeded",
            "automation_started_at": "2026-03-25T08:00:00Z",
            "automation_finished_at": "2026-03-25T08:01:00Z",
            "wrapper_exit_code": 0,
            "runner_process_exit_code": 0,
            "publish_executed": True,
            "workflow_manifest": "reports/workflow/runs/auto-001/workflow_manifest.json",
            "failed_step": None,
            "blocked_reasons": [],
            "suggested_next_action": None,
        },
    )
    _write_json(
        root / "reports/workflow/end_to_end_workflow_summary.json",
        {
            "run_id": "summary-should-not-be-used",
            "status": "failed",
            "started_at": "2026-03-25T07:00:00Z",
            "finished_at": "2026-03-25T07:01:00Z",
            "workflow_manifest_path": "reports/workflow/runs/summary/workflow_manifest.json",
            "failed_step": "some_step",
            "publish_result": {"executed": False},
            "research_governance_result": {"blocked_reasons": ["x"]},
        },
    )

    outside = tmp_path / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    proc = _run_entry(
        ["status", "latest", "--workdir", str(root), "--json"],
        cwd=outside,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["source"] == "automation_latest"
    assert payload["run_id"] == "auto-001"
    assert payload["status"] == "succeeded"
    assert payload["manifest_path"] == str(root / "reports/workflow/runs/auto-001/workflow_manifest.json")


def test_status_latest_prefers_artifact_index_pointer(tmp_path):
    root = tmp_path / "artifacts"
    index_payload = _make_artifact_index(automation_run_id="auto-idx-01", run_id="wf-idx-01", status="succeeded")
    _write_json(
        root / "reports/workflow/automation/runs/auto-idx-01/artifact_index.json",
        index_payload,
    )
    _write_json(
        root / "reports/workflow/automation/latest_run.json",
        {
            "automation_run_id": "auto-idx-01",
            "run_id": "wf-legacy-should-not-be-used",
            "workflow_status": "failed",
            "automation_started_at": "2026-03-25T07:00:00Z",
            "automation_finished_at": "2026-03-25T07:01:00Z",
            "wrapper_exit_code": 1,
            "runner_process_exit_code": 1,
            "publish_executed": False,
            "workflow_manifest": "reports/workflow/runs/wf-legacy/workflow_manifest.json",
            "artifact_index_path": "reports/workflow/automation/runs/auto-idx-01/artifact_index.json",
        },
    )

    proc = _run_entry(["status", "latest", "--workdir", str(root), "--json"])

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["source"] == "artifact_index"
    assert payload["automation_run_id"] == "auto-idx-01"
    assert payload["run_id"] == "wf-idx-01"
    assert payload["status"] == "succeeded"
    assert payload["manifest_path"] == str(root / "reports/workflow/runs/wf-idx-01/workflow_manifest.json")


def test_status_latest_falls_back_to_latest_record_when_index_pointer_missing_target(tmp_path):
    root = tmp_path / "artifacts"
    _write_json(
        root / "reports/workflow/automation/latest_run.json",
        {
            "automation_run_id": "auto-missing-index",
            "run_id": "wf-from-latest",
            "workflow_status": "succeeded",
            "automation_started_at": "2026-03-25T07:00:00Z",
            "automation_finished_at": "2026-03-25T07:01:00Z",
            "wrapper_exit_code": 0,
            "runner_process_exit_code": 0,
            "publish_executed": True,
            "workflow_manifest": "reports/workflow/runs/wf-from-latest/workflow_manifest.json",
            "artifact_index_path": "reports/workflow/automation/runs/auto-missing-index/artifact_index.json",
        },
    )
    _write_json(
        root / "reports/workflow/end_to_end_workflow_summary.json",
        {
            "run_id": "wf-summary-should-not-be-used",
            "status": "failed",
            "started_at": "2026-03-25T06:00:00Z",
            "finished_at": "2026-03-25T06:02:00Z",
            "workflow_manifest_path": "reports/workflow/runs/wf-summary/workflow_manifest.json",
        },
    )

    proc = _run_entry(["status", "latest", "--workdir", str(root), "--json"])

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["source"] == "automation_latest"
    assert payload["run_id"] == "wf-from-latest"


def test_status_latest_falls_back_to_workflow_summary(tmp_path):
    root = tmp_path / "artifacts"
    _write_json(
        root / "reports/workflow/end_to_end_workflow_summary.json",
        {
            "run_id": "wf-002",
            "status": "blocked",
            "started_at": "2026-03-25T09:00:00Z",
            "finished_at": "2026-03-25T09:02:00Z",
            "workflow_manifest_path": "reports/workflow/runs/wf-002/workflow_manifest.json",
            "failed_step": None,
            "research_governance_result": {"blocked_reasons": ["risk_limit_exceeded"]},
        },
    )

    proc = _run_entry(["status", "latest", "--workdir", str(root), "--json"])

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["source"] == "workflow_summary_fallback"
    assert payload["run_id"] == "wf-002"
    assert payload["status"] == "blocked"
    assert payload["publish_executed"] is False
    assert payload["blocked_reasons"] == ["risk_limit_exceeded"]
    assert payload["suggested_next_action"] == "inspect blocked_reasons and governance review status"
    assert payload["manifest_path"] == str(root / "reports/workflow/runs/wf-002/workflow_manifest.json")


def test_status_latest_returns_one_when_no_artifact_exists(tmp_path):
    root = tmp_path / "empty-artifacts"
    root.mkdir(parents=True, exist_ok=True)

    proc = _run_entry(["status", "latest", "--workdir", str(root), "--json"])

    assert proc.returncode == 1


def test_status_latest_json_error_goes_to_stderr(tmp_path):
    root = tmp_path / "empty-artifacts"
    root.mkdir(parents=True, exist_ok=True)

    proc = _run_entry(["status", "latest", "--workdir", str(root), "--json"])

    assert proc.returncode == 1
    assert proc.stdout == ""
    assert "no status artifacts found" in proc.stderr


def test_status_latest_rejects_passthrough_args():
    proc = _run_entry(["status", "latest", "extra-arg"])

    assert proc.returncode == 2
    assert "unrecognized arguments: extra-arg" in proc.stderr


def test_status_latest_text_output_contains_key_fields(tmp_path):
    root = tmp_path / "artifacts"
    _write_json(
        root / "reports/workflow/automation/latest_run.json",
        {
            "automation_run_id": "auto-003",
            "run_id": "auto-003",
            "workflow_status": "failed",
            "automation_started_at": "2026-03-25T10:00:00Z",
            "automation_finished_at": "2026-03-25T10:01:00Z",
            "wrapper_exit_code": 1,
            "runner_process_exit_code": 1,
            "publish_executed": False,
            "workflow_manifest": "reports/workflow/runs/auto-003/workflow_manifest.json",
            "failed_step": "publish",
            "blocked_reasons": [],
            "suggested_next_action": "inspect failed_step=publish and workflow manifest",
        },
    )

    proc = _run_entry(["status", "latest", "--workdir", str(root)])

    assert proc.returncode == 0, proc.stderr
    assert "run_id: auto-003" in proc.stdout
    assert "status: failed" in proc.stdout
    assert "started_at:" in proc.stdout
    assert "finished_at:" in proc.stdout
    assert "publish_executed: false" in proc.stdout
    assert "manifest_path:" in proc.stdout
    assert "failed_step: publish" in proc.stdout


def test_status_latest_text_output_omits_empty_optional_fields(tmp_path):
    root = tmp_path / "artifacts"
    _write_json(
        root / "reports/workflow/automation/latest_run.json",
        {
            "automation_run_id": "auto-004",
            "run_id": "auto-004",
            "workflow_status": "blocked",
            "automation_started_at": "2026-03-25T12:00:00Z",
            "automation_finished_at": "2026-03-25T12:01:00Z",
            "wrapper_exit_code": 0,
            "runner_process_exit_code": 0,
            "publish_executed": False,
            "workflow_manifest": "reports/workflow/runs/auto-004/workflow_manifest.json",
            "failed_step": None,
            "blocked_reasons": [],
            "suggested_next_action": None,
        },
    )

    proc = _run_entry(["status", "latest", "--workdir", str(root)])

    assert proc.returncode == 0, proc.stderr
    assert "failed_step:" not in proc.stdout
    assert "blocked_reasons:" not in proc.stdout
    assert "suggested_next_action:" not in proc.stdout


def test_status_latest_returns_one_for_invalid_json(tmp_path):
    root = tmp_path / "artifacts"
    latest_path = root / "reports/workflow/automation/latest_run.json"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text("{invalid json", encoding="utf-8")
    _write_json(
        root / "reports/workflow/end_to_end_workflow_summary.json",
        {
            "run_id": "wf-fallback",
            "status": "succeeded",
            "started_at": "2026-03-25T11:00:00Z",
            "finished_at": "2026-03-25T11:01:00Z",
            "workflow_manifest_path": "reports/workflow/runs/wf-fallback/workflow_manifest.json",
            "publish_result": {"executed": True},
            "research_governance_result": {"blocked_reasons": []},
        },
    )

    proc = _run_entry(["status", "latest", "--workdir", str(root), "--json"])

    assert proc.returncode == 1


def test_status_latest_returns_one_for_legacy_manifest_path_non_string_type(tmp_path):
    root = tmp_path / "artifacts"
    _write_json(
        root / "reports/workflow/automation/latest_run.json",
        {
            "automation_run_id": "auto-005",
            "run_id": "auto-005",
            "workflow_status": "succeeded",
            "automation_started_at": "2026-03-25T13:00:00Z",
            "automation_finished_at": "2026-03-25T13:01:00Z",
            "wrapper_exit_code": 0,
            "runner_process_exit_code": 0,
            "publish_executed": True,
            "workflow_manifest": ["not-a-string"],
        },
    )

    proc = _run_entry(["status", "latest", "--workdir", str(root), "--json"])

    assert proc.returncode == 1
    assert proc.stdout == ""
    assert "workflow_manifest" in proc.stderr


def test_status_latest_returns_one_for_corrupt_artifact_index(tmp_path):
    root = tmp_path / "artifacts"
    index_path = root / "reports/workflow/automation/runs/auto-bad-index/artifact_index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("{bad json", encoding="utf-8")
    _write_json(
        root / "reports/workflow/automation/latest_run.json",
        {
            "automation_run_id": "auto-bad-index",
            "run_id": "wf-bad-index",
            "workflow_status": "failed",
            "automation_started_at": "2026-03-25T10:00:00Z",
            "automation_finished_at": "2026-03-25T10:01:00Z",
            "wrapper_exit_code": 1,
            "runner_process_exit_code": 1,
            "publish_executed": False,
            "workflow_manifest": "reports/workflow/runs/wf-bad-index/workflow_manifest.json",
            "artifact_index_path": str(index_path),
        },
    )

    proc = _run_entry(["status", "latest", "--workdir", str(root), "--json"])

    assert proc.returncode == 1
    assert proc.stdout == ""
    assert "invalid json" in proc.stderr


def test_status_runs_lists_history_and_supports_limit(tmp_path):
    root = tmp_path / "artifacts"
    history = root / "reports/workflow/automation/run_history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "automation_run_id": "auto-001",
                        "run_id": "wf-001",
                        "workflow_status": "failed",
                        "automation_finished_at": "2026-03-25T08:01:00Z",
                        "wrapper_exit_code": 1,
                        "failed_step": "publish",
                    }
                ),
                "{bad",
                json.dumps(
                    {
                        "automation_run_id": "auto-002",
                        "run_id": "wf-002",
                        "workflow_status": "succeeded",
                        "automation_finished_at": "2026-03-25T09:01:00Z",
                        "wrapper_exit_code": 0,
                        "failed_step": None,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    proc = _run_entry(["status", "runs", "--workdir", str(root), "--limit", "1", "--json"])

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0]["automation_run_id"] == "auto-002"
    assert payload[0]["run_id"] == "wf-002"


def test_status_runs_returns_one_when_no_valid_history_records(tmp_path):
    root = tmp_path / "artifacts"
    history = root / "reports/workflow/automation/run_history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text("{bad\n", encoding="utf-8")

    proc = _run_entry(["status", "runs", "--workdir", str(root), "--json"])

    assert proc.returncode == 1
    assert proc.stdout == ""
    assert "no runs found" in proc.stderr


def test_status_runs_returns_one_for_history_path_error(tmp_path):
    root = tmp_path / "artifacts"
    history_dir = root / "reports/workflow/automation/run_history.jsonl"
    history_dir.mkdir(parents=True, exist_ok=True)

    proc = _run_entry(["status", "runs", "--workdir", str(root), "--json"])

    assert proc.returncode == 1
    assert proc.stdout == ""
    assert "run_history.jsonl" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_status_show_prioritizes_exact_automation_run_id_over_workflow_run_id(tmp_path):
    root = tmp_path / "artifacts"
    history = root / "reports/workflow/automation/run_history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "automation_run_id": "same-id",
                        "run_id": "wf-other",
                        "workflow_status": "failed",
                        "automation_started_at": "2026-03-25T08:00:00Z",
                        "automation_finished_at": "2026-03-25T08:01:00Z",
                        "wrapper_exit_code": 1,
                        "runner_process_exit_code": 1,
                        "workflow_manifest": "reports/workflow/runs/wf-other/workflow_manifest.json",
                        "publish_executed": False,
                    }
                ),
                json.dumps(
                    {
                        "automation_run_id": "auto-002",
                        "run_id": "same-id",
                        "workflow_status": "succeeded",
                        "automation_started_at": "2026-03-25T09:00:00Z",
                        "automation_finished_at": "2026-03-25T09:01:00Z",
                        "wrapper_exit_code": 0,
                        "runner_process_exit_code": 0,
                        "workflow_manifest": "reports/workflow/runs/same-id/workflow_manifest.json",
                        "publish_executed": True,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    proc = _run_entry(["status", "show", "--workdir", str(root), "--run-id", "same-id", "--json"])

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["automation_run_id"] == "same-id"
    assert payload["run_id"] == "wf-other"
    assert payload["status"] == "failed"


def test_status_show_uses_latest_finished_for_duplicate_workflow_run_id(tmp_path):
    root = tmp_path / "artifacts"
    history = root / "reports/workflow/automation/run_history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "automation_run_id": "auto-early",
                        "run_id": "wf-dup",
                        "workflow_status": "failed",
                        "automation_started_at": "2026-03-25T07:00:00Z",
                        "automation_finished_at": "2026-03-25T07:01:00Z",
                        "wrapper_exit_code": 1,
                        "runner_process_exit_code": 1,
                        "workflow_manifest": "reports/workflow/runs/wf-dup/workflow_manifest.json",
                        "publish_executed": False,
                    }
                ),
                json.dumps(
                    {
                        "automation_run_id": "auto-late",
                        "run_id": "wf-dup",
                        "workflow_status": "succeeded",
                        "automation_started_at": "2026-03-25T10:00:00Z",
                        "automation_finished_at": "2026-03-25T10:01:00Z",
                        "wrapper_exit_code": 0,
                        "runner_process_exit_code": 0,
                        "workflow_manifest": "reports/workflow/runs/wf-dup/workflow_manifest.json",
                        "publish_executed": True,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    proc = _run_entry(["status", "show", "--workdir", str(root), "--run-id", "wf-dup", "--json"])

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["automation_run_id"] == "auto-late"
    assert payload["status"] == "succeeded"


def test_status_show_returns_one_for_not_found(tmp_path):
    root = tmp_path / "artifacts"
    history = root / "reports/workflow/automation/run_history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text("", encoding="utf-8")

    proc = _run_entry(["status", "show", "--workdir", str(root), "--run-id", "missing-id", "--json"])

    assert proc.returncode == 1
    assert proc.stdout == ""
    assert "run not found" in proc.stderr


def test_status_show_returns_one_for_corrupt_artifact_index(tmp_path):
    root = tmp_path / "artifacts"
    history = root / "reports/workflow/automation/run_history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    index_path = root / "reports/workflow/automation/runs/auto-bad/artifact_index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("{bad json", encoding="utf-8")
    history.write_text(
        json.dumps(
            {
                "automation_run_id": "auto-bad",
                "run_id": "wf-bad",
                "workflow_status": "failed",
                "automation_started_at": "2026-03-25T10:00:00Z",
                "automation_finished_at": "2026-03-25T10:01:00Z",
                "wrapper_exit_code": 1,
                "runner_process_exit_code": 1,
                "workflow_manifest": "reports/workflow/runs/wf-bad/workflow_manifest.json",
                "publish_executed": False,
                "artifact_index_path": str(index_path),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    proc = _run_entry(["status", "show", "--workdir", str(root), "--run-id", "auto-bad", "--json"])

    assert proc.returncode == 1
    assert proc.stdout == ""
    assert "invalid json" in proc.stderr


def test_status_show_fallback_view_uses_absolute_path_in_json(tmp_path):
    root = tmp_path / "artifacts"
    history = root / "reports/workflow/automation/run_history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text(
        json.dumps(
            {
                "automation_run_id": "auto-no-index",
                "run_id": "wf-no-index",
                "workflow_status": "succeeded",
                "automation_started_at": "2026-03-25T10:00:00Z",
                "automation_finished_at": "2026-03-25T10:01:00Z",
                "wrapper_exit_code": 0,
                "runner_process_exit_code": 0,
                "workflow_manifest": "reports/workflow/runs/wf-no-index/workflow_manifest.json",
                "publish_executed": True,
                "artifact_index_path": "reports/workflow/automation/runs/auto-no-index/artifact_index.json",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    proc = _run_entry(["status", "show", "--workdir", str(root), "--run-id", "auto-no-index", "--json"])

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["source"] == "legacy_fallback"
    assert payload["manifest_path"] == str(root / "reports/workflow/runs/wf-no-index/workflow_manifest.json")


def test_status_latest_keeps_legacy_suggested_next_action(tmp_path):
    root = tmp_path / "artifacts"
    _write_json(
        root / "reports/workflow/automation/latest_run.json",
        {
            "automation_run_id": "auto-next-action",
            "run_id": "wf-next-action",
            "workflow_status": "failed",
            "automation_started_at": "2026-03-25T10:00:00Z",
            "automation_finished_at": "2026-03-25T10:01:00Z",
            "wrapper_exit_code": 1,
            "runner_process_exit_code": 1,
            "publish_executed": False,
            "workflow_manifest": "reports/workflow/runs/wf-next-action/workflow_manifest.json",
            "failed_step": "publish",
            "suggested_next_action": "inspect failed_step=publish and workflow manifest",
        },
    )

    proc_json = _run_entry(["status", "latest", "--workdir", str(root), "--json"])
    assert proc_json.returncode == 0, proc_json.stderr
    payload = json.loads(proc_json.stdout)
    assert payload["suggested_next_action"] == "inspect failed_step=publish and workflow manifest"

    proc_text = _run_entry(["status", "latest", "--workdir", str(root)])
    assert proc_text.returncode == 0, proc_text.stderr
    assert "suggested_next_action: inspect failed_step=publish and workflow manifest" in proc_text.stdout


def test_status_show_keeps_legacy_suggested_next_action(tmp_path):
    root = tmp_path / "artifacts"
    history = root / "reports/workflow/automation/run_history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text(
        json.dumps(
            {
                "automation_run_id": "auto-show-next-action",
                "run_id": "wf-show-next-action",
                "workflow_status": "failed",
                "automation_started_at": "2026-03-25T10:00:00Z",
                "automation_finished_at": "2026-03-25T10:01:00Z",
                "wrapper_exit_code": 1,
                "runner_process_exit_code": 1,
                "workflow_manifest": "reports/workflow/runs/wf-show-next-action/workflow_manifest.json",
                "publish_executed": False,
                "failed_step": "publish",
                "suggested_next_action": "inspect failed_step=publish and workflow manifest",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    proc_json = _run_entry(
        ["status", "show", "--workdir", str(root), "--run-id", "auto-show-next-action", "--json"]
    )
    assert proc_json.returncode == 0, proc_json.stderr
    payload = json.loads(proc_json.stdout)
    assert payload["suggested_next_action"] == "inspect failed_step=publish and workflow manifest"

    proc_text = _run_entry(["status", "show", "--workdir", str(root), "--run-id", "auto-show-next-action"])
    assert proc_text.returncode == 0, proc_text.stderr
    assert "suggested_next_action: inspect failed_step=publish and workflow manifest" in proc_text.stdout


def test_status_show_returns_one_for_history_path_error(tmp_path):
    root = tmp_path / "artifacts"
    history_dir = root / "reports/workflow/automation/run_history.jsonl"
    history_dir.mkdir(parents=True, exist_ok=True)

    proc = _run_entry(["status", "show", "--workdir", str(root), "--run-id", "whatever", "--json"])

    assert proc.returncode == 1
    assert proc.stdout == ""
    assert "run_history.jsonl" in proc.stderr
    assert "Traceback" not in proc.stderr

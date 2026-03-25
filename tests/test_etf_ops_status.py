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


def test_status_latest_prefers_automation_latest_run(tmp_path):
    root = tmp_path / "artifacts"
    _write_json(
        root / "reports/workflow/automation/latest_run.json",
        {
            "run_id": "auto-001",
            "workflow_status": "succeeded",
            "automation_started_at": "2026-03-25T08:00:00Z",
            "automation_finished_at": "2026-03-25T08:01:00Z",
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


def test_status_latest_text_output_contains_key_fields(tmp_path):
    root = tmp_path / "artifacts"
    _write_json(
        root / "reports/workflow/automation/latest_run.json",
        {
            "run_id": "auto-003",
            "workflow_status": "failed",
            "automation_started_at": "2026-03-25T10:00:00Z",
            "automation_finished_at": "2026-03-25T10:01:00Z",
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

import json
import re
from pathlib import Path

import pytest


def test_generate_automation_run_id_is_path_safe():
    from src.workflow.automation import generate_automation_run_id

    run_id = generate_automation_run_id()
    assert re.match(r"^\d{8}T\d{6}Z-[a-z0-9]{8}$", run_id)


def test_parse_workflow_stdout_contract_extracts_required_fields():
    from src.workflow.automation import parse_workflow_stdout_contract

    contract = parse_workflow_stdout_contract(
        "run_id=20260325T010203Z-abcd1234\n"
        "workflow_manifest=reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json\n"
        "workflow_status=blocked\n"
        "publish_executed=false\n"
    )

    assert contract["run_id"] == "20260325T010203Z-abcd1234"
    assert contract["workflow_status"] == "blocked"
    assert contract["publish_executed"] is False


def test_write_automation_outputs_writes_history_latest_and_attention(tmp_path):
    from src.workflow.automation import write_automation_outputs

    record = {
        "automation_run_id": "20260325T010203Z-a1b2c3d4",
        "automation_started_at": "2026-03-25T01:02:03Z",
        "automation_finished_at": "2026-03-25T01:02:05Z",
        "runner_command": ["python", "/abs/scripts/run_end_to_end_workflow.py", "--preflight-only"],
        "runner_process_exit_code": 1,
        "wrapper_exit_code": 1,
        "run_id": "20260325T010203Z-abcd1234",
        "workflow_manifest": "reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json",
        "workflow_status": "failed",
        "publish_executed": False,
        "manifest_exit_code": 1,
        "failed_step": "preflight",
        "blocked_reasons": [],
        "health_check_report_path": None,
        "post_publish_health_check_report_path": None,
        "research_governance_pipeline_summary_path": None,
        "runner_stdout_path": "reports/workflow/automation/runs/20260325T010203Z-a1b2c3d4/runner_stdout.log",
        "runner_stderr_path": "reports/workflow/automation/runs/20260325T010203Z-a1b2c3d4/runner_stderr.log",
    }

    root = tmp_path / "reports" / "workflow" / "automation"
    paths = write_automation_outputs(record, root=root)

    assert Path(paths["latest_run_path"]).exists()
    assert Path(paths["latest_attention_json_path"]).exists()
    assert Path(paths["latest_attention_md_path"]).exists()

    history_lines = (root / "run_history.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(history_lines) == 1

    attention_payload = json.loads(Path(paths["latest_attention_json_path"]).read_text(encoding="utf-8"))
    assert {"attention_type", "automation_run_id", "suggested_next_action"} <= attention_payload.keys()

    attention_md = Path(paths["latest_attention_md_path"]).read_text(encoding="utf-8")
    assert "automation_run_id" in attention_md
    assert "workflow_status" in attention_md
    assert "runner_stdout" in attention_md
    assert "runner_stderr" in attention_md


def test_write_automation_outputs_keeps_existing_attention_on_success(tmp_path):
    from src.workflow.automation import write_automation_outputs

    root = tmp_path / "reports" / "workflow" / "automation"
    failed_record = {
        "automation_run_id": "20260325T010203Z-a1b2c3d4",
        "automation_started_at": "2026-03-25T01:02:03Z",
        "automation_finished_at": "2026-03-25T01:02:05Z",
        "runner_command": ["python", "/abs/scripts/run_end_to_end_workflow.py"],
        "runner_process_exit_code": 1,
        "wrapper_exit_code": 1,
        "run_id": None,
        "workflow_manifest": None,
        "workflow_status": "failed",
        "publish_executed": False,
        "manifest_exit_code": None,
        "failed_step": "automation_contract_error",
        "blocked_reasons": [],
        "health_check_report_path": None,
        "post_publish_health_check_report_path": None,
        "research_governance_pipeline_summary_path": None,
        "runner_stdout_path": "reports/workflow/automation/runs/20260325T010203Z-a1b2c3d4/runner_stdout.log",
        "runner_stderr_path": "reports/workflow/automation/runs/20260325T010203Z-a1b2c3d4/runner_stderr.log",
        "attention_type": "automation_contract_error",
        "suggested_next_action": "check stdout",
    }
    write_automation_outputs(failed_record, root=root)
    attention_before = (root / "latest_attention.json").read_text(encoding="utf-8")

    success_record = dict(failed_record)
    success_record.update(
        {
            "automation_run_id": "20260325T010210Z-e5f6g7h8",
            "runner_process_exit_code": 0,
            "wrapper_exit_code": 0,
            "workflow_status": "preflight_only",
            "attention_type": None,
        }
    )
    write_automation_outputs(success_record, root=root)

    assert (root / "latest_attention.json").read_text(encoding="utf-8") == attention_before


def test_write_automation_outputs_appends_history_without_overwriting(tmp_path):
    from src.workflow.automation import write_automation_outputs

    root = tmp_path / "reports" / "workflow" / "automation"
    base = {
        "automation_started_at": "2026-03-25T01:02:03Z",
        "automation_finished_at": "2026-03-25T01:02:05Z",
        "runner_command": ["python", "/abs/scripts/run_end_to_end_workflow.py"],
        "runner_process_exit_code": 0,
        "wrapper_exit_code": 0,
        "run_id": "20260325T010203Z-abcd1234",
        "workflow_manifest": "reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json",
        "workflow_status": "preflight_only",
        "publish_executed": False,
        "manifest_exit_code": 0,
        "failed_step": None,
        "blocked_reasons": [],
        "health_check_report_path": None,
        "post_publish_health_check_report_path": None,
        "research_governance_pipeline_summary_path": None,
        "runner_stdout_path": "reports/workflow/automation/runs/x/runner_stdout.log",
        "runner_stderr_path": "reports/workflow/automation/runs/x/runner_stderr.log",
    }
    write_automation_outputs({"automation_run_id": "20260325T010203Z-a1b2c3d4", **base}, root=root)
    write_automation_outputs({"automation_run_id": "20260325T010210Z-e5f6g7h8", **base}, root=root)

    history_lines = (root / "run_history.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(history_lines) == 2
    assert "20260325T010203Z-a1b2c3d4" in history_lines[0]
    assert "20260325T010210Z-e5f6g7h8" in history_lines[1]


def test_parse_workflow_contract_error_when_manifest_mismatches():
    from src.workflow.automation import validate_workflow_contract

    contract = {
        "run_id": "20260325T010203Z-abcd1234",
        "workflow_manifest": "reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json",
        "workflow_status": "failed",
        "publish_executed": False,
    }
    manifest_payload = {"run_id": "other", "status": "failed", "exit_code": 1}

    with pytest.raises(Exception):
        validate_workflow_contract(contract, manifest_payload, runner_process_exit_code=1)


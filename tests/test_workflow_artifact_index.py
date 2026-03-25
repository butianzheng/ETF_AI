from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_artifact_index_uses_complete_schema_and_effective_workdir_relative_paths(tmp_path: Path) -> None:
    from src.workflow.automation_index import build_artifact_index

    effective_root = tmp_path / "effective"
    effective_root.mkdir(parents=True, exist_ok=True)

    # Mix absolute/relative inputs; output must normalize to relpath relative to effective_workdir.
    manifest_abs = effective_root / "reports" / "workflow" / "runs" / "wf-001" / "workflow_manifest.json"
    manifest_abs.parent.mkdir(parents=True, exist_ok=True)
    manifest_abs.write_text("{}", encoding="utf-8")

    payload = build_artifact_index(
        record={
            "automation_run_id": "auto-001",
            "run_id": "wf-001",
            "workflow_status": "blocked",
            "automation_started_at": "2026-03-25T08:00:00Z",
            "automation_finished_at": "2026-03-25T08:01:00Z",
            "wrapper_exit_code": 2,
            "runner_process_exit_code": 2,
            "workflow_manifest": str(manifest_abs),
            "runner_stdout_path": "reports/workflow/automation/runs/auto-001/runner_stdout.log",
            "runner_stderr_path": "reports/workflow/automation/runs/auto-001/runner_stderr.log",
            "health_check_report_path": None,
            "post_publish_health_check_report_path": None,
            "research_governance_pipeline_summary_path": "reports/governance/pipeline/wf-001.json",
            "blocked_reasons": ["REGIME_MISMATCH"],
            "failed_step": None,
            "publish_executed": False,
            "suggested_next_action": "inspect blocked_reasons and governance review status",
            "requested_workdir": str(tmp_path / "requested"),
            "effective_workdir": str(effective_root),
            "outputs_fallback_used": True,
        },
        effective_workdir=effective_root,
        created_at="2026-03-25T08:01:02Z",
    )

    assert payload["source"] == "artifact_index"
    assert payload["automation_run_id"] == "auto-001"
    assert payload["run_id"] == "wf-001"
    assert payload["workflow_status"] == "blocked"
    assert payload["automation_started_at"] == "2026-03-25T08:00:00Z"
    assert payload["automation_finished_at"] == "2026-03-25T08:01:00Z"
    assert payload["wrapper_exit_code"] == 2
    assert payload["runner_process_exit_code"] == 2
    assert payload["manifest_path"] == "reports/workflow/runs/wf-001/workflow_manifest.json"
    assert payload["runner_stdout_path"] == "reports/workflow/automation/runs/auto-001/runner_stdout.log"
    assert payload["runner_stderr_path"] == "reports/workflow/automation/runs/auto-001/runner_stderr.log"
    assert payload["health_check_report_path"] is None
    assert payload["post_publish_health_check_report_path"] is None
    assert payload["research_governance_pipeline_summary_path"] == "reports/governance/pipeline/wf-001.json"
    assert payload["blocked_reasons"] == ["REGIME_MISMATCH"]
    assert payload["failed_step"] is None
    assert payload["suggested_next_action"] == "inspect blocked_reasons and governance review status"
    assert payload["publish_executed"] is False
    assert payload["created_at"] == "2026-03-25T08:01:02Z"
    assert payload["requested_workdir"] == str(tmp_path / "requested")
    assert payload["effective_workdir"] == str(effective_root)
    assert payload["outputs_fallback_used"] is True

    # Schema must be locked: missing fields must still exist (explicit null).
    expected_keys = {
        "source",
        "automation_run_id",
        "run_id",
        "workflow_status",
        "automation_started_at",
        "automation_finished_at",
        "wrapper_exit_code",
        "runner_process_exit_code",
        "manifest_path",
        "runner_stdout_path",
        "runner_stderr_path",
        "health_check_report_path",
        "post_publish_health_check_report_path",
        "research_governance_pipeline_summary_path",
        "blocked_reasons",
        "failed_step",
        "suggested_next_action",
        "publish_executed",
        "created_at",
        "requested_workdir",
        "effective_workdir",
        "outputs_fallback_used",
    }
    assert set(payload.keys()) == expected_keys


def test_build_artifact_index_normalizes_blocked_reasons_and_keeps_missing_fields_as_null(tmp_path: Path) -> None:
    from src.workflow.automation_index import build_artifact_index

    effective_root = tmp_path / "wd"
    effective_root.mkdir(parents=True, exist_ok=True)

    payload = build_artifact_index(
        record={
            "automation_run_id": "auto-002",
            "run_id": None,
            "workflow_status": None,
            # Intentionally sparse record: helper must still output full schema with explicit nulls.
            "workflow_manifest": None,
            "blocked_reasons": "ONE_REASON",
            "requested_workdir": str(tmp_path),
            "effective_workdir": str(effective_root),
        },
        effective_workdir=effective_root,
        created_at="2026-03-25T08:02:00Z",
    )

    assert payload["blocked_reasons"] == ["ONE_REASON"]
    assert payload["manifest_path"] is None
    assert payload["runner_stdout_path"] is None
    assert payload["runner_stderr_path"] is None
    assert payload["publish_executed"] is None
    assert payload["outputs_fallback_used"] is None


def test_artifact_index_relpath_and_write_artifact_index(tmp_path: Path) -> None:
    from src.workflow.automation_index import artifact_index_relpath
    from src.workflow.automation_index import write_artifact_index

    effective_root = tmp_path / "wd"
    effective_root.mkdir(parents=True, exist_ok=True)

    relpath = artifact_index_relpath("auto-003")
    assert relpath == "reports/workflow/automation/runs/auto-003/artifact_index.json"

    payload = {
        "source": "artifact_index",
        "automation_run_id": "auto-003",
        "run_id": "wf-003",
        "workflow_status": "failed",
        "automation_started_at": None,
        "automation_finished_at": None,
        "wrapper_exit_code": 1,
        "runner_process_exit_code": 1,
        "manifest_path": "reports/workflow/runs/wf-003/workflow_manifest.json",
        "runner_stdout_path": None,
        "runner_stderr_path": None,
        "health_check_report_path": None,
        "post_publish_health_check_report_path": None,
        "research_governance_pipeline_summary_path": None,
        "blocked_reasons": [],
        "failed_step": "preflight",
        "suggested_next_action": None,
        "publish_executed": False,
        "created_at": "2026-03-25T08:03:00Z",
        "requested_workdir": str(effective_root),
        "effective_workdir": str(effective_root),
        "outputs_fallback_used": False,
    }
    write_artifact_index(payload, effective_workdir=effective_root)
    assert (effective_root / relpath).exists()


def test_iter_history_records_skips_bad_lines_and_keeps_order(tmp_path: Path) -> None:
    from src.workflow.automation_index import iter_history_records

    history_path = tmp_path / "reports" / "workflow" / "automation" / "run_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        "\n".join(
            [
                json.dumps({"automation_run_id": "auto-001", "automation_finished_at": "2026-03-25T08:01:00Z"}),
                "{bad json",
                "",  # blank line
                json.dumps({"automation_run_id": "auto-002", "automation_finished_at": "2026-03-25T08:02:00Z"}),
                "{\"automation_run_id\": \"auto-003\"",  # truncated tail
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    records = list(iter_history_records(tmp_path))
    assert [record["automation_run_id"] for record in records] == ["auto-001", "auto-002"]


def test_iter_history_records_raises_value_error_for_history_path_error(tmp_path: Path) -> None:
    from src.workflow.automation_index import iter_history_records

    history_path = tmp_path / "reports" / "workflow" / "automation" / "run_history.jsonl"
    history_path.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ValueError, match="failed to read"):
        list(iter_history_records(tmp_path))


def test_find_run_view_prefers_automation_run_id_then_latest_workflow_run_id(tmp_path: Path) -> None:
    from src.workflow.automation_index import find_run_view

    history_path = tmp_path / "reports" / "workflow" / "automation" / "run_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "automation_run_id": "auto-old",
                        "run_id": "wf-dup",
                        "workflow_status": "failed",
                        "automation_started_at": "2026-03-25T08:00:00Z",
                        "automation_finished_at": "2026-03-25T08:01:00Z",
                        "wrapper_exit_code": 1,
                        "runner_process_exit_code": 1,
                        "workflow_manifest": "reports/workflow/runs/wf-dup/workflow_manifest.json",
                        "runner_stdout_path": "reports/workflow/automation/runs/auto-old/runner_stdout.log",
                        "runner_stderr_path": "reports/workflow/automation/runs/auto-old/runner_stderr.log",
                        "failed_step": "preflight",
                        "blocked_reasons": [],
                        "publish_executed": False,
                        "requested_workdir": str(tmp_path),
                        "effective_workdir": str(tmp_path),
                    }
                ),
                json.dumps(
                    {
                        "automation_run_id": "auto-new",
                        "run_id": "wf-dup",
                        "workflow_status": "succeeded",
                        "automation_started_at": "2026-03-25T09:00:00Z",
                        "automation_finished_at": "2026-03-25T09:01:00Z",
                        "wrapper_exit_code": 0,
                        "runner_process_exit_code": 0,
                        "workflow_manifest": "reports/workflow/runs/wf-dup/workflow_manifest.json",
                        "runner_stdout_path": "reports/workflow/automation/runs/auto-new/runner_stdout.log",
                        "runner_stderr_path": "reports/workflow/automation/runs/auto-new/runner_stderr.log",
                        "failed_step": None,
                        "blocked_reasons": [],
                        "publish_executed": False,
                        "requested_workdir": str(tmp_path),
                        "effective_workdir": str(tmp_path),
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    by_automation = find_run_view(tmp_path, run_id="auto-old")
    by_workflow = find_run_view(tmp_path, run_id="wf-dup")
    assert by_automation["automation_run_id"] == "auto-old"
    assert by_workflow["automation_run_id"] == "auto-new"


def test_rebuild_legacy_detail_view_from_latest_record(tmp_path: Path) -> None:
    from src.workflow.automation_index import rebuild_legacy_detail_view

    record = {
        "automation_run_id": "auto-004",
        "run_id": "wf-004",
        "workflow_status": "failed",
        "automation_started_at": "2026-03-25T09:00:00Z",
        "automation_finished_at": "2026-03-25T09:01:00Z",
        "wrapper_exit_code": 1,
        "runner_process_exit_code": 1,
        "workflow_manifest": "reports/workflow/runs/wf-004/workflow_manifest.json",
        "runner_stdout_path": "reports/workflow/automation/runs/auto-004/runner_stdout.log",
        "runner_stderr_path": "reports/workflow/automation/runs/auto-004/runner_stderr.log",
        "failed_step": "preflight",
        "blocked_reasons": [],
        "publish_executed": False,
        "requested_workdir": str(tmp_path),
        "effective_workdir": str(tmp_path),
        "suggested_next_action": "inspect failed_step=preflight and workflow manifest",
    }

    payload = rebuild_legacy_detail_view(record, effective_workdir=tmp_path, source="legacy_fallback")

    assert payload["source"] == "legacy_fallback"
    assert payload["automation_run_id"] == "auto-004"
    assert payload["run_id"] == "wf-004"
    assert payload["status"] == "failed"
    assert payload["started_at"] == "2026-03-25T09:00:00Z"
    assert payload["finished_at"] == "2026-03-25T09:01:00Z"
    assert payload["failed_step"] == "preflight"
    assert payload["manifest_path"] == str(
        tmp_path / "reports" / "workflow" / "runs" / "wf-004" / "workflow_manifest.json"
    )
    assert payload["runner_stdout_path"] == str(
        tmp_path / "reports" / "workflow" / "automation" / "runs" / "auto-004" / "runner_stdout.log"
    )
    assert payload["runner_stderr_path"] == str(
        tmp_path / "reports" / "workflow" / "automation" / "runs" / "auto-004" / "runner_stderr.log"
    )
    assert payload["suggested_next_action"] == "inspect failed_step=preflight and workflow manifest"


def test_rebuild_legacy_detail_view_raises_for_non_string_manifest(tmp_path: Path) -> None:
    from src.workflow.automation_index import rebuild_legacy_detail_view

    record = {
        "automation_run_id": "auto-005",
        "run_id": "wf-005",
        "workflow_status": "failed",
        "automation_started_at": "2026-03-25T09:00:00Z",
        "automation_finished_at": "2026-03-25T09:01:00Z",
        "wrapper_exit_code": 1,
        "runner_process_exit_code": 1,
        "workflow_manifest": ["bad"],
    }

    with pytest.raises(ValueError, match="workflow_manifest"):
        rebuild_legacy_detail_view(record, effective_workdir=tmp_path, source="legacy_fallback")


def test_load_latest_run_view_falls_back_to_workflow_summary_when_latest_missing(tmp_path: Path) -> None:
    from src.workflow.automation_index import load_latest_run_view

    _write_json(
        tmp_path / "reports" / "workflow" / "end_to_end_workflow_summary.json",
        {
            "run_id": "wf-sum-001",
            "status": "blocked",
            "started_at": "2026-03-25T10:00:00Z",
            "finished_at": "2026-03-25T10:01:00Z",
            "workflow_manifest_path": "reports/workflow/runs/wf-sum-001/workflow_manifest.json",
            "publish_result": {"executed": True},
            "research_governance_result": {"blocked_reasons": ["REGIME_MISMATCH"]},
            "failed_step": None,
        },
    )

    view = load_latest_run_view(tmp_path)
    assert view is not None
    assert view["source"] == "workflow_summary_fallback"
    assert view["run_id"] == "wf-sum-001"
    assert view["status"] == "blocked"
    assert view["publish_executed"] is True
    assert view["failed_step"] is None
    assert view["blocked_reasons"] == ["REGIME_MISMATCH"]
    assert view["suggested_next_action"] == "inspect blocked_reasons and governance review status"
    assert view["manifest_path"] == str(
        tmp_path / "reports" / "workflow" / "runs" / "wf-sum-001" / "workflow_manifest.json"
    )


def test_load_latest_run_view_raises_when_latest_exists_but_missing_required_fields(tmp_path: Path) -> None:
    from src.workflow.automation_index import load_latest_run_view

    # latest_run.json exists but is missing required fields: should error, not silently fallback.
    _write_json(
        tmp_path / "reports" / "workflow" / "automation" / "latest_run.json",
        {"automation_run_id": "auto-err"},
    )

    with pytest.raises(ValueError, match="missing fields"):
        load_latest_run_view(tmp_path)


def test_load_latest_run_view_raises_when_legacy_manifest_invalid_type(tmp_path: Path) -> None:
    from src.workflow.automation_index import load_latest_run_view

    _write_json(
        tmp_path / "reports" / "workflow" / "automation" / "latest_run.json",
        {
            "automation_run_id": "auto-bad-manifest",
            "run_id": "wf-bad-manifest",
            "workflow_status": "failed",
            "automation_started_at": "2026-03-25T08:00:00Z",
            "automation_finished_at": "2026-03-25T08:01:00Z",
            "wrapper_exit_code": 1,
            "runner_process_exit_code": 1,
            "publish_executed": False,
            "workflow_manifest": ["bad"],
        },
    )

    with pytest.raises(ValueError, match="workflow_manifest"):
        load_latest_run_view(tmp_path)


def test_find_run_view_raises_when_artifact_index_json_exists_but_invalid(tmp_path: Path) -> None:
    from src.workflow.automation_index import find_run_view

    history_path = tmp_path / "reports" / "workflow" / "automation" / "run_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps(
            {
                "automation_run_id": "auto-idx-bad",
                "run_id": "wf-idx-bad",
                "workflow_status": "failed",
                "automation_started_at": "2026-03-25T08:00:00Z",
                "automation_finished_at": "2026-03-25T08:01:00Z",
                "wrapper_exit_code": 1,
                "runner_process_exit_code": 1,
                "workflow_manifest": "reports/workflow/runs/wf-idx-bad/workflow_manifest.json",
                "runner_stdout_path": "reports/workflow/automation/runs/auto-idx-bad/runner_stdout.log",
                "runner_stderr_path": "reports/workflow/automation/runs/auto-idx-bad/runner_stderr.log",
                "failed_step": "preflight",
                "blocked_reasons": [],
                "publish_executed": False,
                "requested_workdir": str(tmp_path),
                "effective_workdir": str(tmp_path),
                "artifact_index_path": "reports/workflow/automation/runs/auto-idx-bad/artifact_index.json",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    index_path = tmp_path / "reports" / "workflow" / "automation" / "runs" / "auto-idx-bad" / "artifact_index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("{}", encoding="utf-8")  # dict but missing locked schema fields

    with pytest.raises(ValueError, match="artifact index schema"):
        find_run_view(tmp_path, run_id="auto-idx-bad")


def test_load_latest_run_view_raises_when_artifact_index_json_exists_but_damaged_or_missing_fields(
    tmp_path: Path,
) -> None:
    from src.workflow.automation_index import load_latest_run_view

    _write_json(
        tmp_path / "reports" / "workflow" / "automation" / "latest_run.json",
        {
            "automation_run_id": "auto-latest",
            "run_id": "wf-latest",
            "workflow_status": "failed",
            "automation_started_at": "2026-03-25T08:00:00Z",
            "automation_finished_at": "2026-03-25T08:01:00Z",
            "wrapper_exit_code": 1,
            "runner_process_exit_code": 1,
            "publish_executed": False,
            "workflow_manifest": "reports/workflow/runs/wf-latest/workflow_manifest.json",
            "artifact_index_path": "reports/workflow/automation/runs/auto-latest/artifact_index.json",
        },
    )

    index_path = tmp_path / "reports" / "workflow" / "automation" / "runs" / "auto-latest" / "artifact_index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("{bad json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid json"):
        load_latest_run_view(tmp_path)


def test_load_latest_run_view_prefers_artifact_index_when_present_and_valid(tmp_path: Path) -> None:
    from src.workflow.automation_index import artifact_index_relpath
    from src.workflow.automation_index import build_artifact_index
    from src.workflow.automation_index import load_latest_run_view
    from src.workflow.automation_index import write_artifact_index

    effective_root = tmp_path
    index_payload = build_artifact_index(
        record={
            "automation_run_id": "auto-010",
            "run_id": "wf-010",
            "workflow_status": "failed",
            "automation_started_at": "2026-03-25T08:00:00Z",
            "automation_finished_at": "2026-03-25T08:01:00Z",
            "wrapper_exit_code": 1,
            "runner_process_exit_code": 1,
            "workflow_manifest": "reports/workflow/runs/wf-010/workflow_manifest.json",
            "runner_stdout_path": "reports/workflow/automation/runs/auto-010/runner_stdout.log",
            "runner_stderr_path": "reports/workflow/automation/runs/auto-010/runner_stderr.log",
            "blocked_reasons": [],
            "failed_step": "preflight",
            "publish_executed": False,
            "requested_workdir": str(effective_root),
            "effective_workdir": str(effective_root),
            "outputs_fallback_used": False,
        },
        effective_workdir=effective_root,
        created_at="2026-03-25T08:01:02Z",
    )
    write_artifact_index(index_payload, effective_workdir=effective_root)

    _write_json(
        tmp_path / "reports" / "workflow" / "automation" / "latest_run.json",
        {
            "automation_run_id": "auto-010",
            "run_id": "wf-010",
            "workflow_status": "failed",
            "automation_started_at": "2026-03-25T08:00:00Z",
            "automation_finished_at": "2026-03-25T08:01:00Z",
            "wrapper_exit_code": 1,
            "runner_process_exit_code": 1,
            "publish_executed": False,
            "workflow_manifest": "reports/workflow/runs/wf-010/workflow_manifest.json",
            "artifact_index_path": artifact_index_relpath("auto-010"),
        },
    )

    view = load_latest_run_view(tmp_path)
    assert view is not None
    assert view["source"] == "artifact_index"
    assert view["automation_run_id"] == "auto-010"
    assert view["run_id"] == "wf-010"
    assert view["failed_step"] == "preflight"
    assert view["manifest_path"] == str(tmp_path / "reports/workflow/runs/wf-010/workflow_manifest.json")


def test_find_run_view_prefers_artifact_index_when_present_and_valid(tmp_path: Path) -> None:
    from src.workflow.automation_index import artifact_index_relpath
    from src.workflow.automation_index import build_artifact_index
    from src.workflow.automation_index import find_run_view
    from src.workflow.automation_index import write_artifact_index

    effective_root = tmp_path
    index_payload = build_artifact_index(
        record={
            "automation_run_id": "auto-020",
            "run_id": "wf-020",
            "workflow_status": "succeeded",
            "automation_started_at": "2026-03-25T09:00:00Z",
            "automation_finished_at": "2026-03-25T09:01:00Z",
            "wrapper_exit_code": 0,
            "runner_process_exit_code": 0,
            "workflow_manifest": "reports/workflow/runs/wf-020/workflow_manifest.json",
            "blocked_reasons": [],
            "failed_step": None,
            "publish_executed": False,
            "requested_workdir": str(effective_root),
            "effective_workdir": str(effective_root),
            "outputs_fallback_used": False,
        },
        effective_workdir=effective_root,
        created_at="2026-03-25T09:01:02Z",
    )
    write_artifact_index(index_payload, effective_workdir=effective_root)

    history_path = tmp_path / "reports" / "workflow" / "automation" / "run_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps(
            {
                "automation_run_id": "auto-020",
                "run_id": "wf-020",
                "workflow_status": "succeeded",
                "automation_finished_at": "2026-03-25T09:01:00Z",
                "artifact_index_path": artifact_index_relpath("auto-020"),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    view = find_run_view(tmp_path, run_id="auto-020")
    assert view is not None
    assert view["source"] == "artifact_index"
    assert view["automation_run_id"] == "auto-020"
    assert view["run_id"] == "wf-020"


def test_load_latest_run_view_raises_when_artifact_index_semantically_invalid(tmp_path: Path) -> None:
    from src.workflow.automation_index import artifact_index_relpath
    from src.workflow.automation_index import build_artifact_index
    from src.workflow.automation_index import load_latest_run_view
    from src.workflow.automation_index import write_artifact_index

    effective_root = tmp_path
    payload = build_artifact_index(
        record={
            "automation_run_id": "auto-sem-1",
            "run_id": "wf-sem-1",
            "workflow_status": None,  # semantic damage: required core field null
            "automation_started_at": "2026-03-25T08:00:00Z",
            "automation_finished_at": "2026-03-25T08:01:00Z",
            "wrapper_exit_code": 1,
            "runner_process_exit_code": 1,
            "workflow_manifest": "reports/workflow/runs/wf-sem-1/workflow_manifest.json",
            "blocked_reasons": [],
            "failed_step": None,
            "publish_executed": False,
            "requested_workdir": str(effective_root),
            "effective_workdir": str(effective_root),
            "outputs_fallback_used": False,
        },
        effective_workdir=effective_root,
        created_at="2026-03-25T08:01:02Z",
    )
    write_artifact_index(payload, effective_workdir=effective_root)

    _write_json(
        tmp_path / "reports" / "workflow" / "automation" / "latest_run.json",
        {
            "automation_run_id": "auto-sem-1",
            "run_id": "wf-sem-1",
            "workflow_status": "failed",
            "automation_started_at": "2026-03-25T08:00:00Z",
            "automation_finished_at": "2026-03-25T08:01:00Z",
            "wrapper_exit_code": 1,
            "runner_process_exit_code": 1,
            "publish_executed": False,
            "workflow_manifest": "reports/workflow/runs/wf-sem-1/workflow_manifest.json",
            "artifact_index_path": artifact_index_relpath("auto-sem-1"),
        },
    )

    with pytest.raises(ValueError, match="semantic error"):
        load_latest_run_view(tmp_path)


def test_find_run_view_raises_when_artifact_index_semantically_invalid_type(tmp_path: Path) -> None:
    from src.workflow.automation_index import artifact_index_relpath
    from src.workflow.automation_index import build_artifact_index
    from src.workflow.automation_index import find_run_view
    from src.workflow.automation_index import write_artifact_index

    effective_root = tmp_path
    payload = build_artifact_index(
        record={
            "automation_run_id": "auto-sem-2",
            "run_id": "wf-sem-2",
            "workflow_status": "failed",
            "automation_started_at": "2026-03-25T08:00:00Z",
            "automation_finished_at": "2026-03-25T08:01:00Z",
            "wrapper_exit_code": 1,
            "runner_process_exit_code": 1,
            "workflow_manifest": "reports/workflow/runs/wf-sem-2/workflow_manifest.json",
            "blocked_reasons": [],
            "failed_step": None,
            "publish_executed": False,
            "requested_workdir": str(effective_root),
            "effective_workdir": str(effective_root),
            "outputs_fallback_used": False,
        },
        effective_workdir=effective_root,
        created_at="2026-03-25T08:01:02Z",
    )
    payload["manifest_path"] = 123  # type damage, but schema still complete
    write_artifact_index(payload, effective_workdir=effective_root)

    history_path = tmp_path / "reports" / "workflow" / "automation" / "run_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps(
            {
                "automation_run_id": "auto-sem-2",
                "run_id": "wf-sem-2",
                "workflow_status": "failed",
                "automation_finished_at": "2026-03-25T08:01:00Z",
                "artifact_index_path": artifact_index_relpath("auto-sem-2"),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manifest_path"):
        find_run_view(tmp_path, run_id="auto-sem-2")

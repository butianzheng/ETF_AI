"""Local workflow automation helper module.

This module is consumed by a local wrapper script (planned) to:
- parse runner stdout contract (key=value lines)
- validate contract vs workflow manifest payload
- write automation indexes (history/latest) and attention summaries
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
from typing import Any


class WorkflowContractError(ValueError):
    """Raised when runner stdout contract is missing/invalid or mismatches manifest."""


_CONTRACT_KEYS = ("run_id", "workflow_manifest", "workflow_status", "publish_executed")
_ATTENTION_TYPES_ALLOWED = ("automation_contract_error", "workflow_blocked", "workflow_failed")


def _normalize_bool(value: Any, *, default: bool = False, field_name: str = "bool") -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no"):
            return False
    raise WorkflowContractError(f"invalid {field_name} value: {value!r}")


def generate_automation_run_id(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return f"{current:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"


def parse_workflow_stdout_contract(stdout: str) -> dict[str, Any]:
    """Parse runner stdout contract lines into a dict.

    Expected lines (order not important, may have other noise lines):
    - run_id=<run id>
    - workflow_manifest=<path>
    - workflow_status=<status>
    - publish_executed=true|false
    """

    extracted: dict[str, str] = {}
    for raw in (stdout or "").splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if key in _CONTRACT_KEYS:
            extracted[key] = value.strip()

    missing = [key for key in _CONTRACT_KEYS if key not in extracted]
    if missing:
        raise WorkflowContractError(f"runner stdout contract missing keys: {', '.join(missing)}")

    run_id = extracted.get("run_id") or ""
    if not run_id:
        raise WorkflowContractError("runner stdout contract empty run_id")

    workflow_manifest = extracted.get("workflow_manifest") or ""
    if not workflow_manifest:
        raise WorkflowContractError("runner stdout contract empty workflow_manifest")

    workflow_status = extracted.get("workflow_status") or ""
    if not workflow_status:
        raise WorkflowContractError("runner stdout contract empty workflow_status")

    publish_executed = _normalize_bool(
        extracted.get("publish_executed"),
        field_name="publish_executed",
    )

    return {
        "run_id": run_id,
        "workflow_manifest": workflow_manifest,
        "workflow_status": workflow_status,
        "publish_executed": publish_executed,
    }


def validate_workflow_contract(
    contract: dict[str, Any],
    manifest_payload: dict[str, Any],
    runner_process_exit_code: int | None,
) -> None:
    """Validate manifest payload matches stdout contract (best-effort, strict on run_id/status)."""

    if not isinstance(contract, dict) or not isinstance(manifest_payload, dict):
        raise WorkflowContractError("contract/manifest_payload must be dict")

    manifest_path_value = contract.get("workflow_manifest")
    if not isinstance(manifest_path_value, str) or not manifest_path_value.strip():
        raise WorkflowContractError("runner contract missing workflow_manifest")
    manifest_path = Path(manifest_path_value)
    if not manifest_path.exists():
        raise WorkflowContractError(f"workflow_manifest path does not exist: {manifest_path_value}")

    contract_run_id = contract.get("run_id")
    manifest_run_id = manifest_payload.get("run_id")
    if contract_run_id and manifest_run_id and str(contract_run_id) != str(manifest_run_id):
        raise WorkflowContractError(
            f"manifest run_id mismatch: contract={contract_run_id!r} manifest={manifest_run_id!r}"
        )

    contract_status = contract.get("workflow_status")
    manifest_status = manifest_payload.get("status")
    if contract_status and manifest_status and str(contract_status) != str(manifest_status):
        raise WorkflowContractError(
            f"manifest status mismatch: contract={contract_status!r} manifest={manifest_status!r}"
        )

    if runner_process_exit_code is not None and manifest_payload.get("exit_code") is not None:
        try:
            manifest_exit_code = int(manifest_payload.get("exit_code"))
        except Exception as e:  # pragma: no cover
            raise WorkflowContractError(f"invalid manifest exit_code: {manifest_payload.get('exit_code')!r}") from e
        if int(runner_process_exit_code) != manifest_exit_code:
            raise WorkflowContractError(
                f"manifest exit_code mismatch: runner={runner_process_exit_code} manifest={manifest_exit_code}"
            )


def build_automation_record(
    *,
    automation_run_id: str,
    automation_started_at: str,
    automation_finished_at: str,
    runner_command: list[str],
    runner_process_exit_code: int | None,
    wrapper_exit_code: int,
    contract: dict[str, Any] | None = None,
    manifest_payload: dict[str, Any] | None = None,
    runner_stdout_path: str | None = None,
    runner_stderr_path: str | None = None,
    attention_type: str | None = None,
    suggested_next_action: str | None = None,
) -> dict[str, Any]:
    contract = contract or {}
    manifest_payload = manifest_payload or {}

    health_check_report_path = (manifest_payload.get("health_check_result") or {}).get("report_path")
    post_publish_health_check_report_path = (manifest_payload.get("post_publish_health_check_result") or {}).get(
        "report_path"
    )
    rg_summary_path = (manifest_payload.get("research_governance_result") or {}).get("pipeline_summary")
    blocked_reasons = (manifest_payload.get("research_governance_result") or {}).get("blocked_reasons") or []
    if not isinstance(blocked_reasons, list):
        blocked_reasons = [blocked_reasons]

    return {
        "automation_run_id": automation_run_id,
        "automation_started_at": automation_started_at,
        "automation_finished_at": automation_finished_at,
        "runner_command": runner_command,
        "runner_process_exit_code": runner_process_exit_code,
        "wrapper_exit_code": wrapper_exit_code,
        "run_id": contract.get("run_id", manifest_payload.get("run_id")),
        "workflow_manifest": contract.get("workflow_manifest", manifest_payload.get("workflow_manifest_path")),
        "workflow_status": contract.get("workflow_status", manifest_payload.get("status")),
        "publish_executed": (
            _normalize_bool(contract.get("publish_executed"), field_name="publish_executed")
            if "publish_executed" in contract
            else _normalize_bool(
                (manifest_payload.get("publish_result") or {}).get("executed"),
                default=False,
                field_name="publish_executed",
            )
        ),
        "manifest_exit_code": manifest_payload.get("exit_code"),
        "failed_step": manifest_payload.get("failed_step"),
        "blocked_reasons": blocked_reasons,
        "health_check_report_path": health_check_report_path,
        "post_publish_health_check_report_path": post_publish_health_check_report_path,
        "research_governance_pipeline_summary_path": rg_summary_path,
        "runner_stdout_path": runner_stdout_path,
        "runner_stderr_path": runner_stderr_path,
        "attention_type": attention_type,
        "suggested_next_action": suggested_next_action,
    }


def write_runner_logs(
    automation_run_id: str,
    stdout: str,
    stderr: str,
    root: Path,
) -> dict[str, str]:
    run_dir = root / "runs" / automation_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = run_dir / "runner_stdout.log"
    stderr_path = run_dir / "runner_stderr.log"
    stdout_path.write_text(stdout or "", encoding="utf-8")
    stderr_path.write_text(stderr or "", encoding="utf-8")
    return {"runner_stdout_path": str(stdout_path), "runner_stderr_path": str(stderr_path)}


def should_update_attention(record: dict[str, Any]) -> bool:
    attention_type = record.get("attention_type")
    status = record.get("workflow_status")
    if status in ("succeeded", "preflight_only"):
        return False
    if status in ("blocked", "failed"):
        return True

    failed_step = record.get("failed_step")
    if failed_step == "automation_contract_error":
        return True
    return attention_type == "automation_contract_error"


def _default_suggested_next_action(attention_type: str, record: dict[str, Any]) -> str:
    if attention_type == "automation_contract_error":
        return "check runner stdout/stderr logs and wrapper parsing"
    if attention_type == "workflow_blocked":
        return "inspect blocked_reasons and governance review status"
    if attention_type == "workflow_failed":
        failed_step = record.get("failed_step")
        if failed_step:
            return f"inspect failed_step={failed_step} and runner logs"
        return "inspect runner logs and workflow manifest"
    return "inspect latest_run.json and runner logs"


def _build_attention_payload(record: dict[str, Any]) -> dict[str, Any]:
    workflow_status = record.get("workflow_status")
    attention_type = record.get("attention_type")
    if attention_type not in _ATTENTION_TYPES_ALLOWED and attention_type is not None:
        attention_type = None
    if record.get("failed_step") == "automation_contract_error":
        attention_type = "automation_contract_error"
    elif workflow_status == "blocked":
        attention_type = "workflow_blocked"
    elif workflow_status == "failed":
        attention_type = "workflow_failed"
    elif attention_type == "automation_contract_error":
        attention_type = "automation_contract_error"
    else:
        raise WorkflowContractError(f"cannot infer attention_type from record: workflow_status={workflow_status!r}")

    suggested_next_action = record.get("suggested_next_action") or _default_suggested_next_action(attention_type, record)

    payload = {
        "attention_type": attention_type,
        "automation_run_id": record.get("automation_run_id"),
        "run_id": record.get("run_id"),
        "workflow_status": workflow_status,
        "failed_step": record.get("failed_step"),
        "blocked_reasons": record.get("blocked_reasons"),
        "workflow_manifest": record.get("workflow_manifest"),
        "health_check_report_path": record.get("health_check_report_path"),
        "post_publish_health_check_report_path": record.get("post_publish_health_check_report_path"),
        "research_governance_pipeline_summary_path": record.get("research_governance_pipeline_summary_path"),
        "runner_process_exit_code": record.get("runner_process_exit_code"),
        "runner_stdout_path": record.get("runner_stdout_path"),
        "runner_stderr_path": record.get("runner_stderr_path"),
        "suggested_next_action": suggested_next_action,
    }
    return payload


def render_attention_markdown(record: dict[str, Any]) -> str:
    attention = _build_attention_payload(record)
    blocked_reasons = attention.get("blocked_reasons") or []
    if isinstance(blocked_reasons, list):
        blocked_text = ", ".join(str(item) for item in blocked_reasons) if blocked_reasons else "(none)"
    else:
        blocked_text = str(blocked_reasons)

    lines = [
        "# Workflow Automation Attention",
        "",
        f"attention_type: {attention.get('attention_type')}",
        f"automation_run_id: {attention.get('automation_run_id')}",
        f"run_id: {attention.get('run_id')}",
        f"workflow_status: {attention.get('workflow_status')}",
        f"failed_step: {attention.get('failed_step')}",
        f"blocked_reasons: {blocked_text}",
        "",
        f"workflow_manifest: {attention.get('workflow_manifest')}",
        f"health_check_report_path: {attention.get('health_check_report_path')}",
        f"post_publish_health_check_report_path: {attention.get('post_publish_health_check_report_path')}",
        f"research_governance_pipeline_summary_path: {attention.get('research_governance_pipeline_summary_path')}",
        "",
        f"runner_stdout: {attention.get('runner_stdout_path')}",
        f"runner_stderr: {attention.get('runner_stderr_path')}",
        "",
        f"suggested_next_action: {attention.get('suggested_next_action')}",
        "",
    ]
    return "\n".join(lines)


def write_automation_outputs(record: dict[str, Any], *, root: Path) -> dict[str, str]:
    if not isinstance(record, dict):
        raise ValueError("record must be a dict")
    if not record.get("automation_run_id"):
        raise ValueError("record missing automation_run_id")

    root.mkdir(parents=True, exist_ok=True)

    run_history_path = root / "run_history.jsonl"
    latest_run_path = root / "latest_run.json"
    latest_attention_json_path = root / "latest_attention.json"
    latest_attention_md_path = root / "latest_attention.md"

    # Append history (never overwrite).
    with open(run_history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    latest_run_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    updated_attention = should_update_attention(record)
    if updated_attention:
        attention_payload = _build_attention_payload(record)
        latest_attention_json_path.write_text(
            json.dumps(attention_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        latest_attention_md_path.write_text(render_attention_markdown(record), encoding="utf-8")

    out: dict[str, Any] = {
        "run_history_path": str(run_history_path),
        "latest_run_path": str(latest_run_path),
        "latest_attention_json_path": str(latest_attention_json_path) if updated_attention else None,
        "latest_attention_md_path": str(latest_attention_md_path) if updated_attention else None,
    }
    return out

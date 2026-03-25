"""Workflow manifest 写盘与 run_id 生成。"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
from typing import Any

_REQUIRED_PAYLOAD_KEYS = (
    "run_id",
    "started_at",
    "finished_at",
    "status",
    "exit_code",
    "preflight_result",
)


def generate_run_id(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return f"{current:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"


def write_workflow_manifest(payload: dict[str, Any], root: Path) -> dict[str, str]:
    missing = [key for key in _REQUIRED_PAYLOAD_KEYS if key not in payload]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"workflow manifest payload missing required keys: {joined}")

    manifest_path = root / "runs" / str(payload["run_id"]) / "workflow_manifest.json"
    latest_path = root / "end_to_end_workflow_summary.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload["workflow_manifest_path"] = str(manifest_path)

    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    manifest_path.write_text(serialized, encoding="utf-8")
    latest_path.write_text(serialized, encoding="utf-8")
    return {"manifest_path": str(manifest_path), "latest_summary_path": str(latest_path)}

"""Local workflow automation wrapper.

This script runs the existing workflow runner as a subprocess, captures stdout/stderr,
writes automation indexes (latest/history) and attention summaries.

Key behaviors (Task 2):
- `--workdir` controls the subprocess cwd (default: repo root).
- runner args are passed after `--`.
- runner is invoked via an absolute path.
- when `workdir != repo root`, create `workdir/config -> <repo>/config` symlink.
- write runner stdout/stderr logs before parsing stdout contract.
- wrapper exit code inherits runner exit code unless wrapper/contract error => 1.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.workflow.automation import (  # noqa: E402
    WorkflowContractError,
    build_automation_record,
    generate_automation_run_id,
    parse_workflow_stdout_contract,
    validate_workflow_contract,
    write_automation_outputs,
    write_runner_logs,
)


RUNNER_SCRIPT = (PROJECT_ROOT / "scripts" / "run_end_to_end_workflow.py").resolve()


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local workflow automation wrapper")
    parser.add_argument("--workdir", default=None, help="Runner subprocess working directory (default: repo root)")
    parser.add_argument("runner_args", nargs=argparse.REMAINDER, help="Runner args (pass after `--`)")
    return parser.parse_args(argv)


def _ensure_workdir_config_symlink(*, workdir: Path, repo_root: Path) -> None:
    config_target = (repo_root / "config").resolve()
    link_path = workdir / "config"

    if link_path.exists() or link_path.is_symlink():
        if link_path.is_symlink() and link_path.resolve() == config_target:
            return
        raise RuntimeError(f"workdir config path already exists and is not the expected symlink: {link_path}")

    link_path.symlink_to(config_target, target_is_directory=True)


def _rel_to_workdir(path: str | Path | None, *, workdir: Path) -> str | None:
    if path is None:
        return None
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(workdir))
    except Exception:
        return str(resolved)


def _resolve_manifest_path(value: str, *, workdir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (workdir / path).resolve()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = PROJECT_ROOT.resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else repo_root
    workdir.mkdir(parents=True, exist_ok=True)

    if workdir != repo_root:
        _ensure_workdir_config_symlink(workdir=workdir, repo_root=repo_root)

    automation_run_id = generate_automation_run_id()
    started_at = _iso_utc_now()
    automation_root = workdir / "reports" / "workflow" / "automation"

    runner_args = list(args.runner_args or [])
    runner_command = [sys.executable, str(RUNNER_SCRIPT), *runner_args]

    proc = subprocess.run(
        runner_command,
        cwd=str(workdir),
        text=True,
        capture_output=True,
        check=False,
    )
    runner_exit_code = proc.returncode

    # Always persist raw logs first (even if contract parsing fails).
    runner_logs_abs = write_runner_logs(
        automation_run_id=automation_run_id,
        stdout=proc.stdout,
        stderr=proc.stderr,
        root=automation_root,
    )
    runner_stdout_path = _rel_to_workdir(runner_logs_abs.get("runner_stdout_path"), workdir=workdir)
    runner_stderr_path = _rel_to_workdir(runner_logs_abs.get("runner_stderr_path"), workdir=workdir)

    wrapper_exit_code = runner_exit_code
    contract: dict[str, Any] | None = None
    manifest_payload: dict[str, Any] | None = None
    record: dict[str, Any]

    try:
        contract = parse_workflow_stdout_contract(proc.stdout)
        resolved_manifest_path = _resolve_manifest_path(str(contract["workflow_manifest"]), workdir=workdir)
        manifest_payload = json.loads(resolved_manifest_path.read_text(encoding="utf-8"))
        validate_workflow_contract(
            contract,
            manifest_payload,
            runner_process_exit_code=runner_exit_code,
            manifest_path=resolved_manifest_path,
        )

        finished_at = _iso_utc_now()
        record = build_automation_record(
            automation_run_id=automation_run_id,
            automation_started_at=started_at,
            automation_finished_at=finished_at,
            runner_command=runner_command,
            runner_process_exit_code=runner_exit_code,
            wrapper_exit_code=wrapper_exit_code,
            contract=contract,
            manifest_payload=manifest_payload,
            runner_stdout_path=runner_stdout_path,
            runner_stderr_path=runner_stderr_path,
        )
    except WorkflowContractError as e:
        wrapper_exit_code = 1
        finished_at = _iso_utc_now()
        record = build_automation_record(
            automation_run_id=automation_run_id,
            automation_started_at=started_at,
            automation_finished_at=finished_at,
            runner_command=runner_command,
            runner_process_exit_code=runner_exit_code,
            wrapper_exit_code=wrapper_exit_code,
            contract=contract or {},
            manifest_payload=manifest_payload or {},
            runner_stdout_path=runner_stdout_path,
            runner_stderr_path=runner_stderr_path,
            attention_type="automation_contract_error",
            suggested_next_action=str(e),
        )
        record["failed_step"] = "automation_contract_error"
    except Exception as e:  # pragma: no cover
        wrapper_exit_code = 1
        finished_at = _iso_utc_now()
        record = build_automation_record(
            automation_run_id=automation_run_id,
            automation_started_at=started_at,
            automation_finished_at=finished_at,
            runner_command=runner_command,
            runner_process_exit_code=runner_exit_code,
            wrapper_exit_code=wrapper_exit_code,
            contract=contract or {},
            manifest_payload=manifest_payload or {},
            runner_stdout_path=runner_stdout_path,
            runner_stderr_path=runner_stderr_path,
            attention_type="automation_contract_error",
            suggested_next_action=f"wrapper error: {type(e).__name__}",
        )
        record["failed_step"] = "automation_contract_error"

    try:
        write_automation_outputs(record, root=automation_root)
    except Exception:
        # Wrapper self-failure should return 1 (but keep runner_process_exit_code in record).
        return 1

    return int(wrapper_exit_code)


if __name__ == "__main__":
    raise SystemExit(main())


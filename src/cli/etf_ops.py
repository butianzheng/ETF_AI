"""Unified ETF Ops CLI entry."""
from __future__ import annotations

import argparse

from src.cli.commands import (
    run_automation_command,
    run_daily_command,
    run_research_governance_command,
    run_workflow_command,
)
from src.cli.status import run_status_latest


def _ensure_preflight_only(argv: list[str]) -> list[str]:
    if "--preflight-only" in argv:
        return list(argv)
    return [*argv, "--preflight-only"]


def _strip_leading_double_dash(argv: list[str]) -> list[str]:
    if argv and argv[0] == "--":
        return argv[1:]
    return list(argv)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ETF Ops unified command entry")
    subparsers = parser.add_subparsers(dest="command", required=True)

    workflow = subparsers.add_parser("workflow", help="End-to-end workflow commands")
    workflow_subparsers = workflow.add_subparsers(dest="workflow_command", required=True)
    workflow_subparsers.add_parser("run", help="Run workflow")
    workflow_subparsers.add_parser("preflight", help="Run workflow preflight only")

    automation = subparsers.add_parser("automation", help="Workflow automation commands")
    automation_subparsers = automation.add_subparsers(dest="automation_command", required=True)
    automation_run = automation_subparsers.add_parser("run", help="Run automation wrapper")
    automation_run.add_argument("runner_args", nargs=argparse.REMAINDER, help="Args for automation wrapper")

    daily = subparsers.add_parser("daily", help="Daily operation commands")
    daily_subparsers = daily.add_subparsers(dest="daily_command", required=True)
    daily_subparsers.add_parser("run", help="Run daily pipeline")

    governance = subparsers.add_parser("research-governance", help="Research governance commands")
    governance_subparsers = governance.add_subparsers(dest="governance_command", required=True)
    governance_subparsers.add_parser("run", help="Run research governance pipeline")

    status = subparsers.add_parser("status", help="Status commands")
    status_subparsers = status.add_subparsers(dest="status_command", required=True)
    status_latest = status_subparsers.add_parser("latest", help="Show latest workflow status")
    status_latest.add_argument("--workdir", help="Artifacts root directory")
    status_latest.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Output JSON only",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, passthrough = parser.parse_known_args(argv)

    if args.command == "workflow":
        workflow_args = list(passthrough or [])
        if args.workflow_command == "preflight":
            workflow_args = _strip_leading_double_dash(workflow_args)
            workflow_args = _ensure_preflight_only(workflow_args)
        return run_workflow_command(workflow_args)

    if args.command == "automation" and args.automation_command == "run":
        passthrough_args = list(passthrough or [])
        runner_args = list(args.runner_args or [])
        return run_automation_command([*passthrough_args, *runner_args])

    if args.command == "daily" and args.daily_command == "run":
        return run_daily_command(list(passthrough or []))

    if args.command == "research-governance" and args.governance_command == "run":
        return run_research_governance_command(list(passthrough or []))

    if args.command == "status" and args.status_command == "latest":
        if passthrough:
            parser.error(f"unrecognized arguments: {' '.join(passthrough)}")
        return run_status_latest(args.workdir, output_json=args.json_output)

    parser.error("Unsupported command")

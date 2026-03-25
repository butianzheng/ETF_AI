"""Workflow 辅助模块。"""

from src.workflow.automation import (
    build_automation_record,
    generate_automation_run_id,
    parse_workflow_stdout_contract,
    render_attention_markdown,
    should_update_attention,
    validate_workflow_contract,
    write_automation_outputs,
    write_runner_logs,
)
from src.workflow.preflight import run_workflow_preflight

__all__ = [
    "build_automation_record",
    "generate_automation_run_id",
    "parse_workflow_stdout_contract",
    "render_attention_markdown",
    "run_workflow_preflight",
    "should_update_attention",
    "validate_workflow_contract",
    "write_automation_outputs",
    "write_runner_logs",
]

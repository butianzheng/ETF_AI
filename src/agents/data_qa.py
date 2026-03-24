"""Data QA Agent。"""
from typing import Any, Dict, List

from pydantic import ConfigDict, Field

from src.agents.base import AgentInput, AgentOutput, BaseAgent


class DataQAInput(AgentInput):
    """Data QA Agent 输入模型。"""

    symbols: List[str]
    validation_summary: Dict[str, Any]
    missing_dates: List[str] = Field(default_factory=list)


class DataQAOutput(AgentOutput):
    """Data QA Agent 输出模型。"""

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "status": "warning",
            "allow_strategy_run": False,
            "issues": [
                {
                    "code": "510300",
                    "issue_type": "price_jump",
                    "date": "2026-03-10",
                    "description": "价格跳变15.2%",
                    "severity": "medium",
                }
            ],
            "summary": "数据质量警告，存在异常",
        }
    })

    allow_strategy_run: bool
    issues: List[Dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


class DataQAAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="data_qa")

    def prepare_prompt(self, input_data: DataQAInput) -> str:
        return (
            "你是 ETF 数据质量检查助手。"
            "请只根据结构化输入给出 JSON，不要扩展投资建议。\n"
            f"symbols={input_data.symbols}\n"
            f"validation_summary={input_data.validation_summary}\n"
            f"missing_dates={input_data.missing_dates}\n"
            "输出字段：status, allow_strategy_run, issues, summary。"
        )

    def parse_output(self, raw_output: str) -> DataQAOutput:
        data = self._extract_json(raw_output)
        return DataQAOutput(
            status=data.get("status", "error"),
            allow_strategy_run=data.get("allow_strategy_run", False),
            issues=data.get("issues", []),
            summary=data.get("summary", ""),
            message=data.get("message", ""),
            data=data.get("data", {}),
        )

    def fallback_output(self, input_data: DataQAInput) -> DataQAOutput:
        summary = input_data.validation_summary
        issues = summary.get("issues", [])
        if input_data.missing_dates:
            issues = issues + [
                {
                    "code": "calendar",
                    "issue_type": "missing_dates",
                    "date": d,
                    "description": f"交易日 {d} 缺失",
                    "severity": "medium",
                }
                for d in input_data.missing_dates
            ]

        status = summary.get("status", "warning" if issues else "ok")
        allow_strategy_run = summary.get("allow_strategy_run", status != "error")
        text = summary.get("summary", "数据质量良好" if allow_strategy_run else "数据质量不满足策略运行要求")
        return DataQAOutput(
            status=status,
            allow_strategy_run=allow_strategy_run,
            issues=issues,
            summary=text,
            data={"symbols": input_data.symbols, "issue_count": len(issues)},
        )

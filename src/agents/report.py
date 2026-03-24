"""Report Agent。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import Field

from src.agents.base import AgentInput, AgentOutput, BaseAgent


class ReportInput(AgentInput):
    trade_date: str
    current_position: Optional[str] = None
    target_position: Optional[str] = None
    rebalance: bool = False
    scores: List[Dict[str, Any]] = Field(default_factory=list)
    risk_status: str = "green"
    data_status: str = "ok"
    report_type: str = "daily"
    execution_status: str = "pending"
    execution_reason: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)


class ReportOutput(AgentOutput):
    should_rebalance: bool
    title: str
    summary: str
    reasons: List[str] = Field(default_factory=list)
    markdown_report: str


class ReportAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="report")

    def prepare_prompt(self, input_data: ReportInput) -> str:
        return (
            "你是 ETF 调仓报告助手。请输出 JSON。"
            f"\ntrade_date={input_data.trade_date}"
            f"\ncurrent_position={input_data.current_position}"
            f"\ntarget_position={input_data.target_position}"
            f"\nrebalance={input_data.rebalance}"
            f"\nscores={input_data.scores}"
            f"\nrisk_status={input_data.risk_status}"
            f"\ndata_status={input_data.data_status}"
            f"\nexecution_status={input_data.execution_status}"
            f"\nexecution_reason={input_data.execution_reason}"
            f"\ndata={input_data.data}"
            "\n字段：status, should_rebalance, title, summary, reasons, markdown_report, data。"
            "\n要求：必须在 data.active_strategy_id 与 data.reason_codes 返回策略信息。"
            "\n要求：markdown_report 必须显式包含“生效策略”和“提案原因”两行。"
        )

    def parse_output(self, raw_output: str) -> ReportOutput:
        data = self._extract_json(raw_output)
        payload = data.get("data", {})
        if not isinstance(payload, dict):
            payload = {}
        return ReportOutput(
            status=data.get("status", "ok"),
            should_rebalance=data.get("should_rebalance", False),
            title=data.get("title", "策略报告"),
            summary=data.get("summary", ""),
            reasons=data.get("reasons", []),
            markdown_report=data.get("markdown_report", ""),
            message=data.get("message", ""),
            data=payload,
        )

    def _ensure_strategy_metadata(self, output: ReportOutput, input_data: ReportInput) -> ReportOutput:
        payload = dict(output.data or {})
        input_payload = dict(input_data.data or {})
        has_input_active_strategy_id = "active_strategy_id" in input_payload
        has_input_reason_codes = "reason_codes" in input_payload

        if has_input_active_strategy_id:
            payload["active_strategy_id"] = input_payload.get("active_strategy_id")
        if has_input_reason_codes:
            raw_codes = input_payload.get("reason_codes")
            payload["reason_codes"] = list(raw_codes) if isinstance(raw_codes, list) else []

        output.data = payload

        active_strategy_id = payload.get("active_strategy_id")
        reason_codes = payload.get("reason_codes")
        normalized_reason_codes = list(reason_codes) if isinstance(reason_codes, list) else []

        reasons = list(output.reasons or [])
        reasons = [item for item in reasons if "生效策略：" not in item and "提案原因：" not in item]
        if active_strategy_id:
            reasons.append(f"生效策略：{active_strategy_id}")
        if normalized_reason_codes:
            reasons.append(f"提案原因：{', '.join(str(code) for code in normalized_reason_codes)}")
        output.reasons = reasons

        markdown_lines = (output.markdown_report or "").splitlines()
        markdown_lines = [line for line in markdown_lines if "生效策略：" not in line and "提案原因：" not in line]
        if active_strategy_id:
            markdown_lines.append(f"- 生效策略：{active_strategy_id}")
        if normalized_reason_codes:
            markdown_lines.append(f"- 提案原因：{', '.join(str(code) for code in normalized_reason_codes)}")
        output.markdown_report = "\n".join(markdown_lines).strip()
        return output

    def run(self, input_data: ReportInput) -> ReportOutput:
        output = super().run(input_data)
        return self._ensure_strategy_metadata(output, input_data)

    def fallback_output(self, input_data: ReportInput) -> ReportOutput:
        top_score = input_data.scores[0] if input_data.scores else None
        reasons: List[str] = []
        if input_data.rebalance:
            reasons.append("当前持仓与目标持仓不同，满足调仓条件")
        else:
            reasons.append("当前持仓与目标持仓一致，本期无需调仓")
        if top_score:
            reasons.append(
                f"{top_score.get('name', top_score.get('code', '目标ETF'))} 综合得分最高：{top_score.get('score', 0):.4f}"
            )
            if top_score.get("above_ma") is True:
                reasons.append("目标 ETF 当前价格高于均线过滤，趋势条件通过")
            elif top_score.get("above_ma") is False:
                reasons.append("目标 ETF 趋势过滤未通过，需要谨慎复核")

        summary = (
            f"{input_data.trade_date} 建议{'调仓' if input_data.rebalance else '保持持仓'}，"
            f"风险状态 {input_data.risk_status}，数据状态 {input_data.data_status}，执行状态 {input_data.execution_status}。"
        )
        if input_data.execution_reason:
            reasons.append(f"执行说明：{input_data.execution_reason}")
        active_strategy_id = input_data.data.get("active_strategy_id") if input_data.data else None
        reason_codes = input_data.data.get("reason_codes") if input_data.data else None
        if active_strategy_id:
            reasons.append(f"生效策略：{active_strategy_id}")
        if reason_codes:
            reasons.append(f"提案原因：{', '.join(str(code) for code in reason_codes)}")
        markdown_report = "\n".join(
            [
                f"# {input_data.report_type.capitalize()} Report",
                f"- 日期：{input_data.trade_date}",
                f"- 当前持仓：{input_data.current_position or '空仓'}",
                f"- 目标持仓：{input_data.target_position or '空仓'}",
                f"- 是否调仓：{'是' if input_data.rebalance else '否'}",
                f"- 风险状态：{input_data.risk_status}",
                f"- 数据状态：{input_data.data_status}",
                f"- 执行状态：{input_data.execution_status}",
                f"- 生效策略：{active_strategy_id or 'N/A'}",
                f"- 提案原因：{', '.join(reason_codes) if reason_codes else 'N/A'}",
                "",
                "## 原因",
                *[f"{idx}. {reason}" for idx, reason in enumerate(reasons, start=1)],
            ]
        )
        return ReportOutput(
            status="ok",
            should_rebalance=input_data.rebalance,
            title=f"{input_data.trade_date} 策略报告",
            summary=summary,
            reasons=reasons,
            markdown_report=markdown_report,
            data={"report_type": input_data.report_type, **(input_data.data or {})},
        )

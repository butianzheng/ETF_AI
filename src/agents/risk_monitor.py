"""Risk Monitor Agent。"""
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import Field

from src.agents.base import AgentInput, AgentOutput, BaseAgent


class RiskMonitorInput(AgentInput):
    nav_series: List[Dict[str, Any]] = Field(default_factory=list)
    benchmark_series: List[Dict[str, Any]] = Field(default_factory=list)
    recent_signals: List[Dict[str, Any]] = Field(default_factory=list)
    account_status: Dict[str, Any] = Field(default_factory=dict)
    current_drawdown: float = 0.0


class RiskMonitorOutput(AgentOutput):
    risk_level: str
    require_manual_review: bool
    reasons: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    summary: str


class RiskMonitorAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="risk_monitor")

    def prepare_prompt(self, input_data: RiskMonitorInput) -> str:
        return (
            "你是策略风险监控助手。请只输出 JSON。"
            f"\nnav_series={input_data.nav_series}"
            f"\nbenchmark_series={input_data.benchmark_series}"
            f"\nrecent_signals={input_data.recent_signals}"
            f"\naccount_status={input_data.account_status}"
            f"\ncurrent_drawdown={input_data.current_drawdown}"
            "\n字段：status, risk_level, require_manual_review, reasons, suggestions, summary。"
        )

    def parse_output(self, raw_output: str) -> RiskMonitorOutput:
        data = self._extract_json(raw_output)
        return RiskMonitorOutput(
            status=data.get("status", "ok"),
            risk_level=data.get("risk_level", "green"),
            require_manual_review=data.get("require_manual_review", False),
            reasons=data.get("reasons", []),
            suggestions=data.get("suggestions", []),
            summary=data.get("summary", ""),
            message=data.get("message", ""),
            data=data.get("data", {}),
        )

    def fallback_output(self, input_data: RiskMonitorInput) -> RiskMonitorOutput:
        drawdown = float(input_data.current_drawdown)
        reasons: List[str] = []
        suggestions: List[str] = []
        risk_level = "green"

        if drawdown <= -0.15:
            risk_level = "red"
            reasons.append(f"当前回撤 {drawdown:.2%} 已超过 15%")
            suggestions.append("暂停自动执行，立即人工复核")
        elif drawdown <= -0.10:
            risk_level = "orange"
            reasons.append(f"当前回撤 {drawdown:.2%} 已超过 10%")
            suggestions.append("检查近期信号与市场风格是否偏离")
        elif drawdown <= -0.05:
            risk_level = "yellow"
            reasons.append(f"当前回撤 {drawdown:.2%} 已超过 5%")
            suggestions.append("继续观察并准备人工复核")
        else:
            reasons.append("当前回撤处于可接受区间")

        cash_ratio = input_data.account_status.get("cash_ratio")
        if cash_ratio is not None and float(cash_ratio) < 0.02:
            reasons.append("账户现金比例偏低")
            suggestions.append("确认后续调仓是否需要预留现金")
            if risk_level == "green":
                risk_level = "yellow"

        benchmark_return = 0.0
        strategy_return = 0.0
        if len(input_data.nav_series) >= 2:
            strategy_return = input_data.nav_series[-1]["nav"] / input_data.nav_series[0]["nav"] - 1
        if len(input_data.benchmark_series) >= 2:
            benchmark_return = (
                input_data.benchmark_series[-1]["nav"] / input_data.benchmark_series[0]["nav"] - 1
            )
        if strategy_return - benchmark_return < -0.08:
            reasons.append("策略相对基准显著落后")
            suggestions.append("检查参数是否失效或样本外表现恶化")
            if risk_level == "green":
                risk_level = "yellow"

        summary = f"当前风险等级 {risk_level}，需要{'人工复核' if risk_level in {'orange', 'red'} else '继续跟踪'}。"
        return RiskMonitorOutput(
            status="ok",
            risk_level=risk_level,
            require_manual_review=risk_level in {"orange", "red"},
            reasons=reasons,
            suggestions=suggestions,
            summary=summary,
            data={"strategy_return": strategy_return, "benchmark_return": benchmark_return},
        )

"""Research Agent。"""
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import Field

from src.agents.base import AgentInput, AgentOutput, BaseAgent


class ResearchInput(AgentInput):
    production_strategy_version: str
    research_window: str
    candidates: List[Dict[str, Any]] = Field(default_factory=list)


class ResearchOutput(AgentOutput):
    ranked_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    recommendation: str
    overfit_risk: str
    summary: str


class ResearchAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="research")

    def prepare_prompt(self, input_data: ResearchInput) -> str:
        return (
            "你是 ETF 参数研究助手。请输出 JSON，不能直接建议上线。"
            f"\nproduction_strategy_version={input_data.production_strategy_version}"
            f"\nresearch_window={input_data.research_window}"
            f"\ncandidates={input_data.candidates}"
            "\n字段：status, ranked_candidates, recommendation, overfit_risk, summary。"
        )

    def parse_output(self, raw_output: str) -> ResearchOutput:
        data = self._extract_json(raw_output)
        return ResearchOutput(
            status=data.get("status", "ok"),
            ranked_candidates=data.get("ranked_candidates", []),
            recommendation=data.get("recommendation", ""),
            overfit_risk=data.get("overfit_risk", "unknown"),
            summary=data.get("summary", ""),
            message=data.get("message", ""),
            data=data.get("data", {}),
        )

    def _candidate_score(self, candidate: Dict[str, Any]) -> float:
        annual_return = float(candidate.get("annual_return", 0.0))
        max_drawdown = abs(float(candidate.get("max_drawdown", 0.0)))
        sharpe = float(candidate.get("sharpe", 0.0))
        return annual_return * 100 - max_drawdown * 60 + sharpe * 10

    def fallback_output(self, input_data: ResearchInput) -> ResearchOutput:
        ranked = []
        for candidate in input_data.candidates:
            ranked.append({**candidate, "composite_score": round(self._candidate_score(candidate), 4)})
        ranked.sort(key=lambda item: item["composite_score"], reverse=True)

        if not ranked:
            return ResearchOutput(
                status="warning",
                ranked_candidates=[],
                recommendation="缺少候选参数结果，无法形成研究建议",
                overfit_risk="unknown",
                summary="研究输入为空",
            )

        best = ranked[0]
        overfit_risk = "low"
        if float(best.get("annual_return", 0.0)) > 0.35 and abs(float(best.get("max_drawdown", 0.0))) > 0.2:
            overfit_risk = "high"
        elif float(best.get("sharpe", 0.0)) < 1.0:
            overfit_risk = "medium"

        recommendation = (
            f"优先复核候选方案 {best.get('name', best.get('param_desc', 'candidate_1'))}，"
            f"再与生产版 {input_data.production_strategy_version} 做样本外比较。"
        )
        summary = (
            f"研究窗口 {input_data.research_window} 内共比较 {len(ranked)} 个候选方案，"
            f"当前综合排名第一的是 {best.get('name', best.get('param_desc', 'candidate_1'))}。"
        )
        return ResearchOutput(
            status="ok",
            ranked_candidates=ranked,
            recommendation=recommendation,
            overfit_risk=overfit_risk,
            summary=summary,
            data={"production_strategy_version": input_data.production_strategy_version},
        )

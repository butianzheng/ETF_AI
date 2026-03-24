"""研究线主流程。"""
from __future__ import annotations

from copy import deepcopy
import csv
from datetime import date
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.agents import ResearchAgent, ResearchInput
from src.backtest.engine import SimpleBacktestEngine
from src.backtest.evaluator import evaluate_backtest
from src.core.config import StrategyConfig, config_loader
from src.core.logger import get_logger, setup_logger
from src.report_portal import build_report_portal
from src.strategy.registry import build_candidate_strategy, split_candidate_overrides

logger = get_logger(__name__)


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


def _build_markdown_report(
    start_date: date,
    end_date: date,
    candidates: List[Dict[str, Any]],
    research_output: Dict[str, Any],
) -> str:
    lines = [
        "# Research Report",
        f"- 研究区间：{start_date} -> {end_date}",
        f"- 候选数量：{len(candidates)}",
        f"- 总结：{research_output['summary']}",
        f"- 推荐：{research_output['recommendation']}",
        f"- 过拟合风险：{research_output['overfit_risk']}",
        "",
        "## 候选排名",
    ]
    for idx, candidate in enumerate(research_output["ranked_candidates"], start=1):
        lines.extend(
            [
                f"### {idx}. {candidate.get('candidate_name', candidate.get('name', candidate.get('param_desc', f'candidate_{idx}')))}",
                f"- 策略ID：{candidate.get('strategy_id', 'N/A')}",
                f"- 说明：{candidate.get('description', '未提供')}",
                f"- 年化收益：{candidate.get('annual_return', 0):.2%}",
                f"- 最大回撤：{candidate.get('max_drawdown', 0):.2%}",
                f"- Sharpe：{candidate.get('sharpe', 0):.4f}",
                f"- Composite Score：{candidate.get('composite_score', 0):.4f}",
                f"- 参数：{candidate.get('overrides', candidate.get('param_desc', {}))}",
                f"- 目标分布：{candidate.get('target_etf_counts', {})}",
                "",
            ]
        )
    return "\n".join(lines)


def _save_research_outputs(
    end_date: date,
    comparison_rows: List[Dict[str, Any]],
    research_output: Dict[str, Any],
    markdown_report: str,
) -> Dict[str, str]:
    report_dir = Path("reports/research")
    report_dir.mkdir(parents=True, exist_ok=True)
    base_name = end_date.isoformat()
    markdown_path = report_dir / f"{base_name}.md"
    json_path = report_dir / f"{base_name}.json"
    csv_path = report_dir / f"{base_name}.csv"

    markdown_path.write_text(markdown_report, encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "comparison_rows": _to_jsonable(comparison_rows),
                "research_output": _to_jsonable(research_output),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    header = ["name", "annual_return", "max_drawdown", "sharpe", "turnover", "trade_count", "win_rate", "profit_drawdown_ratio", "param_desc"]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in comparison_rows:
            writer.writerow(
                [
                    row.get("candidate_name", row.get("name", "")),
                    row.get("annual_return", ""),
                    row.get("max_drawdown", ""),
                    row.get("sharpe", ""),
                    row.get("turnover", ""),
                    row.get("trade_count", ""),
                    row.get("win_rate", ""),
                    row.get("profit_drawdown_ratio", ""),
                    json.dumps(row.get("overrides", row.get("param_desc", "")), ensure_ascii=False),
                ]
            )
    return {"markdown": str(markdown_path), "json": str(json_path), "csv": str(csv_path)}


def _apply_overrides(base_cfg: StrategyConfig, overrides: Dict[str, Any]) -> StrategyConfig:
    cfg_dict = deepcopy(base_cfg.model_dump())

    def _update(target: Dict[str, Any], changes: Dict[str, Any]) -> None:
        for key, value in changes.items():
            if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                _update(target[key], value)
            else:
                target[key] = value

    _update(cfg_dict, overrides)
    return StrategyConfig(**cfg_dict)


def _build_param_desc(overrides: Dict[str, Any]) -> str:
    if not overrides:
        return "default"
    return ", ".join([f"{k}={v}" for k, v in overrides.items()])


def _count_target_etfs(results: list[Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for result in results:
        target = result.target_position or "CASH"
        counts[target] = counts.get(target, 0) + 1
    return counts


def run_research_pipeline(
    start_date: date,
    end_date: date,
    candidate_specs: Optional[List[Dict[str, Any]]] = None,
    initial_capital: float = 100000.0,
    fee_rate: float = 0.001,
    log_level: str = "INFO",
) -> Dict[str, Any]:
    """执行研究线闭环：按候选 registry 回测 -> ResearchAgent -> 报告落盘。"""
    setup_logger(log_level=log_level)
    if candidate_specs is None:
        candidate_specs = [
            candidate.model_dump()
            for candidate in config_loader.load_research_config().candidates
        ]
    candidate_specs = deepcopy(candidate_specs)
    if not candidate_specs:
        raise ValueError("研究候选列表不能为空")
    base_config = config_loader.load_strategy_config()
    comparison_rows: List[Dict[str, Any]] = []
    for idx, spec in enumerate(candidate_specs, start=1):
        strategy_id = spec["strategy_id"]
        raw_overrides = spec.get("overrides") or {}
        config_overrides, strategy_params = split_candidate_overrides(raw_overrides)
        run_config = _apply_overrides(base_config, config_overrides)
        candidate_strategy = build_candidate_strategy(
            strategy_id=strategy_id,
            strategy_config=run_config,
            strategy_params=strategy_params,
        )
        engine = SimpleBacktestEngine(
            config=run_config,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            fee_rate=fee_rate,
            candidate_strategy=candidate_strategy,
        )
        nav_series, strategy_results = engine.run(persist_run=False)
        metrics = evaluate_backtest(nav_series, trades=len(strategy_results))
        comparison_rows.append(
            {
                "run_id": idx,
                "candidate_name": spec["name"],
                "name": spec["name"],
                "strategy_id": strategy_id,
                "description": spec.get("description"),
                "overrides": raw_overrides,
                "param_desc": _build_param_desc(raw_overrides),
                "target_etf_counts": _count_target_etfs(strategy_results),
                **_to_jsonable(metrics),
            }
        )
    comparison_rows.sort(key=lambda item: item.get("annual_return", 0.0), reverse=True)

    strategy_config = base_config
    research_output = ResearchAgent().run(
        ResearchInput(
            production_strategy_version=f"{strategy_config.name}_v{strategy_config.version}",
            research_window=f"{start_date} -> {end_date}",
            candidates=comparison_rows,
        )
    )

    markdown_report = _build_markdown_report(
        start_date=start_date,
        end_date=end_date,
        candidates=comparison_rows,
        research_output=research_output.model_dump(),
    )
    output_paths = _save_research_outputs(
        end_date=end_date,
        comparison_rows=comparison_rows,
        research_output=research_output.model_dump(),
        markdown_report=markdown_report,
    )
    portal_paths = build_report_portal()["output_paths"]
    logger.info(f"Research report written to {output_paths['markdown']}")
    return {
        "comparison_rows": comparison_rows,
        "research_output": research_output,
        "report_paths": output_paths,
        "portal_paths": portal_paths,
    }

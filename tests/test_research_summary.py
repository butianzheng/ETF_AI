import json
from pathlib import Path

from src.research_summary import aggregate_research_reports


def _write_report(
    path: Path,
    top_name: str,
    top_strategy_id: str,
    annual_return: float,
    sharpe: float,
    summary: str,
) -> None:
    path.write_text(
        json.dumps(
            {
                "comparison_rows": [
                    {
                        "name": top_name,
                        "candidate_name": top_name,
                        "strategy_id": top_strategy_id,
                        "description": f"{top_name} desc",
                        "overrides": {"rebalance_frequency": "monthly"},
                        "annual_return": annual_return,
                        "sharpe": sharpe,
                        "max_drawdown": -0.12,
                        "composite_score": sharpe,
                    },
                    {
                        "name": "baseline",
                        "candidate_name": "baseline",
                        "strategy_id": "trend_momentum",
                        "description": "baseline desc",
                        "overrides": {},
                        "annual_return": annual_return - 0.03,
                        "sharpe": sharpe - 0.2,
                        "max_drawdown": -0.10,
                        "composite_score": sharpe - 0.2,
                    },
                ],
                "research_output": {
                    "ranked_candidates": [
                        {
                            "name": top_name,
                            "candidate_name": top_name,
                            "strategy_id": top_strategy_id,
                            "description": f"{top_name} desc",
                            "overrides": {"rebalance_frequency": "monthly"},
                            "annual_return": annual_return,
                            "sharpe": sharpe,
                            "max_drawdown": -0.12,
                            "composite_score": sharpe,
                        },
                        {
                            "name": "baseline",
                            "candidate_name": "baseline",
                            "strategy_id": "trend_momentum",
                            "description": "baseline desc",
                            "overrides": {},
                            "annual_return": annual_return - 0.03,
                            "sharpe": sharpe - 0.2,
                            "max_drawdown": -0.10,
                            "composite_score": sharpe - 0.2,
                        },
                    ],
                    "recommendation": f"推荐 {top_name}",
                    "overfit_risk": "low",
                    "summary": summary,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_aggregate_research_reports_generates_summary(tmp_path):
    report_dir = tmp_path / "reports"
    output_dir = tmp_path / "summary"
    report_dir.mkdir()
    _write_report(report_dir / "2026-03-10.json", "ma90_filter", "risk_adjusted_momentum", 0.21, 1.1, "第一次研究")
    _write_report(report_dir / "2026-03-11.json", "ma90_filter", "risk_adjusted_momentum", 0.24, 1.3, "第二次研究")
    _write_report(report_dir / "2026-03-12.json", "biweekly_rebalance", "trend_momentum", 0.28, 1.5, "第三次研究")

    result = aggregate_research_reports(report_dir=report_dir, output_dir=output_dir)

    assert len(result["report_summaries"]) == 3
    assert result["candidate_leaderboard"][0]["name"] == "ma90_filter"
    assert result["candidate_leaderboard"][0]["strategy_id"] == "risk_adjusted_momentum"
    assert result["candidate_leaderboard"][0]["top1_count"] == 2
    assert Path(result["output_paths"]["markdown"]).exists()
    assert Path(result["output_paths"]["html"]).exists()
    assert Path(result["output_paths"]["json"]).exists()
    assert Path(result["output_paths"]["reports_csv"]).exists()
    assert Path(result["output_paths"]["candidates_csv"]).exists()
    assert len(result["candidate_observations"]) == 6
    html_content = Path(result["output_paths"]["html"]).read_text(encoding="utf-8")
    assert "研究历史总览" in html_content
    assert "ma90_filter" in html_content
    assert "risk_adjusted_momentum" in html_content
    assert 'id="candidate-filter"' in html_content
    assert 'data-table="reports"' in html_content
    assert 'data-table="candidates"' in html_content


def test_aggregate_research_reports_requires_input_files(tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    try:
        aggregate_research_reports(report_dir=empty_dir)
    except FileNotFoundError as exc:
        assert "未找到研究报告" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")

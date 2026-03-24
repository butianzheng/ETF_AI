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
    baseline_annual_return = annual_return - 0.03
    baseline_sharpe = sharpe - 0.2
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
                        "annual_return": baseline_annual_return,
                        "sharpe": baseline_sharpe,
                        "max_drawdown": -0.10,
                        "composite_score": baseline_sharpe,
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
                            "annual_return": baseline_annual_return,
                            "sharpe": baseline_sharpe,
                            "max_drawdown": -0.10,
                            "composite_score": baseline_sharpe,
                        },
                    ],
                    "recommendation": f"推荐 {top_name}",
                    "overfit_risk": "low",
                    "summary": summary,
                },
                "regime_config_snapshot": {
                    "enabled": True,
                    "min_pool_coverage": 3,
                    "min_volatility_20": 0.18,
                },
                "regime_daily_labels": [
                    {"trade_date": "2026-03-10", "regime_label": "risk_on", "regime_score": 0.6, "reason_codes": [], "metrics_snapshot": {"coverage": 4}},
                    {"trade_date": "2026-03-11", "regime_label": "neutral", "regime_score": 0.0, "reason_codes": [], "metrics_snapshot": {"coverage": 4}},
                    {"trade_date": "2026-03-12", "regime_label": "risk_off", "regime_score": -0.6, "reason_codes": [], "metrics_snapshot": {"coverage": 4}},
                ],
                "candidate_regime_metrics": {
                    top_name: {
                        "overall_metrics": {
                            "annual_return": annual_return,
                            "sharpe": sharpe,
                            "max_drawdown": -0.12,
                            "observation_count": 90,
                        },
                        "by_regime_metrics": {
                            "risk_on": {
                                "annual_return": annual_return + 0.04,
                                "sharpe": sharpe + 0.2,
                                "max_drawdown": -0.08,
                                "observation_count": 30,
                            },
                            "neutral": {
                                "annual_return": annual_return,
                                "sharpe": sharpe,
                                "max_drawdown": -0.12,
                                "observation_count": 30,
                            },
                            "risk_off": {
                                "annual_return": annual_return - 0.06,
                                "sharpe": sharpe - 0.15,
                                "max_drawdown": -0.05,
                                "observation_count": 30,
                            },
                        },
                    },
                    "baseline": {
                        "overall_metrics": {
                            "annual_return": baseline_annual_return,
                            "sharpe": baseline_sharpe,
                            "max_drawdown": -0.10,
                            "observation_count": 90,
                        },
                        "by_regime_metrics": {
                            "risk_on": {
                                "annual_return": baseline_annual_return - 0.01,
                                "sharpe": baseline_sharpe,
                                "max_drawdown": -0.09,
                                "observation_count": 30,
                            },
                            "neutral": {
                                "annual_return": baseline_annual_return,
                                "sharpe": baseline_sharpe,
                                "max_drawdown": -0.10,
                                "observation_count": 30,
                            },
                            "risk_off": {
                                "annual_return": baseline_annual_return - 0.01,
                                "sharpe": baseline_sharpe + 0.05,
                                "max_drawdown": -0.04,
                                "observation_count": 30,
                            },
                        },
                    },
                },
                "candidate_sample_split_metrics": {
                    top_name: {
                        "in_sample_metrics": {
                            "annual_return": annual_return + 0.02,
                            "sharpe": sharpe + 0.1,
                            "max_drawdown": -0.10,
                            "observation_count": 63,
                        },
                        "out_of_sample_metrics": {
                            "annual_return": annual_return - 0.05,
                            "sharpe": sharpe - 0.2,
                            "max_drawdown": -0.14,
                            "observation_count": 27,
                        },
                        "by_regime_and_sample_metrics": {},
                    },
                    "baseline": {
                        "in_sample_metrics": {
                            "annual_return": baseline_annual_return,
                            "sharpe": baseline_sharpe,
                            "max_drawdown": -0.10,
                            "observation_count": 63,
                        },
                        "out_of_sample_metrics": {
                            "annual_return": baseline_annual_return - 0.01,
                            "sharpe": baseline_sharpe - 0.05,
                            "max_drawdown": -0.12,
                            "observation_count": 27,
                        },
                        "by_regime_and_sample_metrics": {},
                    },
                },
                "candidate_regime_transition_metrics": {
                    top_name: [
                        {
                            "from_regime": "neutral",
                            "to_regime": "risk_off",
                            "transition": "neutral->risk_off",
                            "event_count": 1,
                            "avg_forward_return_5": -0.03,
                            "avg_forward_drawdown_5": -0.04,
                        }
                    ],
                    "baseline": [
                        {
                            "from_regime": "neutral",
                            "to_regime": "risk_off",
                            "transition": "neutral->risk_off",
                            "event_count": 1,
                            "avg_forward_return_5": -0.01,
                            "avg_forward_drawdown_5": -0.02,
                        }
                    ],
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
    assert "regime_summary" in result
    assert result["candidate_regime_leaderboard"]
    assert result["candidate_regime_leaderboard"][0]["regime_label"] in {"risk_on", "risk_off", "neutral"}
    assert result["candidate_out_of_sample_leaderboard"]
    assert len(result["candidate_regime_observations"]) == 4
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
    assert "哪个候选在 risk_on 最强" in html_content
    assert "哪个候选在 risk_off 更稳" in html_content
    assert "某候选是否只在单一 regime 下有效" in html_content
    assert "某候选在样本外是否明显退化" in html_content


def test_aggregate_research_reports_requires_input_files(tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    try:
        aggregate_research_reports(report_dir=empty_dir)
    except FileNotFoundError as exc:
        assert "未找到研究报告" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")

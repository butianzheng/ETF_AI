from src.agents.data_qa import DataQAAgent, DataQAInput
from src.agents.report import ReportAgent, ReportInput
from src.agents.research import ResearchAgent, ResearchInput
from src.agents.risk_monitor import RiskMonitorAgent, RiskMonitorInput
from src.storage.database import init_db


def setup_module():
    init_db()


def test_data_qa_agent_fallback_runs():
    agent = DataQAAgent()
    output = agent.run(
        DataQAInput(
            symbols=["510300", "510500"],
            validation_summary={
                "status": "warning",
                "allow_strategy_run": False,
                "issues": [{"code": "510300", "issue_type": "missing_price", "description": "缺失收盘价", "severity": "high"}],
                "summary": "存在缺失值",
            },
        )
    )
    assert output.status == "warning"
    assert output.allow_strategy_run is False
    assert output.issues


def test_report_agent_fallback_runs():
    agent = ReportAgent()
    output = agent.run(
        ReportInput(
            trade_date="2026-03-11",
            current_position="510300",
            target_position="510500",
            rebalance=True,
            scores=[{"code": "510500", "name": "中证500ETF", "score": 0.12, "above_ma": True}],
        )
    )
    assert output.should_rebalance is True
    assert "中证500ETF" in output.markdown_report


def test_research_agent_fallback_runs():
    agent = ResearchAgent()
    output = agent.run(
        ResearchInput(
            production_strategy_version="etf_momentum_v1_v1.0.0",
            research_window="2025-01-01 ~ 2026-03-11",
            candidates=[
                {"name": "20/60 + MA120", "annual_return": 0.28, "max_drawdown": -0.08, "sharpe": 1.6},
                {"name": "20/90 + MA90", "annual_return": 0.31, "max_drawdown": -0.18, "sharpe": 1.2},
            ],
        )
    )
    assert output.ranked_candidates
    assert output.recommendation


def test_risk_monitor_agent_fallback_runs():
    agent = RiskMonitorAgent()
    output = agent.run(
        RiskMonitorInput(
            nav_series=[{"date": "2026-03-01", "nav": 1.0}, {"date": "2026-03-11", "nav": 0.93}],
            benchmark_series=[{"date": "2026-03-01", "nav": 1.0}, {"date": "2026-03-11", "nav": 0.98}],
            account_status={"cash_ratio": 0.01},
            current_drawdown=-0.12,
        )
    )
    assert output.risk_level in {"orange", "red"}
    assert output.require_manual_review is True

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

import src.main as main_module
from src.governance.models import GovernanceDecision
from src.main import run_daily_pipeline
from src.storage.repositories import GovernanceRepository


def _build_price_df(symbol: str, start_date: date, days: int, base: float, slope: float) -> pd.DataFrame:
    rows = []
    for idx in range(days):
        current_date = start_date + timedelta(days=idx)
        if current_date.weekday() >= 5:
            continue
        close = round(base + slope * idx, 4)
        rows.append(
            {
                "trade_date": current_date,
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": 100000 + idx,
                "amount": close * (100000 + idx),
                "source": "test",
            }
        )
    return pd.DataFrame(rows)


def test_daily_pipeline_end_to_end_generates_report_and_execution():
    start = date(2025, 3, 1)
    price_data = {
        "510300": _build_price_df("510300", start, 420, 4.0, 0.001),
        "510500": _build_price_df("510500", start, 420, 3.5, 0.006),
        "159915": _build_price_df("159915", start, 420, 3.0, 0.002),
        "515180": _build_price_df("515180", start, 420, 2.8, 0.0015),
    }

    result = run_daily_pipeline(
        as_of_date=date(2026, 3, 11),
        log_level="INFO",
        execute_trade=True,
        manual_approved=True,
        available_cash=100000.0,
        refresh_data=False,
        price_data_override=price_data,
    )

    assert result["status"] == "ok"
    assert result["data_qa_output"].allow_strategy_run is True
    assert result["order_check_result"].passed is True
    assert result["execution_result"] is not None
    assert result["execution_result"]["status"] == "filled"
    assert result["report_output"].markdown_report
    assert result["strategy_result"].scores
    assert result["strategy_result"].scores[0].current_price > 0
    assert result["report_output"].data.get("active_strategy_id") == "trend_momentum"
    assert result["report_output"].data.get("reason_codes")
    assert "- 生效策略：trend_momentum" in result["report_output"].markdown_report
    assert "- 提案原因：" in result["report_output"].markdown_report
    assert Path(result["report_paths"]["markdown"]).exists()
    assert Path(result["report_paths"]["json"]).exists()


def test_daily_pipeline_fails_fast_when_production_trend_filter_config_is_unsupported(monkeypatch):
    class DummyScoreFormula:
        return_20_weight = 0.5
        return_60_weight = 0.5

    class DummyTrendFilter:
        enabled = True
        ma_period = 60
        ma_type = "ema"

    class DummyConfig:
        score_formula = DummyScoreFormula()
        trend_filter = DummyTrendFilter()
        allow_cash = True
        hold_count = 1
        trade_policy = None
        version = "1.0.0"

    monkeypatch.setattr(main_module.config_loader, "load_strategy_config", lambda: DummyConfig())
    monkeypatch.setattr(main_module.config_loader, "load_production_strategy_id", lambda: "trend_momentum")
    monkeypatch.setattr(
        main_module.config_loader,
        "load_etf_pool",
        lambda: (_ for _ in ()).throw(AssertionError("should fail before loading etf_pool")),
    )

    with pytest.raises(ValueError, match="only supports"):
        run_daily_pipeline(as_of_date=date(2026, 3, 11), refresh_data=False)


def test_daily_pipeline_uses_latest_published_governance_strategy():
    repo = GovernanceRepository()
    try:
        draft = repo.save_draft(
            GovernanceDecision(
                decision_date=date(2026, 3, 24),
                current_strategy_id="trend_momentum",
                selected_strategy_id="risk_adjusted_momentum",
                previous_strategy_id="trend_momentum",
                fallback_strategy_id="trend_momentum",
                decision_type="switch",
            )
        )
        repo.approve(draft.id, approved_by="tester")
        repo.publish(draft.id)
    finally:
        repo.close()

    start = date(2025, 3, 1)
    price_data = {
        "510300": _build_price_df("510300", start, 420, 4.0, 0.001),
        "510500": _build_price_df("510500", start, 420, 3.5, 0.006),
        "159915": _build_price_df("159915", start, 420, 3.0, 0.002),
        "515180": _build_price_df("515180", start, 420, 2.8, 0.0015),
    }

    result = run_daily_pipeline(
        as_of_date=date(2026, 3, 11),
        log_level="INFO",
        execute_trade=False,
        manual_approved=True,
        available_cash=100000.0,
        refresh_data=False,
        price_data_override=price_data,
    )

    assert result["status"] == "ok"
    assert result["report_output"].data.get("active_strategy_id") == "risk_adjusted_momentum"


def test_health_check_rollback_recommendation_can_restore_fallback_strategy(tmp_path):
    from src.governance.health import check_governance_health

    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    report_path = daily_dir / f"{date.today().isoformat()}.json"
    report_path.write_text(
        __import__("json").dumps(
            {
                "status": "ok",
                "strategy_result": {
                    "current_position": None,
                    "target_position": "510500",
                    "rebalance": False,
                },
                "risk_output": {"risk_level": "red"},
                "execution_result": {"status": "filled", "action": "BUY"},
                "report_output": {
                    "summary": "health rollback",
                    "data": {"active_strategy_id": "trend_momentum"},
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    repo = GovernanceRepository()
    try:
        draft = repo.save_draft(
            GovernanceDecision(
                decision_date=date.today(),
                current_strategy_id="trend_momentum",
                selected_strategy_id="risk_adjusted_momentum",
                previous_strategy_id="trend_momentum",
                fallback_strategy_id="trend_momentum",
                decision_type="switch",
                review_status="ready",
            )
        )
        repo.approve(draft.id, approved_by="tester")
        repo.publish(draft.id)

        recommendation = check_governance_health(
            report_dir=daily_dir,
            repo=repo,
            policy=main_module.config_loader.load_strategy_config().governance,
            create_rollback_draft=True,
        ).rollback_recommendation
        assert recommendation is not None

        repo.approve(recommendation.id, approved_by="ops")
        repo.publish(recommendation.id)
    finally:
        repo.close()

    start = date(2025, 3, 1)
    price_data = {
        "510300": _build_price_df("510300", start, 420, 4.0, 0.001),
        "510500": _build_price_df("510500", start, 420, 3.5, 0.006),
        "159915": _build_price_df("159915", start, 420, 3.0, 0.002),
        "515180": _build_price_df("515180", start, 420, 2.8, 0.0015),
    }

    result = run_daily_pipeline(
        as_of_date=date(2026, 3, 11),
        log_level="INFO",
        execute_trade=False,
        manual_approved=True,
        available_cash=100000.0,
        refresh_data=False,
        price_data_override=price_data,
    )

    assert result["status"] == "ok"
    assert result["report_output"].data.get("active_strategy_id") == "trend_momentum"

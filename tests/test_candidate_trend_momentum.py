from __future__ import annotations

from datetime import date

import pytest

from src.agents.report import ReportAgent, ReportInput
from src.strategy.features import FeatureSnapshot, SymbolFeatures
from src.strategy.candidates.trend_momentum import TrendMomentumStrategy


def _build_snapshot() -> FeatureSnapshot:
    return FeatureSnapshot(
        trade_date=date(2026, 3, 11),
        by_symbol={
            "510300": SymbolFeatures(momentum_20=0.03, momentum_60=0.06, ma_distance_120=0.01),
            "510500": SymbolFeatures(momentum_20=0.08, momentum_60=0.10, ma_distance_120=0.02),
            "159915": SymbolFeatures(momentum_20=0.02, momentum_60=0.03, ma_distance_120=0.01),
        },
    )


def test_trend_momentum_strategy_selects_highest_trending_symbol():
    snapshot = _build_snapshot()
    strategy = TrendMomentumStrategy(return_20_weight=0.5, return_60_weight=0.5, allow_cash=True)

    proposal = strategy.generate(snapshot, current_position=None)

    assert proposal.target_etf == "510500"
    assert proposal.strategy_id == "trend_momentum"
    assert "TOP_SCORE_SELECTED" in proposal.reason_codes
    assert "REBALANCE_REQUIRED" in proposal.reason_codes


def test_trend_momentum_strategy_moves_to_cash_when_all_trend_filters_fail():
    snapshot = FeatureSnapshot(
        trade_date=date(2026, 3, 11),
        by_symbol={
            "510300": SymbolFeatures(momentum_20=0.10, momentum_60=0.12, ma_distance_120=-0.01),
            "510500": SymbolFeatures(momentum_20=0.11, momentum_60=0.09, ma_distance_120=-0.02),
        },
    )
    strategy = TrendMomentumStrategy(allow_cash=True)

    proposal = strategy.generate(snapshot, current_position="510300")

    assert proposal.target_etf is None
    assert "TREND_FILTER_FAILED" in proposal.reason_codes
    assert "MOVE_TO_CASH" in proposal.reason_codes


def test_trend_momentum_strategy_holds_current_when_target_unchanged():
    snapshot = _build_snapshot()
    strategy = TrendMomentumStrategy()

    proposal = strategy.generate(snapshot, current_position="510500")

    assert proposal.target_etf == "510500"
    assert "HOLD_CURRENT" in proposal.reason_codes


def test_trend_momentum_strategy_can_disable_trend_filter():
    snapshot = FeatureSnapshot(
        trade_date=date(2026, 3, 11),
        by_symbol={
            "510500": SymbolFeatures(momentum_20=0.09, momentum_60=0.11, ma_distance_120=-0.05),
            "510300": SymbolFeatures(momentum_20=0.04, momentum_60=0.03, ma_distance_120=0.01),
        },
    )
    strategy = TrendMomentumStrategy(trend_filter_enabled=False)

    proposal = strategy.generate(snapshot, current_position=None)

    assert proposal.target_etf == "510500"
    assert "TOP_SCORE_SELECTED" in proposal.reason_codes


def test_trend_momentum_strategy_raises_for_unsupported_trend_filter_config():
    with pytest.raises(ValueError, match="only supports"):
        TrendMomentumStrategy(
            trend_filter_enabled=True,
            trend_filter_ma_period=60,
            trend_filter_ma_type="sma",
        )


def test_report_agent_llm_success_path_keeps_active_strategy_metadata(monkeypatch):
    agent = ReportAgent()
    monkeypatch.setattr(agent.llm, "is_available", lambda: True)
    monkeypatch.setattr(
        agent.llm,
        "call",
        lambda **kwargs: (
            '{"status":"ok","should_rebalance":true,"title":"日报","summary":"ok","reasons":["已有原因"],'
            '"markdown_report":"# Daily Report\\n- 日期：2026-03-11","data":{}}'
        ),
    )
    monkeypatch.setattr(agent, "_log_execution", lambda input_data, output: None)

    output = agent.run(
        ReportInput(
            trade_date="2026-03-11",
            current_position="510300",
            target_position="510500",
            rebalance=True,
            data={"active_strategy_id": "trend_momentum", "reason_codes": ["TOP_SCORE_SELECTED"]},
        )
    )

    assert output.source == "llm"
    assert output.data["active_strategy_id"] == "trend_momentum"
    assert output.data["reason_codes"] == ["TOP_SCORE_SELECTED"]
    assert "生效策略：trend_momentum" in output.markdown_report
    assert "提案原因：TOP_SCORE_SELECTED" in output.markdown_report


def test_report_agent_llm_success_path_overrides_wrong_metadata_with_input_truth(monkeypatch):
    agent = ReportAgent()
    monkeypatch.setattr(agent.llm, "is_available", lambda: True)
    monkeypatch.setattr(
        agent.llm,
        "call",
        lambda **kwargs: (
            '{"status":"ok","should_rebalance":true,"title":"日报","summary":"ok",'
            '"reasons":["生效策略：wrong_strategy","提案原因：WRONG_REASON"],'
            '"markdown_report":"# Daily Report\\n- 生效策略：wrong_strategy\\n- 提案原因：WRONG_REASON",'
            '"data":{"active_strategy_id":"wrong_strategy","reason_codes":["WRONG_REASON"]}}'
        ),
    )
    monkeypatch.setattr(agent, "_log_execution", lambda input_data, output: None)

    output = agent.run(
        ReportInput(
            trade_date="2026-03-11",
            current_position="510300",
            target_position="510500",
            rebalance=True,
            data={"active_strategy_id": "trend_momentum", "reason_codes": ["TOP_SCORE_SELECTED"]},
        )
    )

    assert output.source == "llm"
    assert output.data["active_strategy_id"] == "trend_momentum"
    assert output.data["reason_codes"] == ["TOP_SCORE_SELECTED"]
    assert "wrong_strategy" not in output.markdown_report
    assert "WRONG_REASON" not in output.markdown_report
    assert "生效策略：trend_momentum" in output.markdown_report
    assert "提案原因：TOP_SCORE_SELECTED" in output.markdown_report

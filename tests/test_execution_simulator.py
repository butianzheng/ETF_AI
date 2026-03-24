from datetime import date

import pandas as pd

from src.execution.simulator import ExecutionSimulator, PortfolioSnapshot
from src.execution.trade_policy import TradePolicy
from src.storage.repositories import PriceRepository


def _seed_price(symbol: str, trade_date: date, close: float) -> None:
    repo = PriceRepository()
    try:
        repo.save_prices(
            symbol,
            pd.DataFrame(
                [
                    {
                        "trade_date": trade_date,
                        "open": close,
                        "high": close,
                        "low": close,
                        "close": close,
                        "volume": 100000,
                        "amount": close * 100000,
                        "source": "test",
                    }
                ]
            ),
        )
    finally:
        repo.close()


def test_simulator_rejects_buy_below_minimum_lot():
    _seed_price("510300", date(2026, 3, 13), 5.0)
    simulator = ExecutionSimulator(TradePolicy(rebalance_frequency="monthly"))
    try:
        result = simulator.rebalance(
            current_state=PortfolioSnapshot(cash=500.0, holding_symbol=None, holding_shares=0),
            target_symbol="510300",
            trade_date=date(2026, 3, 13),
        )
    finally:
        simulator.close()

    assert result.status == "rejected"
    assert result.action == "BUY"
    assert result.filled_shares == 0
    assert "不足一个最小交易单位" in "; ".join(result.reasons)
    assert result.final_state.holding_symbol is None
    assert result.final_state.cash == 500.0


def test_simulator_rejects_when_target_price_missing():
    simulator = ExecutionSimulator(TradePolicy(rebalance_frequency="monthly"))
    try:
        result = simulator.rebalance(
            current_state=PortfolioSnapshot(cash=100000.0, holding_symbol=None, holding_shares=0),
            target_symbol="510300",
            trade_date=date(2026, 3, 13),
        )
    finally:
        simulator.close()

    assert result.status == "rejected"
    assert result.action == "BUY"
    assert any("缺少 510300 买入价格" in reason for reason in result.reasons)
    assert result.final_state.cash == 100000.0


def test_simulator_rejects_buy_when_only_previous_day_price_exists():
    _seed_price("510300", date(2026, 3, 12), 5.0)
    simulator = ExecutionSimulator(TradePolicy(rebalance_frequency="monthly"))
    try:
        result = simulator.rebalance(
            current_state=PortfolioSnapshot(cash=100000.0, holding_symbol=None, holding_shares=0),
            target_symbol="510300",
            trade_date=date(2026, 3, 13),
        )
    finally:
        simulator.close()

    assert result.status == "rejected"
    assert result.action == "BUY"
    assert any("缺少 510300 买入价格" in reason for reason in result.reasons)
    assert result.final_state.cash == 100000.0


def test_simulator_returns_cash_when_sell_succeeds_but_buy_fails():
    _seed_price("510300", date(2026, 3, 13), 5.0)
    simulator = ExecutionSimulator(TradePolicy(rebalance_frequency="monthly"))
    try:
        result = simulator.rebalance(
            current_state=PortfolioSnapshot(cash=0.0, holding_symbol="510300", holding_shares=100),
            target_symbol="510500",
            trade_date=date(2026, 3, 13),
        )
    finally:
        simulator.close()

    assert result.action == "REBALANCE"
    assert result.final_state.holding_symbol is None
    assert result.final_state.holding_shares == 0
    assert result.final_state.cash > 0
    assert any("缺少 510500 买入价格" in reason for reason in result.reasons)


def test_simulator_rejects_rebalance_when_sell_price_missing_on_trade_date():
    _seed_price("510300", date(2026, 3, 12), 5.0)
    _seed_price("510500", date(2026, 3, 13), 6.0)
    simulator = ExecutionSimulator(TradePolicy(rebalance_frequency="monthly"))
    try:
        result = simulator.rebalance(
            current_state=PortfolioSnapshot(cash=0.0, holding_symbol="510300", holding_shares=100),
            target_symbol="510500",
            trade_date=date(2026, 3, 13),
        )
    finally:
        simulator.close()

    assert result.status == "rejected"
    assert result.action == "REBALANCE"
    assert any("缺少 510300 卖出价格" in reason for reason in result.reasons)
    assert result.final_state.holding_symbol == "510300"
    assert result.final_state.holding_shares == 100


def test_simulator_holds_existing_position():
    _seed_price("510300", date(2026, 3, 13), 5.0)
    simulator = ExecutionSimulator(TradePolicy(rebalance_frequency="monthly"))
    try:
        result = simulator.rebalance(
            current_state=PortfolioSnapshot(cash=1000.0, holding_symbol="510300", holding_shares=100),
            target_symbol="510300",
            trade_date=date(2026, 3, 13),
        )
    finally:
        simulator.close()

    assert result.status == "skipped"
    assert result.action == "HOLD"
    assert result.filled_shares == 100
    assert result.cash_after == 1000.0
    assert result.to_holdings_dict() == {"510300": 100}

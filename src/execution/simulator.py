"""统一成交模拟器。"""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from src.execution.trade_policy import TradePolicy
from src.storage.repositories import PriceRepository


class PortfolioSnapshot(BaseModel):
    """最小组合快照。"""

    cash: float = 0.0
    holding_symbol: str | None = None
    holding_shares: int = 0


class SimulatedFill(BaseModel):
    """单次成交结果。"""

    action: str
    filled_shares: int
    fill_price: float | None
    cash_after: float
    holding_symbol: str | None


class SimulationResult(BaseModel):
    """统一成交模拟输出。"""

    status: str
    action: str
    reasons: list[str] = Field(default_factory=list)
    fills: list[SimulatedFill] = Field(default_factory=list)
    final_state: PortfolioSnapshot
    target_symbol: str | None = None
    target_price: float | None = None
    estimated_shares: int = 0
    filled_shares: int = 0
    cash_after: float = 0.0
    total_asset: float = 0.0

    def to_holdings_dict(self) -> dict[str, int]:
        if self.final_state.holding_symbol is None or self.final_state.holding_shares <= 0:
            return {}
        return {self.final_state.holding_symbol: self.final_state.holding_shares}


class ExecutionSimulator:
    """统一处理卖出、买入、手续费与整手约束。"""

    def __init__(self, policy: TradePolicy, price_repo: Optional[PriceRepository] = None):
        self.policy = policy
        self.price_repo = price_repo or PriceRepository()
        self._owns_price_repo = price_repo is None

    def _normalize_state(self, state: PortfolioSnapshot) -> PortfolioSnapshot:
        cash = max(float(state.cash or 0.0), 0.0)
        shares = int(state.holding_shares or 0)
        symbol = state.holding_symbol if shares > 0 else None
        return PortfolioSnapshot(
            cash=cash,
            holding_symbol=symbol,
            holding_shares=shares if symbol else 0,
        )

    def _get_price(self, symbol: str, trade_date: date) -> float | None:
        price = self.price_repo.get_price_on_date(symbol, trade_date)
        if price is None or price <= 0:
            return None
        return float(price)

    def _estimate_shares(self, cash: float, price: float) -> int:
        raw_shares = int(cash / (price * (1 + self.policy.fee_rate)))
        return (raw_shares // self.policy.lot_size) * self.policy.lot_size

    def _portfolio_value(
        self,
        state: PortfolioSnapshot,
        trade_date: date,
        preferred_price: float | None = None,
    ) -> float:
        total = float(state.cash)
        if state.holding_symbol and state.holding_shares > 0:
            price = preferred_price if preferred_price is not None else self._get_price(state.holding_symbol, trade_date)
            if price is not None:
                total += state.holding_shares * price
        return total

    def _build_result(
        self,
        *,
        status: str,
        action: str,
        final_state: PortfolioSnapshot,
        trade_date: date,
        reasons: list[str] | None = None,
        fills: list[SimulatedFill] | None = None,
        target_symbol: str | None = None,
        target_price: float | None = None,
        estimated_shares: int = 0,
        filled_shares: int = 0,
        valuation_price: float | None = None,
    ) -> SimulationResult:
        normalized_state = self._normalize_state(final_state)
        return SimulationResult(
            status=status,
            action=action,
            reasons=reasons or [],
            fills=fills or [],
            final_state=normalized_state,
            target_symbol=target_symbol,
            target_price=target_price,
            estimated_shares=estimated_shares,
            filled_shares=filled_shares,
            cash_after=normalized_state.cash,
            total_asset=self._portfolio_value(normalized_state, trade_date, preferred_price=valuation_price),
        )

    def rebalance(
        self,
        current_state: PortfolioSnapshot,
        target_symbol: str | None,
        trade_date: date,
    ) -> SimulationResult:
        state = self._normalize_state(current_state)

        if target_symbol == state.holding_symbol:
            hold_price = self._get_price(target_symbol, trade_date) if target_symbol else None
            if target_symbol and hold_price is None:
                return self._build_result(
                    status="rejected",
                    action="HOLD",
                    final_state=state,
                    trade_date=trade_date,
                    reasons=[f"缺少 {target_symbol} 持仓价格"],
                    target_symbol=target_symbol,
                )
            return self._build_result(
                status="skipped",
                action="HOLD",
                final_state=state,
                trade_date=trade_date,
                target_symbol=target_symbol,
                target_price=hold_price,
                estimated_shares=state.holding_shares,
                filled_shares=state.holding_shares,
                valuation_price=hold_price,
            )

        if target_symbol is None and state.holding_symbol is None:
            return self._build_result(
                status="skipped",
                action="HOLD",
                final_state=state,
                trade_date=trade_date,
            )

        cash = float(state.cash)
        holding_symbol = state.holding_symbol
        holding_shares = int(state.holding_shares)
        fills: list[SimulatedFill] = []
        sold_first = False

        if holding_symbol and holding_symbol != target_symbol:
            sell_price = self._get_price(holding_symbol, trade_date)
            if sell_price is None:
                action = "MOVE_TO_CASH" if target_symbol is None else "REBALANCE"
                return self._build_result(
                    status="rejected",
                    action=action,
                    final_state=state,
                    trade_date=trade_date,
                    reasons=[f"缺少 {holding_symbol} 卖出价格"],
                    target_symbol=target_symbol,
                )

            cash += holding_shares * sell_price * (1 - self.policy.fee_rate)
            holding_symbol = None
            holding_shares = 0
            sold_first = True
            fills.append(
                SimulatedFill(
                    action="SELL",
                    filled_shares=state.holding_shares,
                    fill_price=sell_price,
                    cash_after=cash,
                    holding_symbol=None,
                )
            )

        if target_symbol is None:
            return self._build_result(
                status="filled" if sold_first else "skipped",
                action="MOVE_TO_CASH" if sold_first else "HOLD",
                final_state=PortfolioSnapshot(cash=cash, holding_symbol=None, holding_shares=0),
                trade_date=trade_date,
                fills=fills,
            )

        target_price = self._get_price(target_symbol, trade_date)
        if target_price is None:
            reason = f"缺少 {target_symbol} 买入价格"
            return self._build_result(
                status="partial" if sold_first else "rejected",
                action="REBALANCE" if sold_first else "BUY",
                final_state=PortfolioSnapshot(cash=cash, holding_symbol=None, holding_shares=0) if sold_first else state,
                trade_date=trade_date,
                reasons=[reason],
                fills=fills,
                target_symbol=target_symbol,
            )

        estimated_shares = self._estimate_shares(cash, target_price)
        if estimated_shares < self.policy.lot_size:
            reason = f"扣除手续费后可成交数量不足一个最小交易单位 {self.policy.lot_size} 股"
            return self._build_result(
                status="partial" if sold_first else "rejected",
                action="REBALANCE" if sold_first else "BUY",
                final_state=PortfolioSnapshot(cash=cash, holding_symbol=None, holding_shares=0) if sold_first else state,
                trade_date=trade_date,
                reasons=[reason],
                fills=fills,
                target_symbol=target_symbol,
                target_price=target_price,
                estimated_shares=estimated_shares,
            )

        cash -= estimated_shares * target_price * (1 + self.policy.fee_rate)
        final_state = PortfolioSnapshot(
            cash=max(cash, 0.0),
            holding_symbol=target_symbol,
            holding_shares=estimated_shares,
        )
        fills.append(
            SimulatedFill(
                action="BUY",
                filled_shares=estimated_shares,
                fill_price=target_price,
                cash_after=final_state.cash,
                holding_symbol=target_symbol,
            )
        )
        return self._build_result(
            status="filled",
            action="REBALANCE" if sold_first else "BUY",
            final_state=final_state,
            trade_date=trade_date,
            fills=fills,
            target_symbol=target_symbol,
            target_price=target_price,
            estimated_shares=estimated_shares,
            filled_shares=estimated_shares,
            valuation_price=target_price,
        )

    def close(self) -> None:
        if self._owns_price_repo:
            self.price_repo.close()

"""半自动执行器。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from src.core.config import config_loader
from src.core.logger import get_logger
from src.execution.checker import OrderChecker, OrderCheckResult, OrderRequest
from src.execution.simulator import ExecutionSimulator, PortfolioSnapshot, SimulationResult
from src.execution.trade_policy import TradePolicy
from src.storage.models import PortfolioState
from src.storage.repositories import ExecutionRepository, PortfolioRepository, PriceRepository

logger = get_logger(__name__)


@dataclass
class ExecutionResult:
    status: str
    action: str
    trade_date: date
    target_position: Optional[str]
    filled_shares: int = 0
    fill_price: Optional[float] = None
    cash_after: float = 0.0
    total_asset: float = 0.0
    reason: str = ""


class RebalanceExecutor:
    """基于检查结果执行模拟调仓，并记录状态。"""

    def __init__(
        self,
        policy: Optional[TradePolicy] = None,
        fee_rate: Optional[float] = None,
        lot_size: Optional[int] = None,
    ):
        base_policy = policy.model_copy() if policy is not None else config_loader.load_strategy_config().trade_policy.model_copy()
        if lot_size is not None:
            base_policy.lot_size = lot_size
        if fee_rate is not None:
            base_policy.fee_rate = fee_rate
        self.policy = base_policy
        self.fee_rate = self.policy.fee_rate
        self.lot_size = self.policy.lot_size
        self.checker = OrderChecker(policy=self.policy)
        self.portfolio_repo = PortfolioRepository()
        self.price_repo = PriceRepository()
        self.simulator = ExecutionSimulator(self.policy, price_repo=self.price_repo)
        self.execution_repo = ExecutionRepository()

    def _resolve_portfolio(self, trade_date: date, available_cash: float) -> tuple[float, Optional[str], float]:
        latest = self.portfolio_repo.get_latest_on_or_before(trade_date)
        if latest is None:
            return available_cash, None, 0.0
        cash = latest.cash if latest.cash is not None else available_cash
        return cash, latest.holding_symbol, latest.holding_shares or 0.0

    def _record_rejection(self, request: OrderRequest, check_result: OrderCheckResult) -> ExecutionResult:
        reason = "; ".join(check_result.reasons)
        self.execution_repo.add_record(
            trade_date=request.trade_date,
            action="REJECT",
            status="rejected",
            symbol=request.target_position,
            reason=reason,
            check_summary={
                "reasons": check_result.reasons,
                "estimated_price": check_result.estimated_price,
                "estimated_shares": check_result.estimated_shares,
            },
        )
        return ExecutionResult(
            status="rejected",
            action="REJECT",
            trade_date=request.trade_date,
            target_position=request.target_position,
            reason=reason,
            cash_after=request.available_cash,
            total_asset=request.available_cash,
        )

    def _record_sell_fill(self, request: OrderRequest, initial_state: PortfolioSnapshot, simulation: SimulationResult) -> None:
        sell_fill = next((item for item in simulation.fills if item.action == "SELL"), None)
        if sell_fill is None or initial_state.holding_symbol is None:
            return
        proceeds = sell_fill.filled_shares * (sell_fill.fill_price or 0.0) * (1 - self.fee_rate)
        self.execution_repo.add_record(
            trade_date=request.trade_date,
            action="SELL",
            status="filled",
            symbol=initial_state.holding_symbol,
            price=sell_fill.fill_price,
            shares=sell_fill.filled_shares,
            amount=proceeds,
            check_summary={"rebalance": request.rebalance},
        )

    def _persist_portfolio_state(self, trade_date: date, simulation: SimulationResult) -> None:
        state = PortfolioState(
            trade_date=trade_date,
            cash=simulation.cash_after,
            holding_symbol=simulation.final_state.holding_symbol,
            holding_shares=simulation.final_state.holding_shares,
            total_asset=simulation.total_asset,
            nav=simulation.total_asset,
        )
        self.portfolio_repo.save_state(state)

    def _build_execution_result(self, request: OrderRequest, simulation: SimulationResult) -> ExecutionResult:
        return ExecutionResult(
            status=simulation.status,
            action=simulation.action,
            trade_date=request.trade_date,
            target_position=request.target_position,
            filled_shares=simulation.filled_shares,
            fill_price=simulation.target_price,
            cash_after=simulation.cash_after,
            total_asset=simulation.total_asset,
            reason="; ".join(simulation.reasons),
        )

    def _record_simulation(
        self,
        request: OrderRequest,
        check_result: OrderCheckResult,
        initial_state: PortfolioSnapshot,
        simulation: SimulationResult,
    ) -> ExecutionResult:
        self._record_sell_fill(request, initial_state, simulation)

        summary = {
            "estimated_price": check_result.estimated_price,
            "estimated_shares": check_result.estimated_shares,
            "available_cash": request.available_cash,
        }

        if simulation.action == "HOLD":
            self.execution_repo.add_record(
                trade_date=request.trade_date,
                action="HOLD",
                status="skipped",
                symbol=initial_state.holding_symbol,
                price=simulation.target_price,
                shares=initial_state.holding_shares,
                amount=0.0,
                reason="当前持仓与目标持仓一致" if initial_state.holding_symbol else "保持现金",
                check_summary=summary,
            )
        elif simulation.action == "MOVE_TO_CASH":
            self.execution_repo.add_record(
                trade_date=request.trade_date,
                action="MOVE_TO_CASH",
                status=simulation.status,
                symbol=None,
                amount=0.0,
                reason="目标持仓为空，切换为空仓",
                check_summary=summary,
            )
        else:
            amount = simulation.filled_shares * (simulation.target_price or 0.0)
            self.execution_repo.add_record(
                trade_date=request.trade_date,
                action=simulation.action,
                status=simulation.status,
                symbol=request.target_position,
                price=simulation.target_price,
                shares=simulation.filled_shares,
                amount=amount,
                reason="; ".join(simulation.reasons) or None,
                check_summary=summary,
            )

        if simulation.status != "rejected":
            self._persist_portfolio_state(request.trade_date, simulation)

        return self._build_execution_result(request, simulation)

    def execute(self, request: OrderRequest) -> ExecutionResult:
        check_result = self.checker.check(request)
        if not check_result.passed:
            return self._record_rejection(request, check_result)

        cash, holding_symbol, holding_shares = self._resolve_portfolio(request.trade_date, request.available_cash)
        initial_state = PortfolioSnapshot(
            cash=cash,
            holding_symbol=holding_symbol,
            holding_shares=int(holding_shares or 0),
        )
        simulation = self.simulator.rebalance(
            current_state=initial_state,
            target_symbol=request.target_position,
            trade_date=request.trade_date,
        )
        if simulation.status == "rejected":
            rejection = OrderCheckResult(
                False,
                simulation.reasons,
                target_symbol=request.target_position,
                estimated_price=simulation.target_price,
                estimated_shares=simulation.estimated_shares,
                lot_size=self.lot_size,
            )
            return self._record_rejection(request, rejection)

        result = self._record_simulation(request, check_result, initial_state, simulation)
        logger.info(f"Execution finished: {result}")
        return result

    def close(self) -> None:
        self.checker.close()
        self.portfolio_repo.close()
        self.simulator.close()
        self.price_repo.close()
        self.execution_repo.close()

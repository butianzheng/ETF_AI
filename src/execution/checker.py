"""订单检查器。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from src.core.config import config_loader
from src.core.logger import get_logger
from src.data.calendar import trading_calendar
from src.execution.simulator import ExecutionSimulator, PortfolioSnapshot
from src.execution.trade_policy import TradePolicy
from src.storage.repositories import PortfolioRepository, PriceRepository

logger = get_logger(__name__)


@dataclass
class OrderRequest:
    trade_date: date
    target_position: Optional[str]
    current_position: Optional[str]
    available_cash: float
    order_amount: float
    rebalance: bool
    manual_approved: bool = True
    current_holding_shares: float = 0.0


@dataclass
class OrderCheckResult:
    passed: bool
    reasons: List[str] = field(default_factory=list)
    target_symbol: Optional[str] = None
    estimated_price: Optional[float] = None
    estimated_shares: int = 0
    lot_size: int = 100


class OrderChecker:
    """执行前规则检查。"""

    def __init__(
        self,
        policy: Optional[TradePolicy] = None,
        lot_size: Optional[int] = None,
        fee_rate: Optional[float] = None,
    ):
        base_policy = policy.model_copy() if policy is not None else config_loader.load_strategy_config().trade_policy.model_copy()
        if lot_size is not None:
            base_policy.lot_size = lot_size
        if fee_rate is not None:
            base_policy.fee_rate = fee_rate
        self.policy = base_policy
        self.lot_size = self.policy.lot_size
        self.fee_rate = self.policy.fee_rate
        self.whitelist = set(config_loader.get_enabled_etf_codes())
        self.price_repo = PriceRepository()
        self.portfolio_repo = PortfolioRepository()
        self.simulator = ExecutionSimulator(self.policy, price_repo=self.price_repo)

    def _check_whitelist(self, request: OrderRequest, reasons: List[str]) -> None:
        if request.target_position and request.target_position not in self.whitelist:
            reasons.append(f"目标 ETF {request.target_position} 不在白名单中")

    def _check_rebalance_rule(
        self,
        request: OrderRequest,
        current_position: Optional[str],
        reasons: List[str],
    ) -> None:
        if request.target_position != current_position and not request.rebalance:
            reasons.append("非调仓信号不允许变更持仓")

    def _check_manual_approval(self, request: OrderRequest, reasons: List[str]) -> None:
        if not request.manual_approved:
            reasons.append("未经过人工确认")

    def _trade_day_probes(self, request: OrderRequest, current_position: Optional[str]) -> List[str]:
        probes = [symbol for symbol in [request.target_position, current_position] if symbol]
        if not probes and self.whitelist:
            probes.append(sorted(self.whitelist)[0])
        return probes

    def _check_trading_day(
        self,
        request: OrderRequest,
        current_position: Optional[str],
        reasons: List[str],
    ) -> None:
        if trading_calendar.has_calendar() and trading_calendar.is_trading_day(request.trade_date):
            return

        probes = self._trade_day_probes(request, current_position)
        if any(self.price_repo.has_price_on_date(symbol, request.trade_date) for symbol in probes):
            return
        reasons.append(f"{request.trade_date} 不是交易日")

    def _resolve_portfolio_state(self, request: OrderRequest) -> PortfolioSnapshot:
        latest = self.portfolio_repo.get_latest_on_or_before(request.trade_date)
        if latest is not None:
            return PortfolioSnapshot(
                cash=float(latest.cash if latest.cash is not None else request.available_cash),
                holding_symbol=latest.holding_symbol,
                holding_shares=int(latest.holding_shares or 0),
            )
        return PortfolioSnapshot(
            cash=max(request.available_cash, 0.0),
            holding_symbol=request.current_position,
            holding_shares=int(request.current_holding_shares or 0),
        )

    def _preview(self, request: OrderRequest, current_state: PortfolioSnapshot):
        return self.simulator.rebalance(
            current_state=current_state,
            target_symbol=request.target_position,
            trade_date=request.trade_date,
        )

    def check(self, request: OrderRequest) -> OrderCheckResult:
        reasons: List[str] = []
        current_state = self._resolve_portfolio_state(request)
        self._check_manual_approval(request, reasons)
        self._check_trading_day(request, current_state.holding_symbol, reasons)
        self._check_whitelist(request, reasons)
        self._check_rebalance_rule(request, current_state.holding_symbol, reasons)
        preview = self._preview(request, current_state)
        if preview.status in {"rejected", "partial"}:
            for reason in preview.reasons:
                if reason not in reasons:
                    reasons.append(reason)
        result = OrderCheckResult(
            passed=not reasons,
            reasons=reasons,
            target_symbol=request.target_position,
            estimated_price=preview.target_price,
            estimated_shares=preview.estimated_shares,
            lot_size=self.lot_size,
        )
        logger.info(f"Order check completed: passed={result.passed}, reasons={result.reasons}")
        return result

    def close(self) -> None:
        self.simulator.close()
        self.portfolio_repo.close()
        self.price_repo.close()

"""数据访问层（Repositories）

提供业务友好的 CRUD 接口，封装 SQLAlchemy 会话的细节。
"""
from dataclasses import asdict
from datetime import date
import json
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from src.governance.models import GovernanceDecision
from src.governance.models import GovernanceIncident
from sqlalchemy.orm import Session
from src.storage.database import SessionLocal
from src.storage.models import (
    AgentLog,
    BacktestRun,
    ExecutionRecord,
    GovernanceDecisionRecord,
    GovernanceIncidentRecord,
    MarketPrice,
    PortfolioState,
    StrategySignal,
)


class BaseRepository:
    """基类，提供会话管理"""

    def __init__(self, session: Optional[Session] = None):
        self.session = session or SessionLocal()

    def close(self):
        self.session.close()


def _to_json_compatible(value):
    """将 dataclass/numpy 标量转换为 SQLite JSON 可接受的原生类型。"""
    if isinstance(value, dict):
        return {k: _to_json_compatible(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_compatible(v) for v in value]
    if isinstance(value, tuple):
        return [_to_json_compatible(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


class PriceRepository(BaseRepository):
    """行情价格表操作"""

    def save_prices(self, symbol: str, df: pd.DataFrame):
        """批量保存行情数据，按 symbol + trade_date 更新。"""
        trade_dates = df["trade_date"].tolist()
        existing_rows = (
            self.session.query(MarketPrice)
            .filter(
                MarketPrice.symbol == symbol,
                MarketPrice.trade_date.in_(trade_dates),
            )
            .all()
        )
        existing_by_date = {row.trade_date: row for row in existing_rows}

        for _, row in df.iterrows():
            trade_date = row["trade_date"]
            existing = existing_by_date.get(trade_date)

            if existing is None:
                existing = MarketPrice(
                    symbol=symbol,
                    trade_date=trade_date,
                )
                self.session.add(existing)
                existing_by_date[trade_date] = existing

            existing.open = row.get("open")
            existing.high = row.get("high")
            existing.low = row.get("low")
            existing.close = row.get("close")
            existing.volume = row.get("volume")
            existing.amount = row.get("amount")
            existing.source = row.get("source", "akshare")

        self.session.commit()

    def get_price_range(self, symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
        """查询指定时间段的行情返回 DataFrame"""
        rows = (self.session.query(MarketPrice)
                .filter(MarketPrice.symbol == symbol,
                        MarketPrice.trade_date >= start_date,
                        MarketPrice.trade_date <= end_date)
                .order_by(MarketPrice.trade_date)
                .all())
        if not rows:
            return pd.DataFrame()
        data = {
            "trade_date": [r.trade_date for r in rows],
            "open": [r.open for r in rows],
            "high": [r.high for r in rows],
            "low": [r.low for r in rows],
            "close": [r.close for r in rows],
            "volume": [r.volume for r in rows],
            "amount": [r.amount for r in rows],
        }
        return pd.DataFrame(data)

    def get_latest_price(self, symbol: str) -> Optional[float]:
        row = (self.session.query(MarketPrice)
               .filter(MarketPrice.symbol == symbol)
               .order_by(MarketPrice.trade_date.desc())
               .first())
        return row.close if row else None

    def get_latest_price_on_or_before(self, symbol: str, trade_date: date) -> Optional[float]:
        row = (
            self.session.query(MarketPrice)
            .filter(
                MarketPrice.symbol == symbol,
                MarketPrice.trade_date <= trade_date,
            )
            .order_by(MarketPrice.trade_date.desc())
            .first()
        )
        return row.close if row else None

    def get_price_on_date(self, symbol: str, trade_date: date) -> Optional[float]:
        row = (
            self.session.query(MarketPrice.close)
            .filter(
                MarketPrice.symbol == symbol,
                MarketPrice.trade_date == trade_date,
            )
            .first()
        )
        return float(row[0]) if row is not None and row[0] is not None else None

    def has_price_on_date(self, symbol: str, trade_date: date) -> bool:
        row = (
            self.session.query(MarketPrice.id)
            .filter(
                MarketPrice.symbol == symbol,
                MarketPrice.trade_date == trade_date,
            )
            .first()
        )
        return row is not None

    def get_multi_symbol_prices(self, symbols: List[str], start_date: date, end_date: date) -> Dict[str, pd.DataFrame]:
        result = {}
        for symbol in symbols:
            result[symbol] = self.get_price_range(symbol, start_date, end_date)
        return result

    def get_trading_dates(self, symbol: str, start_date: date, end_date: date) -> List[date]:
        rows = (
            self.session.query(MarketPrice.trade_date)
            .filter(
                MarketPrice.symbol == symbol,
                MarketPrice.trade_date >= start_date,
                MarketPrice.trade_date <= end_date,
            )
            .order_by(MarketPrice.trade_date)
            .all()
        )
        return [row[0] for row in rows]


class SignalRepository(BaseRepository):
    """策略信号表操作"""

    def save_signal(self, result):
        """保存 StrategyResult（来自 strategy/engine）"""
        scores_json = _to_json_compatible([asdict(s) for s in result.scores])
        signal = StrategySignal(
            strategy_version=result.strategy_version,
            trade_date=result.trade_date,
            current_position=result.current_position,
            target_position=result.target_position,
            rebalance=result.rebalance,
            signal_type="rebalance" if result.rebalance else "hold",
            scores_json=scores_json
        )
        self.session.add(signal)
        self.session.commit()

    def get_latest_signal(self) -> Optional[StrategySignal]:
        return (self.session.query(StrategySignal)
                .order_by(StrategySignal.trade_date.desc())
                .first())

    def get_signals_by_range(self, start: date, end: date) -> List[StrategySignal]:
        return (self.session.query(StrategySignal)
                .filter(StrategySignal.trade_date >= start,
                        StrategySignal.trade_date <= end)
                .order_by(StrategySignal.trade_date)
                .all())


class BacktestRepository(BaseRepository):
    def save_run(self, backtest_run: BacktestRun):
        self.session.add(backtest_run)
        self.session.commit()

    def get_runs(self, strategy_name: Optional[str] = None) -> List[BacktestRun]:
        q = self.session.query(BacktestRun)
        if strategy_name:
            q = q.filter(BacktestRun.strategy_name == strategy_name)
        return q.order_by(BacktestRun.created_at.desc()).all()


def _to_governance_decision(record: GovernanceDecisionRecord) -> GovernanceDecision:
    return GovernanceDecision(
        id=record.id,
        decision_date=record.decision_date,
        current_strategy_id=record.current_strategy_id,
        selected_strategy_id=record.selected_strategy_id,
        previous_strategy_id=record.previous_strategy_id,
        fallback_strategy_id=record.fallback_strategy_id,
        decision_type=record.decision_type,
        status=record.status,
        approved_by=record.approved_by,
        summary_hash=record.summary_hash,
        source_report_date=record.source_report_date,
        review_status=record.review_status,
        blocked_reasons=record.blocked_reasons_json or [],
        reason_codes=record.reason_codes_json or [],
        evidence=record.evidence_json or {},
    )


def _to_governance_incident(record: GovernanceIncidentRecord) -> GovernanceIncident:
    return GovernanceIncident(
        id=record.id,
        incident_date=record.incident_date,
        incident_type=record.incident_type,
        severity=record.severity,
        status=record.status,
        strategy_id=record.strategy_id,
        reason_codes=record.reason_codes_json or [],
        evidence=record.evidence_json or {},
    )


class GovernanceRepository(BaseRepository):
    """治理决策仓储。"""

    def get_by_id(self, decision_id: int) -> GovernanceDecision | None:
        record = self.session.get(GovernanceDecisionRecord, decision_id)
        if record is None:
            return None
        return _to_governance_decision(record)

    def get_latest(self) -> GovernanceDecision | None:
        record = (
            self.session.query(GovernanceDecisionRecord)
            .order_by(GovernanceDecisionRecord.id.desc())
            .first()
        )
        if record is None:
            return None
        return _to_governance_decision(record)

    def save_draft(self, decision: GovernanceDecision) -> GovernanceDecision:
        record = GovernanceDecisionRecord(
            decision_date=decision.decision_date,
            decision_type=decision.decision_type,
            status="draft",
            current_strategy_id=decision.current_strategy_id,
            selected_strategy_id=decision.selected_strategy_id,
            previous_strategy_id=decision.previous_strategy_id,
            fallback_strategy_id=decision.fallback_strategy_id,
            approved_by=decision.approved_by,
            summary_hash=decision.summary_hash,
            source_report_date=decision.source_report_date,
            review_status=decision.review_status,
            blocked_reasons_json=_to_json_compatible(decision.blocked_reasons),
            reason_codes_json=_to_json_compatible(decision.reason_codes),
            evidence_json=_to_json_compatible(decision.evidence),
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return _to_governance_decision(record)

    def find_draft_by_summary_hash(self, summary_hash: str) -> GovernanceDecision | None:
        record = (
            self.session.query(GovernanceDecisionRecord)
            .filter(
                GovernanceDecisionRecord.summary_hash == summary_hash,
                GovernanceDecisionRecord.status == "draft",
            )
            .order_by(GovernanceDecisionRecord.id.desc())
            .first()
        )
        if record is None:
            return None
        return _to_governance_decision(record)

    def set_review_status(
        self,
        decision_id: int,
        review_status: str,
        blocked_reasons: List[str],
    ) -> GovernanceDecision:
        record = self.session.get(GovernanceDecisionRecord, decision_id)
        if record is None:
            raise ValueError(f"governance decision not found: {decision_id}")
        record.review_status = review_status
        record.blocked_reasons_json = _to_json_compatible(blocked_reasons)
        self.session.commit()
        self.session.refresh(record)
        return _to_governance_decision(record)

    def approve(self, decision_id: int, approved_by: str) -> GovernanceDecision:
        record = self.session.get(GovernanceDecisionRecord, decision_id)
        if record is None:
            raise ValueError(f"governance decision not found: {decision_id}")
        record.status = "approved"
        record.approved_by = approved_by
        self.session.commit()
        self.session.refresh(record)
        return _to_governance_decision(record)

    def publish(self, decision_id: int) -> GovernanceDecision:
        record = self.session.get(GovernanceDecisionRecord, decision_id)
        if record is None:
            raise ValueError(f"governance decision not found: {decision_id}")
        if record.status not in {"draft", "approved"}:
            raise ValueError(f"cannot publish governance decision in status: {record.status}")
        record.status = "published"
        self.session.commit()
        self.session.refresh(record)
        return _to_governance_decision(record)

    def get_latest_published(self) -> GovernanceDecision | None:
        record = (
            self.session.query(GovernanceDecisionRecord)
            .filter(GovernanceDecisionRecord.status == "published")
            .order_by(GovernanceDecisionRecord.id.desc())
            .first()
        )
        if record is None:
            return None
        return _to_governance_decision(record)

    def rollback_latest(self, approved_by: str, reason: str) -> GovernanceDecision:
        latest = (
            self.session.query(GovernanceDecisionRecord)
            .filter(GovernanceDecisionRecord.status == "published")
            .order_by(GovernanceDecisionRecord.id.desc())
            .first()
        )
        if latest is None:
            raise ValueError("no published governance decision to rollback")

        latest.status = "rolled_back"
        rollback_target = latest.previous_strategy_id or latest.fallback_strategy_id
        rollback_record = GovernanceDecisionRecord(
            decision_date=latest.decision_date,
            decision_type="fallback",
            status="published",
            current_strategy_id=latest.selected_strategy_id,
            selected_strategy_id=rollback_target,
            previous_strategy_id=latest.selected_strategy_id,
            fallback_strategy_id=latest.fallback_strategy_id,
            approved_by=approved_by,
            review_status=latest.review_status,
            blocked_reasons_json=latest.blocked_reasons_json or [],
            reason_codes_json=["MANUAL_ROLLBACK"],
            evidence_json={"reason": reason},
        )
        self.session.add(rollback_record)
        self.session.commit()
        self.session.refresh(rollback_record)
        return _to_governance_decision(rollback_record)

    def save_incident(self, incident: GovernanceIncident) -> GovernanceIncident:
        record = GovernanceIncidentRecord(
            incident_date=incident.incident_date,
            incident_type=incident.incident_type,
            severity=incident.severity,
            status=incident.status,
            strategy_id=incident.strategy_id,
            reason_codes_json=_to_json_compatible(incident.reason_codes),
            evidence_json=_to_json_compatible(incident.evidence),
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return _to_governance_incident(record)

    def list_open_incidents(self) -> List[GovernanceIncident]:
        records = (
            self.session.query(GovernanceIncidentRecord)
            .filter(GovernanceIncidentRecord.status == "open")
            .order_by(GovernanceIncidentRecord.id.desc())
            .all()
        )
        return [_to_governance_incident(record) for record in records]

    def resolve_incident(self, incident_id: int) -> GovernanceIncident:
        record = self.session.get(GovernanceIncidentRecord, incident_id)
        if record is None:
            raise ValueError(f"governance incident not found: {incident_id}")
        record.status = "resolved"
        self.session.commit()
        self.session.refresh(record)
        return _to_governance_incident(record)


class AgentLogRepository(BaseRepository):
    def add_log(self, name: str, input_summary: dict, output_text: str, status: str = "ok"):
        log = AgentLog(
            agent_name=name,
            input_summary=input_summary,
            output_text=output_text,
            status=status
        )
        self.session.add(log)
        self.session.commit()
        return log

    def get_recent(self, name: str, limit: int = 5) -> List[AgentLog]:
        return (self.session.query(AgentLog)
                .filter(AgentLog.agent_name == name)
                .order_by(AgentLog.created_at.desc())
                .limit(limit)
                .all())


class ExecutionRepository(BaseRepository):
    def add_record(
        self,
        trade_date: date,
        action: str,
        status: str,
        symbol: Optional[str] = None,
        price: Optional[float] = None,
        shares: float = 0.0,
        amount: float = 0.0,
        reason: Optional[str] = None,
        check_summary: Optional[dict] = None,
    ) -> ExecutionRecord:
        record = ExecutionRecord(
            trade_date=trade_date,
            action=action,
            symbol=symbol,
            price=price,
            shares=shares,
            amount=amount,
            status=status,
            reason=reason,
            check_summary=check_summary,
        )
        self.session.add(record)
        self.session.commit()
        return record

    def get_latest(self) -> Optional[ExecutionRecord]:
        return (
            self.session.query(ExecutionRecord)
            .order_by(ExecutionRecord.created_at.desc())
            .first()
        )

    def list_by_trade_date(self, trade_date: date) -> List[ExecutionRecord]:
        return (
            self.session.query(ExecutionRecord)
            .filter(ExecutionRecord.trade_date == trade_date)
            .order_by(ExecutionRecord.created_at)
            .all()
        )


class PortfolioRepository(BaseRepository):
    def save_state(self, state: PortfolioState):
        existing = (
            self.session.query(PortfolioState)
            .filter(PortfolioState.trade_date == state.trade_date)
            .one_or_none()
        )

        if existing is None:
            self.session.add(state)
        else:
            existing.cash = state.cash
            existing.holding_symbol = state.holding_symbol
            existing.holding_shares = state.holding_shares
            existing.total_asset = state.total_asset
            existing.nav = state.nav

        self.session.commit()

    def get_by_date(self, trade_date: date) -> Optional[PortfolioState]:
        return (self.session.query(PortfolioState)
                .filter(PortfolioState.trade_date == trade_date)
                .first())

    def get_latest(self) -> Optional[PortfolioState]:
        return (self.session.query(PortfolioState)
                .order_by(PortfolioState.trade_date.desc())
                .first())

    def get_latest_on_or_before(self, trade_date: date) -> Optional[PortfolioState]:
        return (
            self.session.query(PortfolioState)
            .filter(PortfolioState.trade_date <= trade_date)
            .order_by(PortfolioState.trade_date.desc())
            .first()
        )

    def list_range(self, start: date, end: date) -> List[PortfolioState]:
        return (self.session.query(PortfolioState)
                .filter(PortfolioState.trade_date >= start,
                        PortfolioState.trade_date <= end)
                .order_by(PortfolioState.trade_date)
                .all())

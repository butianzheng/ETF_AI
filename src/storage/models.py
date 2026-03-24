"""ORM模型定义"""
from datetime import datetime
from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, JSON, String, Text, UniqueConstraint

from .database import Base


class MarketPrice(Base):
    __tablename__ = "market_price"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, index=True, nullable=False)  # ETF代码
    trade_date = Column(Date, index=True, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    amount = Column(Float)
    source = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("symbol", "trade_date", name="uq_market_price_symbol_date"),
    )


class StrategySignal(Base):
    __tablename__ = "strategy_signal"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_version = Column(String, nullable=False)
    trade_date = Column(Date, index=True, nullable=False)
    current_position = Column(String, nullable=True)
    target_position = Column(String, nullable=True)
    rebalance = Column(Boolean, default=False)
    signal_type = Column(String, nullable=False)  # SELL/BUY/HOLD/MOVE_TO_CASH
    scores_json = Column(JSON)  # 保存ETFScore列表的JSON快照
    created_at = Column(DateTime, default=datetime.utcnow)


class BacktestRun(Base):
    __tablename__ = "backtest_run"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_name = Column(String, nullable=False)
    parameter_snapshot = Column(JSON, nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    annual_return = Column(Float)
    max_drawdown = Column(Float)
    sharpe = Column(Float)
    turnover = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class GovernanceDecisionRecord(Base):
    __tablename__ = "governance_decision"

    id = Column(Integer, primary_key=True, autoincrement=True)
    decision_date = Column(Date, index=True, nullable=False)
    decision_type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    current_strategy_id = Column(String, nullable=True)
    selected_strategy_id = Column(String, nullable=False)
    previous_strategy_id = Column(String, nullable=True)
    fallback_strategy_id = Column(String, nullable=False)
    approved_by = Column(String, nullable=True)
    summary_hash = Column(String, nullable=True, index=True)
    source_report_date = Column(String, nullable=True)
    review_status = Column(String, nullable=False, default="pending")
    blocked_reasons_json = Column(JSON, nullable=True)
    reason_codes_json = Column(JSON, nullable=True)
    evidence_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class GovernanceIncidentRecord(Base):
    __tablename__ = "governance_incident"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_date = Column(Date, index=True, nullable=False)
    incident_type = Column(String, index=True, nullable=False)
    severity = Column(String, nullable=False)
    status = Column(String, index=True, nullable=False, default="open")
    strategy_id = Column(String, nullable=True)
    reason_codes_json = Column(JSON, nullable=True)
    evidence_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentLog(Base):
    __tablename__ = "agent_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String, nullable=False)
    input_summary = Column(JSON, nullable=True)
    output_text = Column(Text, nullable=True)
    status = Column(String, nullable=False)  # ok, warning, error
    created_at = Column(DateTime, default=datetime.utcnow)


class ExecutionRecord(Base):
    __tablename__ = "execution_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(Date, index=True, nullable=False)
    action = Column(String, nullable=False)  # BUY/SELL/HOLD/MOVE_TO_CASH/REBALANCE
    symbol = Column(String, nullable=True)
    price = Column(Float, nullable=True)
    shares = Column(Float, default=0.0)
    amount = Column(Float, default=0.0)
    status = Column(String, nullable=False)  # approved/rejected/filled/skipped
    reason = Column(Text, nullable=True)
    check_summary = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PortfolioState(Base):
    __tablename__ = "portfolio_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(Date, index=True, nullable=False)
    cash = Column(Float, default=0.0)
    holding_symbol = Column(String, nullable=True)
    holding_shares = Column(Float, default=0.0)
    total_asset = Column(Float)
    nav = Column(Float)  # 净值
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("trade_date", name="uq_portfolio_state_date"),
    )

"""数据访问层（Repositories）

提供业务友好的 CRUD 接口，封装 SQLAlchemy 会话的细节。
"""
from dataclasses import asdict
from datetime import date
import json
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from sqlalchemy.orm import Session
from src.storage.database import SessionLocal
from src.storage.models import AgentLog, BacktestRun, ExecutionRecord, MarketPrice, PortfolioState, StrategySignal


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

"""主流程入口。"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta
import json
from pathlib import Path
from typing import Any, Dict, Optional

from src.agents import DataQAAgent, DataQAInput, ReportAgent, ReportInput, RiskMonitorAgent, RiskMonitorInput
from src.core.config import config_loader
from src.core.logger import get_logger, setup_logger
from src.data.calendar import trading_calendar
from src.data.fetcher import DataFetcher
from src.data.normalizer import DataNormalizer
from src.data.validator import ValidationResult, DataValidator
from src.execution import OrderChecker, OrderRequest, RebalanceExecutor
from src.report_portal import build_report_portal
from src.storage.database import init_db
from src.storage.repositories import PortfolioRepository, PriceRepository, SignalRepository
from src.strategy.candidates.base import BaseCandidateStrategy
from src.strategy.candidates.trend_momentum import TrendMomentumStrategy
from src.strategy.engine import StrategyResult
from src.strategy.features import build_feature_snapshot
from src.strategy.momentum import MomentumCalculator
from src.strategy.selector import ETFScore, PositionSelector
from src.strategy.trend_filter import TrendFilter

logger = get_logger(__name__)


def _resolve_portfolio_state(as_of_date: date) -> Dict[str, Any]:
    portfolio_repo = PortfolioRepository()
    try:
        latest_state = portfolio_repo.get_latest_on_or_before(as_of_date)
        if latest_state is None:
            return {
                "cash": 0.0,
                "holding_symbol": None,
                "holding_shares": 0.0,
                "total_asset": 0.0,
                "nav": 0.0,
            }
        return {
            "cash": latest_state.cash or 0.0,
            "holding_symbol": latest_state.holding_symbol,
            "holding_shares": latest_state.holding_shares or 0.0,
            "total_asset": latest_state.total_asset or latest_state.cash or 0.0,
            "nav": latest_state.nav or latest_state.total_asset or latest_state.cash or 0.0,
        }
    finally:
        portfolio_repo.close()


def _load_price_data(as_of_date: date) -> Dict[str, Any]:
    fetcher = DataFetcher()
    normalizer = DataNormalizer()
    etf_pool = config_loader.load_etf_pool()
    strategy_config = config_loader.load_strategy_config()
    lookback_days = max(strategy_config.trend_filter.ma_period * 2, 365)
    start_date = as_of_date - timedelta(days=lookback_days)
    price_repo = PriceRepository()
    price_data: Dict[str, Any] = {}

    try:
        for etf in etf_pool:
            if not etf.enabled:
                continue

            df = fetcher.fetch_etf_daily(
                symbol=etf.code,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=as_of_date.strftime("%Y%m%d"),
            )
            df = normalizer.normalize_price_data(df)
            df = normalizer.remove_duplicates(df)
            price_repo.save_prices(etf.code, df)
            price_data[etf.code] = df

        return price_data
    finally:
        price_repo.close()


def _coerce_to_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime().date()
    if hasattr(value, "date"):
        return value.date()
    return None


def _load_trading_calendar_from_price_data(price_data: Dict[str, Any]) -> None:
    trading_days = sorted(
        {
            trade_date
            for df in price_data.values()
            if df is not None and not df.empty and "trade_date" in df.columns
            for trade_date in [_coerce_to_date(value) for value in df["trade_date"].tolist()]
            if trade_date is not None
        }
    )
    if trading_days:
        trading_calendar.load_calendar(trading_days)


def _validation_to_summary(validation_result: ValidationResult) -> Dict[str, Any]:
    return {
        "status": validation_result.status,
        "allow_strategy_run": validation_result.allow_strategy_run,
        "summary": validation_result.summary,
        "issues": [
            {
                "code": issue.code,
                "issue_type": issue.issue_type,
                "date": issue.date.isoformat() if issue.date else None,
                "description": issue.description,
                "severity": issue.severity,
            }
            for issue in validation_result.issues
        ],
    }


def _persist_price_data(price_data: Dict[str, Any]) -> None:
    price_repo = PriceRepository()
    try:
        for symbol, df in price_data.items():
            price_repo.save_prices(symbol, df)
    finally:
        price_repo.close()


def _load_portfolio_nav_series(as_of_date: date, fallback_state: Dict[str, Any]) -> list[Dict[str, Any]]:
    portfolio_repo = PortfolioRepository()
    try:
        history = portfolio_repo.list_range(as_of_date - timedelta(days=365), as_of_date)
    finally:
        portfolio_repo.close()

    nav_series = [
        {
            "date": state.trade_date.isoformat(),
            "nav": float(state.nav or state.total_asset or state.cash or 0.0),
        }
        for state in history
    ]
    if nav_series:
        return nav_series

    fallback_nav = float(fallback_state.get("nav", 0.0) or fallback_state.get("total_asset", 0.0) or fallback_state.get("cash", 0.0) or 1.0)
    return [{"date": as_of_date.isoformat(), "nav": fallback_nav}]


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, (date,)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


def build_candidate_strategy(strategy_id: str, strategy_config: Any) -> BaseCandidateStrategy:
    """Task 5 临时本地 builder，仅支持 trend_momentum。"""
    if strategy_id != "trend_momentum":
        raise ValueError(f"unsupported production strategy id: {strategy_id}")
    return TrendMomentumStrategy(
        return_20_weight=strategy_config.score_formula.return_20_weight,
        return_60_weight=strategy_config.score_formula.return_60_weight,
        allow_cash=strategy_config.allow_cash,
        trend_filter_enabled=strategy_config.trend_filter.enabled,
        trend_filter_ma_period=strategy_config.trend_filter.ma_period,
        trend_filter_ma_type=strategy_config.trend_filter.ma_type,
    )


def _build_compatible_scores(
    price_data: Dict[str, Any],
    etf_names: Dict[str, str],
    strategy_config: Any,
) -> list[ETFScore]:
    """复用旧评分语义，仅用于报告/信号兼容。"""
    momentum_calculator = MomentumCalculator(
        return_20_weight=strategy_config.score_formula.return_20_weight,
        return_60_weight=strategy_config.score_formula.return_60_weight,
    )
    scores = momentum_calculator.calculate_multi_symbol_scores(price_data)

    if strategy_config.trend_filter.enabled:
        trend_status = TrendFilter(
            ma_period=strategy_config.trend_filter.ma_period,
            ma_type=strategy_config.trend_filter.ma_type,
        ).apply_trend_filter(price_data)
    else:
        trend_status = {
            symbol: {
                "above_ma": True,
                "ma_value": None,
                "current_price": float(df["close"].iloc[-1]) if df is not None and not df.empty else None,
            }
            for symbol, df in price_data.items()
        }

    selector = PositionSelector(
        hold_count=strategy_config.hold_count,
        allow_cash=strategy_config.allow_cash,
    )
    return selector.get_all_scores(scores=scores, trend_status=trend_status, etf_names=etf_names)


def _generate_signal_description(result: StrategyResult) -> str:
    if result.rebalance:
        if result.target_position is None:
            return f"SELL {result.current_position}, MOVE_TO_CASH"
        if result.current_position is None:
            return f"BUY {result.target_position}"
        return f"SELL {result.current_position}, BUY {result.target_position}"
    if result.current_position is None:
        return "HOLD CASH"
    return f"HOLD {result.current_position}"


def _build_risk_input(
    trade_date: date,
    price_data: Dict[str, Any],
    portfolio_state: Dict[str, Any],
    nav_series: Optional[list[Dict[str, Any]]] = None,
) -> RiskMonitorInput:
    nav_series = nav_series or _load_portfolio_nav_series(trade_date, portfolio_state)
    benchmark_symbol = config_loader.get_enabled_etf_codes()[0]
    benchmark_df = price_data[benchmark_symbol]
    nav_start_date = date.fromisoformat(nav_series[0]["date"]) if nav_series else trade_date
    benchmark_series = []
    if not benchmark_df.empty:
        for _, row in benchmark_df.iterrows():
            row_date = _coerce_to_date(row["trade_date"])
            if row_date is None or row_date < nav_start_date or row_date > trade_date:
                continue
            benchmark_series.append({"date": row_date.isoformat(), "nav": float(row["close"])})
    if not benchmark_series and len(benchmark_df) >= 2:
        benchmark_series = [
            {"date": benchmark_df.iloc[-2]["trade_date"].isoformat(), "nav": float(benchmark_df.iloc[-2]["close"])},
            {"date": benchmark_df.iloc[-1]["trade_date"].isoformat(), "nav": float(benchmark_df.iloc[-1]["close"])},
        ]
    elif not benchmark_series:
        benchmark_series = [{"date": trade_date.isoformat(), "nav": 1.0}]

    current_nav = float(nav_series[-1]["nav"]) if nav_series else float(portfolio_state.get("nav", 0.0) or portfolio_state.get("total_asset", 0.0) or 1.0)
    peak_nav = max([float(item["nav"]) for item in nav_series] + [1.0])
    current_drawdown = current_nav / peak_nav - 1 if peak_nav else 0.0
    return RiskMonitorInput(
        nav_series=nav_series,
        benchmark_series=benchmark_series,
        recent_signals=[],
        account_status={
            "cash_ratio": (portfolio_state.get("cash", 0.0) / current_nav) if current_nav else 1.0,
            "holding_symbol": portfolio_state.get("holding_symbol"),
        },
        current_drawdown=current_drawdown,
    )


def _save_daily_report(trade_date: date, markdown_report: str, payload: Dict[str, Any]) -> Dict[str, str]:
    report_dir = Path("reports/daily")
    report_dir.mkdir(parents=True, exist_ok=True)
    base_name = trade_date.isoformat()
    markdown_path = report_dir / f"{base_name}.md"
    json_path = report_dir / f"{base_name}.json"
    markdown_path.write_text(markdown_report, encoding="utf-8")
    json_path.write_text(json.dumps(_to_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    return {"markdown": str(markdown_path), "json": str(json_path)}


def run_daily_pipeline(
    as_of_date: Optional[date] = None,
    log_level: str = "INFO",
    execute_trade: bool = False,
    manual_approved: bool = False,
    available_cash: float = 100000.0,
    refresh_data: bool = True,
    price_data_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """执行日常策略、Agent 和半自动执行闭环。"""
    setup_logger(log_level=log_level)
    init_db()

    trade_date = as_of_date or date.today()
    strategy_config = config_loader.load_strategy_config()
    active_strategy_id = config_loader.load_production_strategy_id()
    active_strategy = build_candidate_strategy(active_strategy_id, strategy_config)
    etf_pool = config_loader.load_etf_pool()
    etf_names = {item.code: item.name for item in etf_pool if item.enabled}
    logger.info(f"Running daily pipeline for {trade_date}")

    if price_data_override is not None:
        price_data = price_data_override
        _persist_price_data(price_data)
    elif refresh_data:
        price_data = _load_price_data(trade_date)
    else:
        price_repo = PriceRepository()
        try:
            symbols = config_loader.get_enabled_etf_codes()
            price_data = price_repo.get_multi_symbol_prices(symbols, trade_date - timedelta(days=365), trade_date)
        finally:
            price_repo.close()

    _load_trading_calendar_from_price_data(price_data)

    validator = DataValidator()
    validation_result: ValidationResult = validator.validate_multi_symbols(
        price_data,
        required_days=max(strategy_config.trend_filter.ma_period, 120),
    )
    validation_summary = _validation_to_summary(validation_result)
    data_qa_output = DataQAAgent().run(
        DataQAInput(
            symbols=config_loader.get_enabled_etf_codes(),
            validation_summary=validation_summary,
        )
    )

    if not validation_result.allow_strategy_run:
        logger.error(validation_result.summary)
        report_output = ReportAgent().run(
            ReportInput(
                trade_date=trade_date.isoformat(),
                current_position=None,
                target_position=None,
                rebalance=False,
                scores=[],
                risk_status="red",
                data_status=data_qa_output.status,
                execution_status="blocked",
                execution_reason=validation_result.summary,
            )
        )
        report_paths = _save_daily_report(
            trade_date,
            report_output.markdown_report,
            {
                "status": "blocked",
                "validation": validation_summary,
                "data_qa_output": data_qa_output.model_dump(),
                "report_output": report_output.model_dump(),
            },
        )
        portal_paths = build_report_portal()["output_paths"]
        return {
            "status": "blocked",
            "validation": validation_result,
            "data_qa_output": data_qa_output,
            "strategy_result": None,
            "report_output": report_output,
            "report_paths": report_paths,
            "portal_paths": portal_paths,
        }

    portfolio_state = _resolve_portfolio_state(trade_date)
    current_position = portfolio_state["holding_symbol"]
    current_holding_shares = portfolio_state["holding_shares"]
    current_cash = portfolio_state["cash"] if portfolio_state["total_asset"] > 0 else available_cash
    if portfolio_state["total_asset"] <= 0:
        portfolio_state["cash"] = current_cash
        portfolio_state["total_asset"] = current_cash
        portfolio_state["nav"] = current_cash

    snapshot = build_feature_snapshot(price_data, benchmark_data={})
    proposal = active_strategy.generate(
        snapshot,
        current_position=current_position,
    )
    strategy_result = StrategyResult(
        trade_date=trade_date,
        strategy_version=f"{proposal.strategy_id}_v{strategy_config.version}",
        rebalance=proposal.target_etf != current_position,
        current_position=current_position,
        target_position=proposal.target_etf,
        scores=_build_compatible_scores(price_data, etf_names, strategy_config),
        risk_mode="normal",
    )

    signal_repo = SignalRepository()
    try:
        signal_repo.save_signal(strategy_result)
    finally:
        signal_repo.close()

    risk_output = RiskMonitorAgent().run(_build_risk_input(trade_date, price_data, portfolio_state))

    order_amount = current_cash
    if current_position and current_position != strategy_result.target_position:
        current_df = price_data.get(current_position)
        if current_df is not None and not current_df.empty:
            current_price = float(current_df.iloc[-1]["close"])
            order_amount += current_holding_shares * current_price

    order_request = OrderRequest(
        trade_date=trade_date,
        target_position=strategy_result.target_position,
        current_position=current_position,
        available_cash=current_cash,
        order_amount=order_amount,
        rebalance=strategy_result.rebalance,
        manual_approved=manual_approved,
        current_holding_shares=current_holding_shares,
    )

    checker = OrderChecker(policy=strategy_config.trade_policy)
    try:
        order_check_result = checker.check(order_request)
    finally:
        checker.close()

    execution_result: Optional[Dict[str, Any]] = None
    execution_status = "checked" if order_check_result.passed else "rejected"
    execution_reason = "; ".join(order_check_result.reasons) if order_check_result.reasons else "执行前检查通过"

    if execute_trade and order_check_result.passed:
        executor = RebalanceExecutor(policy=strategy_config.trade_policy)
        try:
            executed = executor.execute(order_request)
            execution_result = asdict(executed)
            execution_status = executed.status
            execution_reason = executed.reason or "模拟执行完成"
        finally:
            executor.close()
    elif execute_trade and not order_check_result.passed:
        execution_status = "rejected"
    elif not execute_trade:
        execution_status = "awaiting_manual_confirmation"
        execution_reason = "已完成检查，等待人工确认执行"

    report_output = ReportAgent().run(
        ReportInput(
            trade_date=trade_date.isoformat(),
            current_position=current_position,
            target_position=strategy_result.target_position,
            rebalance=strategy_result.rebalance,
            scores=[asdict(score) for score in strategy_result.scores],
            risk_status=risk_output.risk_level,
            data_status=data_qa_output.status,
            execution_status=execution_status,
            execution_reason=execution_reason,
            data={"active_strategy_id": proposal.strategy_id, "reason_codes": proposal.reason_codes},
        )
    )

    payload = {
        "status": "ok",
        "validation": validation_summary,
        "data_qa_output": data_qa_output.model_dump(),
        "strategy_result": strategy_result.to_dict(),
        "strategy_proposal": proposal.model_dump(),
        "risk_output": risk_output.model_dump(),
        "order_check_result": asdict(order_check_result),
        "execution_result": execution_result,
        "report_output": report_output.model_dump(),
    }
    report_paths = _save_daily_report(trade_date, report_output.markdown_report, payload)
    portal_paths = build_report_portal()["output_paths"]

    logger.info(_generate_signal_description(strategy_result))
    logger.info(f"Daily report written to {report_paths['markdown']}")
    logger.info(f"Report portal written to {portal_paths['html']}")
    return {
        "status": "ok",
        "validation": validation_result,
        "data_qa_output": data_qa_output,
        "strategy_result": strategy_result,
        "risk_output": risk_output,
        "order_check_result": order_check_result,
        "execution_result": execution_result,
        "report_output": report_output,
        "report_paths": report_paths,
        "portal_paths": portal_paths,
    }

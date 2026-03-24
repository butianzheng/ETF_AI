"""运行回测脚本。"""
import argparse
from datetime import date, timedelta
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backtest.engine import SimpleBacktestEngine
from src.backtest.evaluator import evaluate_backtest
from src.core.config import config_loader
from src.core.logger import get_logger, setup_logger

logger = get_logger(__name__)


def _parse_args() -> argparse.Namespace:
    today = date.today()
    default_start = today - timedelta(days=365)

    parser = argparse.ArgumentParser(description="运行 ETF 动量轮动回测")
    parser.add_argument("--start-date", default=default_start.isoformat(), help="开始日期，格式 YYYY-MM-DD")
    parser.add_argument("--end-date", default=today.isoformat(), help="结束日期，格式 YYYY-MM-DD")
    parser.add_argument("--initial-capital", type=float, default=100000.0, help="初始资金")
    parser.add_argument("--fee-rate", type=float, default=0.001, help="手续费率")
    parser.add_argument("--log-level", default="INFO", help="日志级别")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    setup_logger(log_level=args.log_level)

    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    strategy_config = config_loader.load_strategy_config()

    engine = SimpleBacktestEngine(
        config=strategy_config,
        start_date=start_date,
        end_date=end_date,
        initial_capital=args.initial_capital,
        fee_rate=args.fee_rate,
    )

    nav_series, results = engine.run()
    metrics = evaluate_backtest(nav_series, trades=len(results))

    logger.info("Backtest finished")
    logger.info(f"Period: {start_date} -> {end_date}")
    logger.info(f"Signals: {len(results)}")
    logger.info(f"Final NAV: {nav_series.iloc[-1]:.4f}")
    logger.info(f"Annual Return: {metrics['annual_return']:.2%}")
    logger.info(f"Max Drawdown: {metrics['max_drawdown']:.2%}")
    logger.info(f"Sharpe: {metrics['sharpe']:.4f}")
    logger.info(f"Turnover: {metrics['turnover']:.4f}")


if __name__ == "__main__":
    main()

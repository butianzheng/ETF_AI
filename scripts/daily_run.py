"""执行日常策略脚本。"""
import argparse
from datetime import date
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.main import run_daily_pipeline


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="执行 ETF 动量轮动日常流程（兼容入口，推荐改用 `python scripts/etf_ops.py ...`）"
    )
    parser.add_argument("--date", default=None, help="交易日期，格式 YYYY-MM-DD，默认今天")
    parser.add_argument("--log-level", default="INFO", help="日志级别")
    parser.add_argument("--execute", action="store_true", help="通过检查后执行模拟调仓")
    parser.add_argument("--manual-approve", action="store_true", help="标记已人工确认")
    parser.add_argument("--available-cash", type=float, default=100000.0, help="初始或可用现金")
    return parser.parse_args(argv)


def run_daily_entrypoint(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    as_of_date = date.fromisoformat(args.date) if args.date else None
    run_daily_pipeline(
        as_of_date=as_of_date,
        log_level=args.log_level,
        execute_trade=args.execute,
        manual_approved=args.manual_approve,
        available_cash=args.available_cash,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    from src.cli.commands import run_daily_command

    effective_argv = sys.argv[1:] if argv is None else argv
    return int(run_daily_command(effective_argv, entrypoint=run_daily_entrypoint))


if __name__ == "__main__":
    raise SystemExit(main())

"""执行研究线脚本。"""
import argparse
from datetime import date, timedelta
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.research_candidate_config import load_candidate_specs
from src.research_pipeline import run_research_pipeline


def _parse_args() -> argparse.Namespace:
    today = date.today()
    default_start = today - timedelta(days=365)
    parser = argparse.ArgumentParser(description="执行 ETF 参数研究与报告生成")
    parser.add_argument("--start-date", default=default_start.isoformat(), help="开始日期，格式 YYYY-MM-DD")
    parser.add_argument("--end-date", default=today.isoformat(), help="结束日期，格式 YYYY-MM-DD")
    parser.add_argument("--initial-capital", type=float, default=100000.0, help="初始资金")
    parser.add_argument("--fee-rate", type=float, default=0.001, help="手续费率")
    parser.add_argument("--candidate-config", help="研究候选配置文件路径，默认使用 config/research.yaml")
    parser.add_argument("--log-level", default="INFO", help="日志级别")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    run_research_pipeline(
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date),
        candidate_specs=load_candidate_specs(args.candidate_config),
        initial_capital=args.initial_capital,
        fee_rate=args.fee_rate,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()

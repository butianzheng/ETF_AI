"""汇总研究报告脚本。"""
import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.research_summary import aggregate_research_reports
from src.report_portal import build_report_portal


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="汇总 reports/research 下的研究报告")
    parser.add_argument("--report-dir", default="reports/research", help="研究报告目录")
    parser.add_argument("--output-dir", help="汇总输出目录，默认写入 reports/research/summary")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = aggregate_research_reports(report_dir=args.report_dir, output_dir=args.output_dir)
    portal_result = build_report_portal(research_dir=args.report_dir)
    for name, path in result["output_paths"].items():
        print(f"{name}: {path}")
    for name, path in portal_result["output_paths"].items():
        print(f"portal_{name}: {path}")


if __name__ == "__main__":
    main()

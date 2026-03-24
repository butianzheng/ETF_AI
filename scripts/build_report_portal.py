"""构建统一报告门户脚本。"""
import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.report_portal import build_report_portal


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建日报与研究统一门户")
    parser.add_argument("--daily-dir", default="reports/daily", help="日报目录")
    parser.add_argument("--research-dir", default="reports/research", help="研究报告目录")
    parser.add_argument("--output-dir", default="reports", help="门户输出目录")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = build_report_portal(
        daily_dir=args.daily_dir,
        research_dir=args.research_dir,
        output_dir=args.output_dir,
    )
    for name, path in result["output_paths"].items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()

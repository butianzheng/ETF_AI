"""初始化数据库脚本

使用 src.storage.database.init_db 创建所有表。
"""
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.database import init_db

if __name__ == "__main__":
    init_db()

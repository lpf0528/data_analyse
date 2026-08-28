"""
SQLite 数据库初始化脚本
读取 scripts/schema_sqlite.sql 执行 DDL，自动创建 data/nl2sql_meta.db 数据库及其结构。
"""

from pathlib import Path
import sqlite3
import sys

# 默认 SQLite 数据库路径
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "nl2sql_meta.db"
SQL_SCHEMA_PATH = BASE_DIR / "scripts" / "schema_sqlite.sql"


def init_db(db_path: Path = DB_PATH, schema_path: Path = SQL_SCHEMA_PATH) -> Path:
    """使用 SQL 文件初始化 SQLite 数据库"""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if not schema_path.exists():
        raise FileNotFoundError(f"DDL file not found: {schema_path}")

    schema_sql = schema_path.read_text(encoding="utf-8")

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        # 启用外键约束
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.executescript(schema_sql)
        conn.commit()
        print(f"[OK] SQLite database initialized successfully at: {db_path}")
    finally:
        conn.close()

    return db_path


if __name__ == "__main__":
    try:
        init_db()
    except Exception as e:
        print(f"[ERROR] Failed to initialize SQLite database: {e}", file=sys.stderr)
        sys.exit(1)

"""
Metabase 查询 CLI 示例：复用 utils.metabase_client。

用法：
  python metabase.py
  python metabase.py --sql "select 1"
"""
from __future__ import annotations

import argparse
import logging

from utils.metabase_client import client_from_secrets, metabase_data_to_dataframe

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="经 Metabase 执行原生 SQL")
    parser.add_argument(
        "--sql",
        default="select * from warehouse.dim_lh_term_student_metrics limit 10",
        help="要执行的 SQL",
    )
    parser.add_argument("--db-id", type=int, default=None, help="Metabase database id")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 与前端共用同一套配置解析（secrets.toml / 环境变量）
    client = client_from_secrets()
    data = client.query_raw(args.sql, db_id=args.db_id)
    df = metabase_data_to_dataframe(data)
    logger.info("查询成功：%d 行 × %d 列", len(df), len(df.columns))
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()

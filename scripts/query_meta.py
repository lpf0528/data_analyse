"""
NL2SQL 元数据动态检索工具 CLI
用于 Agent 根据用户自然语言问题，按需查询相关表结构、字段字典及 SQL 模板，避免加载全量 Markdown 上下文。

用法示例:
1. 列出所有可用的表概览:
   uv run python scripts/query_meta.py --list

2. 根据关键词模糊检索最相关的表结构 (支持多个关键词，空格隔开):
   uv run python scripts/query_meta.py --search "学员 授权 班级"

3. 查询指定数据表的完整元信息:
   uv run python scripts/query_meta.py --table "dws_lh_teaching_term_class_week,dwd_lh_classes"

4. 检索常用/特定 SQL 查询模板:
   uv run python scripts/query_meta.py --template "最新周"
"""

import argparse
from pathlib import Path
import sqlite3
import sys
from typing import List, Optional

# 设置标准输出编码，解决 Windows 控制台 GBK 字符处理
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "nl2sql_meta.db"

# 确保能 import utils.nl2sql_meta
sys.path.insert(0, str(BASE_DIR))
from utils.nl2sql_meta import get_all_query_templates, get_all_table_metas, get_table_detail


def list_tables_summary():
    """输出轻量级的表列表概览"""
    tables = get_all_table_metas()
    print(f"=== 已注册数据表列表 (共 {len(tables)} 张) ===")
    for idx, t in enumerate(tables, start=1):
        print(f"{idx}. 表名: `{t['table_name']}` | 板块: `{t['domain']}`")
        print(f"   适用场景: {t['use_for'].strip()}")
        print()


def get_tables_detail(table_names: List[str]):
    """打印一张或多张表的完整 Schema"""
    for name in table_names:
        tbl_name = name.strip()
        detail = get_table_detail(tbl_name)
        if not detail:
            print(f"⚠️ 未找到数据表: `{tbl_name}`\n")
            continue

        print(f"==================================================")
        print(f"### 表名: `{detail['table_name']}`")
        print(f"- **domain**: {detail['domain']}")
        print(f"- **use_for**: {detail['use_for']}")

        if detail["required_filters"]:
            print(f"- **required_filters**:")
            print("  ```sql")
            for r_line in detail["required_filters"].splitlines():
                print(f"  {r_line}")
            print("  ```")

        if detail["optional_filters"]:
            print(f"- **optional_filters**:")
            print("  ```sql")
            for o_line in detail["optional_filters"].splitlines():
                print(f"  {o_line}")
            print("  ```")

        cols = detail.get("columns", [])
        if cols:
            print("\n| 字段名 | 类型 | 说明 | 主键/外键 |")
            print("|------|------|------|----------|")
            for c in cols:
                pk_fk = []
                if c["is_pk"]:
                    pk_fk.append("PK")
                if c["is_fk"]:
                    ref = f"FK -> {c['ref_table_name']}.{c['ref_column_name']}" if c["ref_table_name"] else "FK"
                    pk_fk.append(ref)
                pf_str = ", ".join(pk_fk) if pk_fk else "-"
                print(f"| `{c['column_name']}` | {c['data_type']} | {c['column_comment']} | {pf_str} |")

        examples = detail.get("examples", [])
        if examples:
            print("\n**典型 SQL 示例:**")
            for ex in examples:
                print(f"\n📌 {ex['example_name']}")
                print("```sql")
                print(ex["sql_content"])
                print("```")
        print(f"==================================================\n")


def search_tables(query_str: str):
    """根据关键词模糊检索匹配的表及其 Schema"""
    keywords = [kw.strip() for kw in query_str.split() if kw.strip()]
    if not keywords:
        list_tables_summary()
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    matched_table_ids = set()

    try:
        for kw in keywords:
            like_pat = f"%{kw}%"
            # 搜表级属性
            cursor.execute("""
                SELECT id FROM nl2sql_table_meta
                WHERE table_name LIKE ? OR domain LIKE ? OR use_for LIKE ? OR required_filters LIKE ?;
            """, (like_pat, like_pat, like_pat, like_pat))
            for row in cursor.fetchall():
                matched_table_ids.add(row["id"])

            # 搜字段级属性
            cursor.execute("""
                SELECT table_id FROM nl2sql_column_meta
                WHERE column_name LIKE ? OR column_comment LIKE ?;
            """, (like_pat, like_pat))
            for row in cursor.fetchall():
                matched_table_ids.add(row["table_id"])
    finally:
        conn.close()

    if not matched_table_ids:
        print(f"🔍 未检索到与 '{query_str}' 匹配的数据表。以下是当前数据表目录概览：\n")
        list_tables_summary()
        return

    print(f"🔍 针对关键词 '{query_str}' 匹配到 {len(matched_table_ids)} 张相关表元数据：\n")
    all_metas = get_all_table_metas()
    matched_names = [t["table_name"] for t in all_metas if t["id"] in matched_table_ids]
    get_tables_detail(matched_names)


def search_templates(kw_str: Optional[str] = None):
    """查询常用/特定 SQL 模板"""
    templates = get_all_query_templates()
    if not templates:
        print("未查找到常用查询模板。")
        return

    if kw_str:
        matched = [t for t in templates if kw_str in t["title"] or kw_str in t["category"] or kw_str in t["scenario"] or kw_str in t["related_tables"]]
    else:
        matched = templates

    print(f"=== 常用 SQL 查询模板 (匹配到 {len(matched)} 个) ===")
    for idx, t in enumerate(matched, start=1):
        print(f"\n{idx}. 模板标题: `{t['title']}` ({t['category']})")
        print(f"   涉及数据源: `{t['related_tables']}`")
        print(f"   业务场景: {t['scenario'].strip()}")
        print("```sql")
        print(t["sql_template"])
        print("```")
        if t["notes"]:
            print(f"   防错约定: {t['notes'].strip()}")
        print("-" * 50)


def main():
    parser = argparse.ArgumentParser(description="NL2SQL 元数据动态检索 CLI 工具")
    parser.add_argument("--list", action="store_true", help="输出所有表概览列表")
    parser.add_argument("--search", type=str, help="按关键词模糊检索匹配的表结构")
    parser.add_argument("--table", type=str, help="指定数据表名，以逗号分隔")
    parser.add_argument("--template", type=str, nargs="?", const="", help="查询常用/特定 SQL 模板")

    args = parser.parse_args()

    if args.list:
        list_tables_summary()
    elif args.search:
        search_tables(args.search)
    elif args.table:
        table_names = args.table.split(",")
        get_tables_detail(table_names)
    elif args.template is not None:
        search_templates(args.template)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

"""
SQLite 数据库 (nl2sql_meta.db) 到 Markdown 参考文件 (schema.md & queries.md) 的同步导出脚本。
用于在修改 SQLite 配置数据库后重新生成标准 Markdown，保障离线与静态兜底。
"""

from pathlib import Path
import sqlite3
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "nl2sql_meta.db"
SCHEMA_MD_PATH = BASE_DIR / ".agents" / "skills" / "nl2sql-metabase" / "references" / "schema.md"
QUERIES_MD_PATH = BASE_DIR / ".agents" / "skills" / "nl2sql-metabase" / "references" / "queries.md"


def export_to_md(db_path: Path = DB_PATH, schema_md_path: Path = SCHEMA_MD_PATH, queries_md_path: Path = QUERIES_MD_PATH):
    """从 SQLite 数据库导出 Markdown"""
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database file not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # ----------------------------------------------------------------------
        # 1. 导出 schema.md
        # ----------------------------------------------------------------------
        cursor.execute("SELECT DISTINCT domain FROM nl2sql_table_meta WHERE status = 1 ORDER BY id;")
        domains = [row["domain"] for row in cursor.fetchall()]

        schema_lines = [
            "# Schema Reference — warehouse 数据库",
            "",
            "## 表元数据协议说明",
            "",
            "每张表用以下结构声明约束，SKILL.md 中的规则引擎会读取并应用这些元数据：",
            "",
            "```",
            "- **alias**: 推荐别名",
            "- **use_for**: 适合回答哪类问题（用于表选择决策）",
            "- **required_filters**: 使用此表必须注入的强制条件（无 [[]]），CTE 型表则为固定 WITH 写法",
            "- **optional_filters**: 可选条件（有则加 [[]]）；未列出时按业务需要自行添加",
            "- **examples**: 该表的典型 SQL 用法（1-2 个）",
            "```",
            "",
            "---",
            "",
        ]

        for dom in domains:
            schema_lines.append(f"## {dom}")
            schema_lines.append("")

            cursor.execute("""
                SELECT * FROM nl2sql_table_meta
                WHERE domain = ? AND status = 1
                ORDER BY id;
            """, (dom,))
            tables = cursor.fetchall()

            for tbl in tables:
                table_id = tbl["id"]
                table_name = tbl["table_name"]
                alias = tbl["table_alias"]
                use_for = tbl["use_for"]
                req_filters = tbl["required_filters"]
                opt_filters = tbl["optional_filters"]

                schema_lines.append(f"### {table_name}")
                schema_lines.append("")
                schema_lines.append(f"- **alias**: `{alias}`")
                schema_lines.append(f"- **use_for**: {use_for}")

                if req_filters:
                    schema_lines.append("- **required_filters**:")
                    schema_lines.append("  ```sql")
                    for r_line in req_filters.splitlines():
                        schema_lines.append(f"  {r_line}")
                    schema_lines.append("  ```")

                if opt_filters:
                    schema_lines.append("- **optional_filters**（可选，加 `[[]]`）:")
                    schema_lines.append("  ```sql")
                    for o_line in opt_filters.splitlines():
                        schema_lines.append(f"  {o_line}")
                    schema_lines.append("  ```")

                schema_lines.append("")

                # 查询字段字典
                cursor.execute("""
                    SELECT * FROM nl2sql_column_meta
                    WHERE table_id = ?
                    ORDER BY sort_order ASC, id ASC;
                """, (table_id,))
                cols = cursor.fetchall()

                if cols:
                    schema_lines.append("| 字段 | 类型 | 说明 |")
                    schema_lines.append("|------|------|------|")
                    for col in cols:
                        c_name = col["column_name"]
                        c_type = col["data_type"]
                        c_comm = col["column_comment"]
                        schema_lines.append(f"| {c_name} | {c_type} | {c_comm} |")
                    schema_lines.append("")

                # 查询典型 SQL 示例
                cursor.execute("""
                    SELECT * FROM nl2sql_table_example
                    WHERE table_id = ?
                    ORDER BY sort_order ASC, id ASC;
                """, (table_id,))
                examples = cursor.fetchall()

                for ex in examples:
                    ex_name = ex["example_name"]
                    ex_sql = ex["sql_content"]
                    schema_lines.append(f"**{ex_name}**")
                    schema_lines.append("```sql")
                    schema_lines.append(ex_sql)
                    schema_lines.append("```")
                    schema_lines.append("")

                schema_lines.append("---")
                schema_lines.append("")

        schema_md_path.parent.mkdir(parents=True, exist_ok=True)
        schema_md_path.write_text("\n".join(schema_lines).strip() + "\n", encoding="utf-8")

        # ----------------------------------------------------------------------
        # 2. 导出 queries.md
        # ----------------------------------------------------------------------
        cursor.execute("SELECT * FROM nl2sql_query_template WHERE status = 1 ORDER BY id ASC;")
        templates = cursor.fetchall()

        queries_lines = [
            "# 特定/常用查询模板 Reference",
            "",
            "本文件记载特定的常用查询模式与复杂指标计算模板，辅助 NL2SQL 生成高质量 Metabase 报表模板。",
            "",
            "---",
            "",
        ]

        idx = 1
        common_notes = ""
        for tpl in templates:
            t_title = tpl["title"]
            t_scen = tpl["scenario"]
            t_tables = tpl["related_tables"]
            t_sql = tpl["sql_template"]
            if tpl["notes"]:
                common_notes = tpl["notes"]

            queries_lines.append(f"## {idx}. {t_title}")
            queries_lines.append("")
            if t_scen:
                queries_lines.append("### 业务场景")
                queries_lines.append(t_scen)
                queries_lines.append("")
            if t_tables:
                queries_lines.append("### 数据源")
                queries_lines.append(f"`{t_tables}`" if not t_tables.startswith("`") else t_tables)
                queries_lines.append("")
            if t_sql:
                queries_lines.append("### SQL 模板")
                queries_lines.append("")
                queries_lines.append("```sql")
                queries_lines.append(t_sql)
                queries_lines.append("```")
                queries_lines.append("")

            queries_lines.append("---")
            queries_lines.append("")
            idx += 1

        if common_notes:
            queries_lines.append(f"## {idx}. 率值计算规范与防错约定")
            queries_lines.append("")
            queries_lines.append(common_notes)
            queries_lines.append("")

        queries_md_path.parent.mkdir(parents=True, exist_ok=True)
        queries_md_path.write_text("\n".join(queries_lines).strip() + "\n", encoding="utf-8")

        print(f"[OK] Successfully exported Markdown reference files from SQLite:")
        print(f"   - {schema_md_path}")
        print(f"   - {queries_md_path}")

    finally:
        conn.close()


if __name__ == "__main__":
    try:
        export_to_md()
    except Exception as e:
        print(f"[ERROR] Export failed: {e}", file=sys.stderr)
        sys.exit(1)

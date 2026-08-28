"""
Markdown 参考文件 (schema.md & queries.md) 到 SQLite 数据库 (nl2sql_meta.db) 的迁移脚本。
自动解析文本格式元数据并写入结构化 SQLite 数据库。
"""

from pathlib import Path
import re
import sqlite3
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "nl2sql_meta.db"
SCHEMA_MD_PATH = BASE_DIR / ".agents" / "skills" / "nl2sql-metabase" / "references" / "schema.md"
QUERIES_MD_PATH = BASE_DIR / ".agents" / "skills" / "nl2sql-metabase" / "references" / "queries.md"
INIT_SCRIPT_PATH = BASE_DIR / "scripts" / "init_sqlite_db.py"


def ensure_db_exists():
    """确保 SQLite 数据库及表结构已建立"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("init_sqlite_db", str(INIT_SCRIPT_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.init_db(DB_PATH)


def parse_schema_md(md_content: str):
    """解析 schema.md 文件，提取板块、数据表元数据、字段字典及示例 SQL"""
    tables = []
    current_domain = "未分类"

    lines = md_content.splitlines()
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].strip()

        # 匹配 ## 业务板块 (如 ## 基础维度表)
        if line.startswith("## ") and not line.startswith("## 表元数据协议说明"):
            current_domain = line[3:].strip()
            i += 1
            continue

        # 匹配 ### 表名 (如 ### dim_lh_basic_team（团队表）)
        if line.startswith("### "):
            header = line[4:].strip()
            table_match = re.match(r"^([a-zA-Z0-9_]+)(?:[（(](.*?)[）)])?", header)
            if table_match:
                table_name = table_match.group(1).strip()

                alias = ""
                use_for = ""
                required_filters = ""
                optional_filters = ""
                columns = []
                examples = []

                i += 1
                # 读取该表块下的内容
                while i < n and not lines[i].strip().startswith("### ") and not lines[i].strip().startswith("## "):
                    cur_line = lines[i].strip()

                    # 解析 alias
                    if cur_line.startswith("- **alias**:") or cur_line.startswith("* **alias**:"):
                        alias = cur_line.split(":", 1)[1].strip().strip("`").strip()

                    # 解析 use_for
                    elif cur_line.startswith("- **use_for**:") or cur_line.startswith("* **use_for** SECONDARY"):
                        use_for_lines = [cur_line.split(":", 1)[1].strip()]
                        i += 1
                        while i < n:
                            next_line = lines[i].rstrip()
                            if next_line.startswith("- **") or next_line.startswith("### ") or next_line.startswith("## ") or next_line.startswith("|") or next_line.startswith("**示例"):
                                i -= 1
                                break
                            if next_line.strip():
                                use_for_lines.append(next_line.strip())
                            i += 1
                        use_for = "\n".join(use_for_lines).strip()

                    # 解析 required_filters 代码块
                    elif cur_line.startswith("- **required_filters**:") or cur_line.startswith("* **required_filters**:"):
                        req_lines = []
                        i += 1
                        if i < n and lines[i].strip().startswith("```"):
                            i += 1
                            while i < n and not lines[i].strip().startswith("```"):
                                req_lines.append(lines[i])
                                i += 1
                        required_filters = "\n".join(req_lines).strip()

                    # 解析 optional_filters 代码块
                    elif cur_line.startswith("- **optional_filters**:") or cur_line.startswith("* **optional_filters**:"):
                        opt_lines = []
                        i += 1
                        if i < n and lines[i].strip().startswith("```"):
                            i += 1
                            while i < n and not lines[i].strip().startswith("```"):
                                opt_lines.append(lines[i])
                                i += 1
                        optional_filters = "\n".join(opt_lines).strip()

                    # 解析 Markdown 表格 (字段列表)
                    elif cur_line.startswith("|") and "字段" in cur_line:
                        # 跳过表头和分隔线
                        i += 2
                        sort_order = 1
                        while i < n and lines[i].strip().startswith("|"):
                            row_str = lines[i].strip()
                            parts = [p.strip() for p in row_str.split("|")[1:-1]]
                            if len(parts) >= 3:
                                col_name = parts[0].strip("` ")
                                col_type = parts[1].strip()
                                col_comment = parts[2].strip()

                                is_pk = 1 if ("PK" in col_comment or col_name == "id") else 0
                                ref_table = None
                                ref_column = None
                                is_fk = 0

                                # 提取外键关联提示，例如: → dim_lh_teaching_class_term.id
                                fk_match = re.search(r"→\s*([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)", col_comment)
                                if fk_match:
                                    ref_table = fk_match.group(1)
                                    ref_column = fk_match.group(2)
                                    is_fk = 1

                                columns.append({
                                    "column_name": col_name,
                                    "data_type": col_type,
                                    "column_comment": col_comment,
                                    "ref_table_name": ref_table,
                                    "ref_column_name": ref_column,
                                    "is_pk": is_pk,
                                    "is_fk": is_fk,
                                    "sort_order": sort_order,
                                })
                                sort_order += 1
                            i += 1
                        i -= 1

                    # 解析示例 SQL (如 **示例 1：查询某团队所有营期列表**)
                    elif cur_line.startswith("**示例"):
                        ex_title = cur_line.strip("*").strip()
                        ex_sql_lines = []
                        i += 1
                        if i < n and lines[i].strip().startswith("```"):
                            i += 1
                            while i < n and not lines[i].strip().startswith("```"):
                                ex_sql_lines.append(lines[i])
                                i += 1
                        examples.append({
                            "example_name": ex_title,
                            "sql_content": "\n".join(ex_sql_lines).strip(),
                            "description": "",
                            "sort_order": len(examples) + 1,
                        })

                    i += 1

                tables.append({
                    "table_name": table_name,
                    "db_name": "warehouse",
                    "table_alias": alias,
                    "domain": current_domain,
                    "use_for": use_for,
                    "required_filters": required_filters,
                    "optional_filters": optional_filters,
                    "columns": columns,
                    "examples": examples,
                })
                continue
        i += 1

    return tables


def parse_queries_md(md_content: str):
    """解析 queries.md 文件，提取常用/特定查询模板"""
    templates = []
    sections = re.split(r"\n(?=## )", md_content)

    notes = ""

    for sec in sections:
        sec_str = sec.strip()
        if not sec_str.startswith("## "):
            continue

        first_line = sec_str.splitlines()[0]
        # 排除防错约定全局块
        if "率值计算规范" in first_line or "防错约定" in first_line:
            notes = sec_str
            continue

        title = re.sub(r"^##\s*\d+\.\s*", "", first_line).strip()

        # 提取业务场景
        scen_match = re.search(r"### 业务场景\s*\n([\s\S]*?)(?=\n###|\Z)", sec_str)
        scenario = scen_match.group(1).strip() if scen_match else ""

        # 提取数据源
        src_match = re.search(r"### 数据源\s*\n([\s\S]*?)(?=\n###|\Z)", sec_str)
        related_tables = src_match.group(1).strip() if src_match else ""

        # 提取 SQL 模板代码块
        sql_match = re.search(r"```sql\s*\n([\s\S]*?)\n```", sec_str)
        sql_template = sql_match.group(1).strip() if sql_match else ""

        if title and sql_template:
            templates.append({
                "title": title,
                "category": "特定/常用查询",
                "scenario": scenario,
                "related_tables": related_tables,
                "sql_template": sql_template,
                "notes": "",
            })

    if notes:
        for t in templates:
            t["notes"] = notes

    return templates


def migrate():
    """执行从 Markdown 到 SQLite 的解析与导入"""
    ensure_db_exists()

    if not SCHEMA_MD_PATH.exists():
        print(f"⚠️ {SCHEMA_MD_PATH} not found, skipping schema migration.")
        parsed_tables = []
    else:
        schema_text = SCHEMA_MD_PATH.read_text(encoding="utf-8")
        parsed_tables = parse_schema_md(schema_text)

    if not QUERIES_MD_PATH.exists():
        print(f"⚠️ {QUERIES_MD_PATH} not found, skipping queries migration.")
        parsed_templates = []
    else:
        queries_text = QUERIES_MD_PATH.read_text(encoding="utf-8")
        parsed_templates = parse_queries_md(queries_text)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    try:
        # 1. 迁移表元数据及关联结构
        for tbl in parsed_tables:
            cursor.execute("""
                INSERT INTO nl2sql_table_meta (db_name, table_name, table_alias, domain, use_for, required_filters, optional_filters, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(table_name) DO UPDATE SET
                    db_name=excluded.db_name,
                    table_alias=excluded.table_alias,
                    domain=excluded.domain,
                    use_for=excluded.use_for,
                    required_filters=excluded.required_filters,
                    optional_filters=excluded.optional_filters,
                    updated_at=CURRENT_TIMESTAMP;
            """, (tbl["db_name"], tbl["table_name"], tbl["table_alias"], tbl["domain"], tbl["use_for"], tbl["required_filters"], tbl["optional_filters"]))

            cursor.execute("SELECT id FROM nl2sql_table_meta WHERE table_name = ?", (tbl["table_name"],))
            table_id = cursor.fetchone()[0]

            # 插入/更新字段字典
            for col in tbl["columns"]:
                cursor.execute("""
                    INSERT INTO nl2sql_column_meta (table_id, column_name, data_type, column_comment, ref_table_name, ref_column_name, is_pk, is_fk, sort_order, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(table_id, column_name) DO UPDATE SET
                        data_type=excluded.data_type,
                        column_comment=excluded.column_comment,
                        ref_table_name=excluded.ref_table_name,
                        ref_column_name=excluded.ref_column_name,
                        is_pk=excluded.is_pk,
                        is_fk=excluded.is_fk,
                        sort_order=excluded.sort_order,
                        updated_at=CURRENT_TIMESTAMP;
                """, (table_id, col["column_name"], col["data_type"], col["column_comment"], col["ref_table_name"], col["ref_column_name"], col["is_pk"], col["is_fk"], col["sort_order"]))

            # 替换插入示例 SQL
            cursor.execute("DELETE FROM nl2sql_table_example WHERE table_id = ?", (table_id,))
            for ex in tbl["examples"]:
                cursor.execute("""
                    INSERT INTO nl2sql_table_example (table_id, example_name, sql_content, description, sort_order, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
                """, (table_id, ex["example_name"], ex["sql_content"], ex["description"], ex["sort_order"]))

        # 2. 迁移特定/常用查询模板
        for tpl in parsed_templates:
            cursor.execute("""
                INSERT INTO nl2sql_query_template (title, category, scenario, related_tables, sql_template, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(title) DO UPDATE SET
                    category=excluded.category,
                    scenario=excluded.scenario,
                    related_tables=excluded.related_tables,
                    sql_template=excluded.sql_template,
                    notes=excluded.notes,
                    updated_at=CURRENT_TIMESTAMP;
            """, (tpl["title"], tpl["category"], tpl["scenario"], tpl["related_tables"], tpl["sql_template"], tpl["notes"]))

        conn.commit()
        print(f"[OK] Successfully migrated {len(parsed_tables)} table schemas and {len(parsed_templates)} query templates to SQLite: {DB_PATH}")

    finally:
        conn.close()


if __name__ == "__main__":
    try:
        migrate()
    except Exception as e:
        print(f"[ERROR] Migration failed: {e}", file=sys.stderr)
        sys.exit(1)

"""
nl2sql_meta.py — SQLite 配置元数据访问与维护工具模块
专门管理 NL2SQL 规则所使用的本地 SQLite 配置数据库 (data/nl2sql_meta.db)。
对 SQLite 的任何变更（新增、修改、删除）均会自动同步刷新 references/ 下的 Markdown 文件。
"""

from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "nl2sql_meta.db"


def get_db_conn(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """获取 SQLite 数据库连接，默认开启 dict 属性访问与外键支持"""
    target_path = db_path or DEFAULT_DB_PATH
    if not target_path.exists():
        # 如果不存在，尝试调用初始化
        from scripts.init_sqlite_db import init_db
        init_db(target_path)

    conn = sqlite3.connect(str(target_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _auto_sync_md():
    """在保存/修改 SQLite 配置后自动触发同步导出到 references/*.md 参考文件"""
    try:
        from scripts.export_sqlite_to_md import export_to_md
        export_to_md()
    except Exception as e:
        print(f"[WARN] Auto sync markdown failed: {e}")


# ------------------------------------------------------------------------------
# 1. 表级元数据 API
# ------------------------------------------------------------------------------

def get_all_domains() -> List[str]:
    """获取所有已注册的业务板块领域"""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT domain FROM nl2sql_table_meta ORDER BY id;")
        return [row["domain"] for row in cursor.fetchall()]


def get_all_table_metas(domain: Optional[str] = None) -> List[Dict[str, Any]]:
    """查询表元数据列表"""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        if domain:
            cursor.execute("""
                SELECT * FROM nl2sql_table_meta
                WHERE domain = ? AND status = 1
                ORDER BY id ASC;
            """, (domain,))
        else:
            cursor.execute("""
                SELECT * FROM nl2sql_table_meta
                ORDER BY id ASC;
            """)
        return [dict(row) for row in cursor.fetchall()]


def get_table_detail(table_id_or_name: Any) -> Optional[Dict[str, Any]]:
    """查询指定表的完整详情（含字段字典与 SQL 示例）"""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        if isinstance(table_id_or_name, int) or (isinstance(table_id_or_name, str) and table_id_or_name.isdigit()):
            cursor.execute("SELECT * FROM nl2sql_table_meta WHERE id = ?;", (int(table_id_or_name),))
        else:
            cursor.execute("SELECT * FROM nl2sql_table_meta WHERE table_name = ?;", (str(table_id_or_name),))

        row = cursor.fetchone()
        if not row:
            return None

        tbl_dict = dict(row)
        table_id = tbl_dict["id"]

        # 查询字段字典
        cursor.execute("""
            SELECT * FROM nl2sql_column_meta
            WHERE table_id = ?
            ORDER BY sort_order ASC, id ASC;
        """, (table_id,))
        tbl_dict["columns"] = [dict(c) for c in cursor.fetchall()]

        # 查询典型示例
        cursor.execute("""
            SELECT * FROM nl2sql_table_example
            WHERE table_id = ?
            ORDER BY sort_order ASC, id ASC;
        """, (table_id,))
        tbl_dict["examples"] = [dict(ex) for ex in cursor.fetchall()]

        return tbl_dict


def save_table_meta(table_data: Dict[str, Any]) -> int:
    """新增或更新表级元数据，并自动同步导出 Markdown"""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        table_id = table_data.get("id")

        if table_id:
            cursor.execute("""
                UPDATE nl2sql_table_meta
                SET db_name = ?,
                    table_name = ?,
                    table_alias = ?,
                    domain = ?,
                    use_for = ?,
                    required_filters = ?,
                    optional_filters = ?,
                    status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
            """, (
                table_data.get("db_name", "warehouse"),
                table_data["table_name"],
                table_data["table_alias"],
                table_data.get("domain", "未分类"),
                table_data.get("use_for", ""),
                table_data.get("required_filters", ""),
                table_data.get("optional_filters", ""),
                table_data.get("status", 1),
                table_id,
            ))
            res_id = table_id
        else:
            cursor.execute("""
                INSERT INTO nl2sql_table_meta (db_name, table_name, table_alias, domain, use_for, required_filters, optional_filters, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                table_data.get("db_name", "warehouse"),
                table_data["table_name"],
                table_data["table_alias"],
                table_data.get("domain", "未分类"),
                table_data.get("use_for", ""),
                table_data.get("required_filters", ""),
                table_data.get("optional_filters", ""),
                table_data.get("status", 1),
            ))
            conn.commit()
            res_id = cursor.lastrowid

    _auto_sync_md()
    return res_id


def delete_table_meta(table_id: int):
    """删除指定表元数据（级联删除字段与示例），并自动同步导出 Markdown"""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM nl2sql_table_meta WHERE id = ?;", (table_id,))
        conn.commit()
    _auto_sync_md()


# ------------------------------------------------------------------------------
# 2. 字段字典 API
# ------------------------------------------------------------------------------

def save_column_meta(col_data: Dict[str, Any]) -> int:
    """新增或更新单个字段属性，并自动同步导出 Markdown"""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        col_id = col_data.get("id")

        if col_id:
            cursor.execute("""
                UPDATE nl2sql_column_meta
                SET column_name = ?,
                    data_type = ?,
                    column_comment = ?,
                    ref_table_name = ?,
                    ref_column_name = ?,
                    is_pk = ?,
                    is_fk = ?,
                    sort_order = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
            """, (
                col_data["column_name"],
                col_data.get("data_type", "varchar"),
                col_data.get("column_comment", ""),
                col_data.get("ref_table_name"),
                col_data.get("ref_column_name"),
                col_data.get("is_pk", 0),
                col_data.get("is_fk", 0),
                col_data.get("sort_order", 0),
                col_id,
            ))
            res_id = col_id
        else:
            cursor.execute("""
                INSERT INTO nl2sql_column_meta (table_id, column_name, data_type, column_comment, ref_table_name, ref_column_name, is_pk, is_fk, sort_order)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                col_data["table_id"],
                col_data["column_name"],
                col_data.get("data_type", "varchar"),
                col_data.get("column_comment", ""),
                col_data.get("ref_table_name"),
                col_data.get("ref_column_name"),
                col_data.get("is_pk", 0),
                col_data.get("is_fk", 0),
                col_data.get("sort_order", 0),
            ))
            conn.commit()
            res_id = cursor.lastrowid

    _auto_sync_md()
    return res_id


def delete_column_meta(col_id: int):
    """删除字段，并自动同步导出 Markdown"""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM nl2sql_column_meta WHERE id = ?;", (col_id,))
        conn.commit()
    _auto_sync_md()


# ------------------------------------------------------------------------------
# 3. 表典型 SQL 示例 API
# ------------------------------------------------------------------------------

def save_table_example(ex_data: Dict[str, Any]) -> int:
    """保存表 SQL 示例，并自动同步导出 Markdown"""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        ex_id = ex_data.get("id")

        if ex_id:
            cursor.execute("""
                UPDATE nl2sql_table_example
                SET example_name = ?,
                    sql_content = ?,
                    description = ?,
                    sort_order = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
            """, (
                ex_data["example_name"],
                ex_data["sql_content"],
                ex_data.get("description", ""),
                ex_data.get("sort_order", 0),
                ex_id,
            ))
            res_id = ex_id
        else:
            cursor.execute("""
                INSERT INTO nl2sql_table_example (table_id, example_name, sql_content, description, sort_order)
                VALUES (?, ?, ?, ?, ?);
            """, (
                ex_data["table_id"],
                ex_data["example_name"],
                ex_data["sql_content"],
                ex_data.get("description", ""),
                ex_data.get("sort_order", 0),
            ))
            conn.commit()
            res_id = cursor.lastrowid

    _auto_sync_md()
    return res_id


def delete_table_example(ex_id: int):
    """删除 SQL 示例，并自动同步导出 Markdown"""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM nl2sql_table_example WHERE id = ?;", (ex_id,))
        conn.commit()
    _auto_sync_md()


# ------------------------------------------------------------------------------
# 4. 常用/特定查询模板 API
# ------------------------------------------------------------------------------

def get_all_query_templates() -> List[Dict[str, Any]]:
    """获取所有常用查询模板"""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM nl2sql_query_template ORDER BY id ASC;")
        return [dict(row) for row in cursor.fetchall()]


def save_query_template(tpl_data: Dict[str, Any]) -> int:
    """新增或更新查询模板，并自动同步导出 Markdown"""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        tpl_id = tpl_data.get("id")

        if tpl_id:
            cursor.execute("""
                UPDATE nl2sql_query_template
                SET title = ?,
                    category = ?,
                    scenario = ?,
                    related_tables = ?,
                    sql_template = ?,
                    notes = ?,
                    status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
            """, (
                tpl_data["title"],
                tpl_data.get("category", "常用查询"),
                tpl_data.get("scenario", ""),
                tpl_data.get("related_tables", ""),
                tpl_data["sql_template"],
                tpl_data.get("notes", ""),
                tpl_data.get("status", 1),
                tpl_id,
            ))
            res_id = tpl_id
        else:
            cursor.execute("""
                INSERT INTO nl2sql_query_template (title, category, scenario, related_tables, sql_template, notes, status)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (
                tpl_data["title"],
                tpl_data.get("category", "常用查询"),
                tpl_data.get("scenario", ""),
                tpl_data.get("related_tables", ""),
                tpl_data["sql_template"],
                tpl_data.get("notes", ""),
                tpl_data.get("status", 1),
            ))
            conn.commit()
            res_id = cursor.lastrowid

    _auto_sync_md()
    return res_id


def delete_query_template(tpl_id: int):
    """删除查询模板，并自动同步导出 Markdown"""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM nl2sql_query_template WHERE id = ?;", (tpl_id,))
        conn.commit()
    _auto_sync_md()

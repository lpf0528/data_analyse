"""
NL2SQL 配置元数据管理页面 (SQLite 本地存储)
采用 Streamlit 弹窗 (st.dialog) 提供数据表与常用查询模板的列表列操作、新增与全功能编辑。
"""

from pathlib import Path
import pandas as pd
import streamlit as st

import importlib
import utils.nl2sql_meta
importlib.reload(utils.nl2sql_meta)

from utils.nl2sql_meta import (
    delete_column_meta,
    delete_query_template,
    delete_table_example,
    delete_table_meta,
    get_all_domains,
    get_all_query_templates,
    get_all_table_metas,
    get_table_detail,
    save_column_meta,
    save_query_template,
    save_table_example,
    save_table_meta,
)

import utils.query
importlib.reload(utils.query)
from utils.query import get_registered_databases




BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "data" / "nl2sql_meta.db"
SCHEMA_SQL_PATH = BASE_DIR / "scripts" / "schema_sqlite.sql"

st.title("NL2SQL 配置元数据管理")
st.caption("管理保存在 SQLite 本地数据库中的表元数据、字段字典与 Metabase SQL 查询模板。变更可一键同步导出至 Markdown。")

# 顶栏右侧：一键发布同步至 Markdown 按钮
col_head1, col_head2 = st.columns([3, 1], vertical_alignment="bottom")
with col_head2:
    if st.button("同步导出至 Markdown", type="primary", key="btn_sync_md"):
        try:
            from scripts.export_sqlite_to_md import export_to_md
            export_to_md()
            st.success("已成功将 SQLite 最新配置同步导出至 references/ 目录下！")
        except Exception as e:
            st.error(f"导出 Markdown 失败: {e}")

# ==============================================================================
# 弹窗定义 (ST.DIALOG)
# ==============================================================================

@st.dialog("新增数据表", width="large")
def modal_add_table():
    with st.form("form_modal_add_table"):
        c1, c2, c3 = st.columns([2, 2, 2])
        with c1:
            new_table_name = st.text_input("表名 (table_name)*", placeholder="dim_lh_sample")
        with c2:
            new_db_name = st.selectbox("目标数据库 (db_name)", options=get_registered_databases(), index=0)
        with c3:
            new_domain = st.text_input("所属板块 (domain)", value="基础维度表")

        new_use_for = st.text_area("业务场景说明 (use_for)", placeholder="用于表选择决断...", height=100)
        new_req_filters = st.text_area("强制 WHERE 条件 (required_filters)", placeholder="AND `s`.`tid` = {{tid}}", height=80)
        new_opt_filters = st.text_area("可选 WHERE 条件 (optional_filters)", placeholder="[[ AND `s`.`status` = {{status}} ]]", height=80)

        if st.form_submit_button("保存新增数据表", type="primary"):
            if not new_table_name:
                st.error("表名不能为空！")
            else:
                try:
                    save_table_meta({
                        "db_name": new_db_name.strip(),
                        "table_name": new_table_name.strip(),
                        "domain": new_domain.strip(),
                        "use_for": new_use_for.strip(),
                        "required_filters": new_req_filters.strip(),
                        "optional_filters": new_opt_filters.strip(),
                    })
                    st.success(f"已新建数据表: {new_table_name}")
                    st.rerun()
                except Exception as e:
                    st.error(f"新建表失败: {e}")


@st.dialog("编辑数据表与字段字典", width="large")
def modal_edit_table(table_id: int):
    table_detail = get_table_detail(table_id)
    if not table_detail:
        st.error("未找到数据表信息！")
        return

    st.subheader(f"表: `{table_detail['table_name']}` (数据库: `{table_detail.get('db_name', 'warehouse')}` | 板块: `{table_detail['domain']}`)")

    dlg_tab1, dlg_tab2, dlg_tab3 = st.tabs(["基本元信息", "字段字典列表", "典型 SQL 示例"])

    # 1. 基本元信息
    with dlg_tab1:
        with st.form(f"form_dlg_edit_table_{table_id}"):
            c1, c2, c3 = st.columns([2, 2, 2])
            with c1:
                edit_name = st.text_input("表名", value=table_detail["table_name"])
            with c2:
                db_opts = get_registered_databases()
                curr_db = table_detail.get("db_name", "warehouse")
                db_idx = db_opts.index(curr_db) if curr_db in db_opts else 0
                edit_db_name = st.selectbox("目标数据库", options=db_opts, index=db_idx)
            with c3:
                edit_domain = st.text_input("所属板块", value=table_detail["domain"])

            edit_use_for = st.text_area("业务场景说明 (use_for)", value=table_detail["use_for"], height=100)
            edit_req_filters = st.text_area("强制条件 (required_filters)", value=table_detail["required_filters"], height=80)
            edit_opt_filters = st.text_area("可选条件 (optional_filters)", value=table_detail["optional_filters"], height=80)

            c_b1, c_b2 = st.columns([1, 1])
            with c_b1:
                submit_save = st.form_submit_button("保存更新表信息", type="primary")
            with c_b2:
                submit_del = st.form_submit_button("删除此表")

            if submit_save:
                save_table_meta({
                    "id": table_detail["id"],
                    "db_name": edit_db_name.strip(),
                    "table_name": edit_name.strip(),
                    "domain": edit_domain.strip(),
                    "use_for": edit_use_for.strip(),
                    "required_filters": edit_req_filters.strip(),
                    "optional_filters": edit_opt_filters.strip(),
                })
                st.success("更新表元信息成功！")
                st.rerun()


            if submit_del:
                delete_table_meta(table_detail["id"])
                st.warning(f"已删除数据表 {table_detail['table_name']}")
                st.rerun()

    # 2. 字段字典管理
    with dlg_tab2:
        cols_data = table_detail.get("columns", [])
        st.markdown(f"**关联字段共 {len(cols_data)} 个** (可在表格中直接编辑)")

        if cols_data:
            edited_df = st.data_editor(
                cols_data,
                column_config={
                    "id": None,
                    "table_id": None,
                    "created_at": None,
                    "updated_at": None,
                    "column_name": st.column_config.TextColumn("字段名", required=True),
                    "data_type": st.column_config.TextColumn("数据类型"),
                    "column_comment": st.column_config.TextColumn("字段说明/注释", width="large"),
                    "is_pk": st.column_config.CheckboxColumn("PK"),
                    "is_fk": st.column_config.CheckboxColumn("FK"),
                    "ref_table_name": st.column_config.TextColumn("关联表"),
                    "ref_column_name": st.column_config.TextColumn("关联字段"),
                    "sort_order": st.column_config.NumberColumn("排序", width="small"),
                },
                hide_index=True,
                key=f"dlg_editor_cols_{table_id}",
            )

            if st.button("保存字段字典修改", key=f"dlg_btn_save_cols_{table_id}", type="primary"):
                try:
                    for row in edited_df:
                        save_column_meta(row)
                    st.success("字段字典批量更新成功！")
                    st.rerun()
                except Exception as e:
                    st.error(f"保存字段失败: {e}")

        # 新增字段表单
        with st.popover("➕ 添加新字段"):
            with st.form(f"dlg_form_add_col_{table_id}"):
                fc1, fc2 = st.columns(2)
                with fc1:
                    add_cname = st.text_input("字段名*", placeholder="status")
                with fc2:
                    add_ctype = st.text_input("数据类型", value="varchar")
                add_ccomment = st.text_input("字段说明", placeholder="状态枚举...")
                if st.form_submit_button("添加字段"):
                    if add_cname:
                        save_column_meta({
                            "table_id": table_id,
                            "column_name": add_cname.strip(),
                            "data_type": add_ctype.strip(),
                            "column_comment": add_ccomment.strip(),
                            "sort_order": len(cols_data) + 1,
                        })
                        st.success("添加字段成功！")
                        st.rerun()

    # 3. 典型 SQL 示例
    with dlg_tab3:
        for ex in table_detail.get("examples", []):
            with st.expander(f"📌 {ex['example_name']}", expanded=False):
                st.code(ex["sql_content"], language="sql")
                if st.button("删除该示例", key=f"dlg_btn_del_ex_{ex['id']}"):
                    delete_table_example(ex["id"])
                    st.warning("已删除示例")
                    st.rerun()

        with st.popover("➕ 新增 SQL 示例"):
            with st.form(f"dlg_form_add_ex_{table_id}"):
                ex_name = st.text_input("示例名称*", value="示例 N：...")
                ex_sql = st.text_area("SQL 内容*", height=150)
                if st.form_submit_button("保存示例"):
                    if ex_name and ex_sql:
                        save_table_example({
                            "table_id": table_id,
                            "example_name": ex_name.strip(),
                            "sql_content": ex_sql.strip(),
                            "sort_order": len(table_detail.get("examples", [])) + 1,
                        })
                        st.success("保存示例成功！")
                        st.rerun()


@st.dialog("新增常用查询模板", width="large")
def modal_add_template():
    with st.form("form_modal_add_tpl"):
        t1, t2 = st.columns(2)
        with t1:
            new_t_title = st.text_input("模板标题*", placeholder="营期班级最新周基数查询")
        with t2:
            new_t_cat = st.text_input("场景分类", value="特定/常用查询")

        new_t_scen = st.text_area("业务场景说明", placeholder="在分析营期维度数据时...", height=80)
        new_t_tbls = st.text_input("涉及数据源表", placeholder="dws_lh_teaching_term_class_week")
        new_t_sql = st.text_area("SQL 模板代码*", placeholder="WITH latest_term_class_week AS ( ... )", height=200)
        new_t_notes = st.text_area("规范与防错约定", placeholder="1. 除零保护...", height=80)

        if st.form_submit_button("保存新增模板", type="primary"):
            if not new_t_title or not new_t_sql:
                st.error("标题与 SQL 模板为必填项！")
            else:
                try:
                    save_query_template({
                        "title": new_t_title.strip(),
                        "category": new_t_cat.strip(),
                        "scenario": new_t_scen.strip(),
                        "related_tables": new_t_tbls.strip(),
                        "sql_template": new_t_sql.strip(),
                        "notes": new_t_notes.strip(),
                    })
                    st.success("新建查询模板成功！")
                    st.rerun()
                except Exception as e:
                    st.error(f"新增模板失败: {e}")


@st.dialog("编辑常用查询模板", width="large")
def modal_edit_template(template_id: int):
    templates = get_all_query_templates()
    tpl_info = next((t for t in templates if t["id"] == template_id), None)
    if not tpl_info:
        st.error("未找到查询模板！")
        return

    st.subheader(f"模板: `{tpl_info['title']}` ({tpl_info['category']})")

    with st.form(f"form_modal_edit_tpl_{template_id}"):
        et1, et2 = st.columns(2)
        with et1:
            edit_t_title = st.text_input("模板标题", value=tpl_info["title"])
        with et2:
            edit_t_cat = st.text_input("分类", value=tpl_info["category"])

        edit_t_scen = st.text_area("业务场景说明", value=tpl_info["scenario"], height=80)
        edit_t_tbls = st.text_input("涉及数据源", value=tpl_info["related_tables"])
        edit_t_sql = st.text_area("SQL 模板内容", value=tpl_info["sql_template"], height=220)
        edit_t_notes = st.text_area("防错约定与说明", value=tpl_info["notes"], height=80)

        tb_c1, tb_c2 = st.columns(2)
        with tb_c1:
            save_tpl_sub = st.form_submit_button("保存更新模板", type="primary")
        with tb_c2:
            del_tpl_sub = st.form_submit_button("删除此模板")

        if save_tpl_sub:
            save_query_template({
                "id": tpl_info["id"],
                "title": edit_t_title.strip(),
                "category": edit_t_cat.strip(),
                "scenario": edit_t_scen.strip(),
                "related_tables": edit_t_tbls.strip(),
                "sql_template": edit_t_sql.strip(),
                "notes": edit_t_notes.strip(),
            })
            st.success("更新模板成功！")
            st.rerun()

        if del_tpl_sub:
            delete_query_template(template_id)
            st.warning("已删除该模板")
            st.rerun()


# ==============================================================================
# MAIN TABS LAYOUT
# ==============================================================================

tab_tables, tab_templates, tab_ddl = st.tabs(["数据表与字段字典", "常用查询模板", "SQLite 建表 DDL 与状态"])

# ------------------------------------------------------------------------------
# TAB 1: 数据表与字段字典管理
# ------------------------------------------------------------------------------
with tab_tables:
    db_options = ["全部"] + get_registered_databases()
    col_t1, col_t2, col_t3 = st.columns([3, 2, 1], vertical_alignment="center")

    with col_t2:
        selected_db_filter = st.selectbox("筛选数据库", options=db_options, index=0, key="tbl_db_filter")
        filter_db = None if selected_db_filter == "全部" else selected_db_filter

    table_metas = get_all_table_metas(db_name=filter_db)

    with col_t1:
        st.subheader(f"📋 已配置数据表列表 (共 {len(table_metas)} 张)")
    with col_t3:
        if st.button("➕ 新增数据表", type="primary", key="btn_open_add_table"):
            modal_add_table()

    # 以带操作列的卡片/行列表形式展示
    for idx, t in enumerate(table_metas, start=1):
        detail = get_table_detail(t["id"])
        col_count = len(detail.get("columns", [])) if detail else 0
        ex_count = len(detail.get("examples", [])) if detail else 0

        with st.container(border=True):
            r1, r2, r3 = st.columns([6, 3, 1], vertical_alignment="center")
            with r1:
                db_badge = t.get('db_name', 'warehouse')
                st.markdown(f"**{idx}. `{t['table_name']}`** `[{db_badge}]` (板块: `{t['domain']}`)")
                scen_text = t['use_for'].replace('\n', ' ')
                if len(scen_text) > 80:
                    scen_text = scen_text[:80] + "..."
                st.caption(f"场景: {scen_text}")

            with r2:
                st.caption(f"字段数: **{col_count}** | 示例数: **{ex_count}**")
                req_text = t['required_filters'].replace('\n', ' ') if t['required_filters'] else "无"
                st.caption(f"强制条件: `{req_text}`")
            with r3:
                if st.button("✏️ 编辑", key=f"btn_edit_tbl_{t['id']}"):
                    modal_edit_table(t["id"])

# ------------------------------------------------------------------------------
# TAB 2: 常用查询模板管理
# ------------------------------------------------------------------------------
with tab_templates:
    col_q1, col_q2 = st.columns([3, 1], vertical_alignment="center")
    templates = get_all_query_templates()

    with col_q1:
        st.subheader(f"📋 已配置常用查询模板列表 (共 {len(templates)} 个)")
    with col_q2:
        if st.button("➕ 新增查询模板", type="primary", key="btn_open_add_tpl"):
            modal_add_template()

    # 以带操作列的行列表形式展示
    for idx, tpl in enumerate(templates, start=1):
        with st.container(border=True):
            r1, r2, r3 = st.columns([6, 3, 1], vertical_alignment="center")
            with r1:
                st.markdown(f"**{idx}. {tpl['title']}** ({tpl['category']})")
                scen_text = tpl['scenario'].replace('\n', ' ')
                if len(scen_text) > 80:
                    scen_text = scen_text[:80] + "..."
                st.caption(f"场景: {scen_text}")
            with r2:
                tbl_text = tpl['related_tables'] if tpl['related_tables'] else "未限定"
                st.caption(f"涉及数据源: `{tbl_text}`")
                st.caption(f"防错约定: {'已配置' if tpl['notes'] else '无'}")
            with r3:
                if st.button("✏️ 编辑", key=f"btn_edit_tpl_{tpl['id']}"):
                    modal_edit_template(tpl["id"])

# ------------------------------------------------------------------------------
# TAB 3: SQLite 数据库状态 & DDL 建表定义
# ------------------------------------------------------------------------------
with tab_ddl:
    st.subheader("SQLite 数据库文件信息")
    if DB_PATH.exists():
        size_kb = DB_PATH.stat().st_size / 1024
        st.success(f"📂 数据库文件路径: `{DB_PATH}` (文件大小: {size_kb:.2f} KB)")
    else:
        st.warning("⚠️ 数据库文件尚未生成，点击下方按钮尝试初始化。")
        if st.button("初始化创建 SQLite 数据库"):
            from scripts.init_sqlite_db import init_db
            init_db()
            st.rerun()

    st.subheader("建表 SQL 定义 (scripts/schema_sqlite.sql)")
    if SCHEMA_SQL_PATH.exists():
        ddl_text = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
        st.code(ddl_text, language="sql")
    else:
        st.error(f"未找到建表定义文件: {SCHEMA_SQL_PATH}")

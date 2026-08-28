"""
NL2SQL 配置元数据管理页面 (SQLite 本地存储)
允许 Admin 角色可视化管理表结构、字段字典、模板查询，并支持一键发布导出至 Markdown 文件。
"""

from pathlib import Path
import pandas as pd
import streamlit as st

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
            st.success("✅ 已成功将 SQLite 最新配置同步导出至 references/ 目录下！")
        except Exception as e:
            st.error(f"❌ 导出 Markdown 失败: {e}")

tab_tables, tab_templates, tab_ddl = st.tabs(["数据表与字段字典", "常用查询模板", "SQLite 建表 DDL 与状态"])

# ==============================================================================
# TAB 1: 数据表与字段字典管理
# ==============================================================================
with tab_tables:
    table_metas = get_all_table_metas()

    # 1.1 列表形式展示所有已配置的数据表概览
    st.subheader(f"📋 已配置数据表列表 (共 {len(table_metas)} 张)")

    overview_rows = []
    for idx, t in enumerate(table_metas, start=1):
        detail = get_table_detail(t["id"])
        col_count = len(detail.get("columns", [])) if detail else 0
        ex_count = len(detail.get("examples", [])) if detail else 0
        overview_rows.append({
            "序号": idx,
            "表名": t["table_name"],
            "别名": t["table_alias"],
            "所属板块": t["domain"],
            "字段数": col_count,
            "示例数": ex_count,
            "必填条件": t["required_filters"].replace("\n", " ") if t["required_filters"] else "无",
            "业务场景说明": t["use_for"].replace("\n", " ")[:60] + ("..." if len(t["use_for"]) > 60 else ""),
        })

    if overview_rows:
        overview_df = pd.DataFrame(overview_rows)
        st.dataframe(
            overview_df,
            column_config={
                "序号": st.column_config.NumberColumn(width="small"),
                "表名": st.column_config.TextColumn(width="medium"),
                "别名": st.column_config.TextColumn(width="small"),
                "所属板块": st.column_config.TextColumn(width="medium"),
                "字段数": st.column_config.NumberColumn(width="small"),
                "示例数": st.column_config.NumberColumn(width="small"),
                "必填条件": st.column_config.TextColumn(width="large"),
                "业务场景说明": st.column_config.TextColumn(width="large"),
            },
            hide_index=True,
        )
    else:
        st.info("暂未配置任何数据表。")

    st.markdown("---")

    # 1.2 数据表表单编辑与详情查看
    st.subheader("🛠️ 查看 / 修改表详情与字段字典")
    table_options = ["(新增数据表...)"] + [f"{t['table_name']} ({t['table_alias']}) - {t['domain']}" for t in table_metas]
    table_map = {f"{t['table_name']} ({t['table_alias']}) - {t['domain']}": t for t in table_metas}

    selected_option = st.selectbox("选择要编辑的数据表", table_options, key="select_tbl_meta")

    if selected_option == "(新增数据表...)":
        st.markdown("#### 新增数据表")
        with st.form("form_add_table"):
            col_a1, col_a2, col_a3 = st.columns(3)
            with col_a1:
                new_table_name = st.text_input("表名 (table_name)*", placeholder="dim_lh_sample")
            with col_a2:
                new_table_alias = st.text_input("推荐别名 (table_alias)*", placeholder="s")
            with col_a3:
                new_domain = st.text_input("所属板块 (domain)", value="基础维度表")

            new_use_for = st.text_area("业务场景说明 (use_for)", placeholder="用于表选择决断...")
            new_req_filters = st.text_area("强制 WHERE 条件 (required_filters)", placeholder="AND `s`.`tid` = {{tid}}")
            new_opt_filters = st.text_area("可选 WHERE 条件 (optional_filters)", placeholder="[[ AND `s`.`status` = {{status}} ]]")

            if st.form_submit_button("保存新增数据表"):
                if not new_table_name or not new_table_alias:
                    st.error("表名与推荐别名不能为空！")
                else:
                    try:
                        save_table_meta({
                            "table_name": new_table_name.strip(),
                            "table_alias": new_table_alias.strip(),
                            "domain": new_domain.strip(),
                            "use_for": new_use_for.strip(),
                            "required_filters": new_req_filters.strip(),
                            "optional_filters": new_opt_filters.strip(),
                        })
                        st.success(f"已新建数据表: {new_table_name}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"新建表失败: {e}")

    else:
        current_tbl_info = table_map[selected_option]
        table_detail = get_table_detail(current_tbl_info["id"])

        if table_detail:
            st.markdown(f"#### 表: `{table_detail['table_name']}` (别名: `{table_detail['table_alias']}` | 板块: `{table_detail['domain']}`)")

            # 基本信息编辑表单
            with st.expander("编辑表基本元信息", expanded=False):
                with st.form(f"form_edit_table_{table_detail['id']}"):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        edit_name = st.text_input("表名", value=table_detail["table_name"])
                    with c2:
                        edit_alias = st.text_input("推荐别名", value=table_detail["table_alias"])
                    with c3:
                        edit_domain = st.text_input("所属板块", value=table_detail["domain"])

                    edit_use_for = st.text_area("业务场景 (use_for)", value=table_detail["use_for"], height=100)
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
                            "table_name": edit_name.strip(),
                            "table_alias": edit_alias.strip(),
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

            # 字段字典展现与维护
            cols_data = table_detail.get("columns", [])
            st.markdown(f"##### 字段字典列表 (共 {len(cols_data)} 个字段)")

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
                    key=f"editor_cols_{table_detail['id']}",
                )

                if st.button("保存字段字典修改", key=f"btn_save_cols_{table_detail['id']}"):
                    try:
                        for row in edited_df:
                            save_column_meta(row)
                        st.success("字段字典批量更新成功！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"保存字段失败: {e}")
            else:
                st.info("暂无字段数据。")

            # 新增字段表单
            with st.popover("添加新字段"):
                with st.form(f"form_add_col_{table_detail['id']}"):
                    fc1, fc2 = st.columns(2)
                    with fc1:
                        add_cname = st.text_input("字段名*", placeholder="status")
                    with fc2:
                        add_ctype = st.text_input("数据类型", value="varchar")
                    add_ccomment = st.text_input("字段说明", placeholder="状态枚举...")
                    if st.form_submit_button("添加字段"):
                        if add_cname:
                            save_column_meta({
                                "table_id": table_detail["id"],
                                "column_name": add_cname.strip(),
                                "data_type": add_ctype.strip(),
                                "column_comment": add_ccomment.strip(),
                                "sort_order": len(cols_data) + 1,
                            })
                            st.success("添加字段成功！")
                            st.rerun()

            # 典型示例 SQL
            st.markdown("##### 典型 SQL 示例")
            for ex in table_detail.get("examples", []):
                with st.expander(f"📌 {ex['example_name']}", expanded=False):
                    st.code(ex["sql_content"], language="sql")
                    if st.button("删除该示例", key=f"btn_del_ex_{ex['id']}"):
                        delete_table_example(ex["id"])
                        st.warning("已删除示例")
                        st.rerun()

            with st.popover("新增 SQL 示例"):
                with st.form(f"form_add_ex_{table_detail['id']}"):
                    ex_name = st.text_input("示例名称*", value="示例 N：...")
                    ex_sql = st.text_area("SQL 内容*", height=150)
                    if st.form_submit_button("保存示例"):
                        if ex_name and ex_sql:
                            save_table_example({
                                "table_id": table_detail["id"],
                                "example_name": ex_name.strip(),
                                "sql_content": ex_sql.strip(),
                                "sort_order": len(table_detail.get("examples", [])) + 1,
                            })
                            st.success("保存示例成功！")
                            st.rerun()

# ==============================================================================
# TAB 2: 常用查询模板管理
# ==============================================================================
with tab_templates:
    templates = get_all_query_templates()

    # 2.1 列表形式展示所有已配置的常用查询模板概览
    st.subheader(f"📋 已配置常用查询模板列表 (共 {len(templates)} 个)")

    tpl_overview_rows = []
    for idx, tpl in enumerate(templates, start=1):
        tpl_overview_rows.append({
            "序号": idx,
            "模板标题": tpl["title"],
            "分类": tpl["category"],
            "涉及数据源表": tpl["related_tables"] if tpl["related_tables"] else "未限定",
            "包含防错约定": "有" if tpl["notes"] else "无",
            "业务场景说明": tpl["scenario"].replace("\n", " ")[:80] + ("..." if len(tpl["scenario"]) > 80 else ""),
        })

    if tpl_overview_rows:
        tpl_df = pd.DataFrame(tpl_overview_rows)
        st.dataframe(
            tpl_df,
            column_config={
                "序号": st.column_config.NumberColumn(width="small"),
                "模板标题": st.column_config.TextColumn(width="medium"),
                "分类": st.column_config.TextColumn(width="medium"),
                "涉及数据源表": st.column_config.TextColumn(width="medium"),
                "包含防错约定": st.column_config.TextColumn(width="small"),
                "业务场景说明": st.column_config.TextColumn(width="large"),
            },
            hide_index=True,
        )
    else:
        st.info("暂未配置任何常用查询模板。")

    st.markdown("---")

    # 2.2 常用查询模板表单编辑与详情查看
    st.subheader("🛠️ 查看 / 修改查询模板详情")

    tpl_options = ["(新增查询模板...)"] + [f"{t['title']} ({t['category']})" for t in templates]
    tpl_map = {f"{t['title']} ({t['category']})": t for t in templates}

    selected_tpl_opt = st.selectbox("选择要编辑的查询模板", tpl_options, key="select_tpl_meta")

    if selected_tpl_opt == "(新增查询模板...)":
        st.markdown("#### 新增查询模板")
        with st.form("form_add_tpl"):
            t1, t2 = st.columns(2)
            with t1:
                new_t_title = st.text_input("模板标题*", placeholder="营期班级最新周基数查询")
            with t2:
                new_t_cat = st.text_input("场景分类", value="特定/常用查询")

            new_t_scen = st.text_area("业务场景说明", placeholder="在分析营期维度数据时...")
            new_t_tbls = st.text_input("涉及数据源表", placeholder="dws_lh_teaching_term_class_week")
            new_t_sql = st.text_area("SQL 模板代码*", placeholder="WITH latest_term_class_week AS ( ... )", height=200)
            new_t_notes = st.text_area("规范与防错约定", placeholder="1. 除零保护...")

            if st.form_submit_button("保存新增模板"):
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

    else:
        tpl_info = tpl_map[selected_tpl_opt]
        st.markdown(f"#### 模板: `{tpl_info['title']}` ({tpl_info['category']})")

        with st.form(f"form_edit_tpl_{tpl_info['id']}"):
            et1, et2 = st.columns(2)
            with et1:
                edit_t_title = st.text_input("模板标题", value=tpl_info["title"])
            with et2:
                edit_t_cat = st.text_input("分类", value=tpl_info["category"])

            edit_t_scen = st.text_area("业务场景说明", value=tpl_info["scenario"], height=80)
            edit_t_tbls = st.text_input("涉及数据源", value=tpl_info["related_tables"])
            edit_t_sql = st.text_area("SQL 模板内容", value=tpl_info["sql_template"], height=250)
            edit_t_notes = st.text_area("防错约定与说明", value=tpl_info["notes"], height=100)

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
                delete_query_template(tpl_info["id"])
                st.warning("已删除该模板")
                st.rerun()

# ==============================================================================
# TAB 3: SQLite 数据库状态 & DDL 建表定义
# ==============================================================================
with tab_ddl:
    st.subheader("SQLite 数据库文件信息")
    if DB_PATH.exists():
        size_kb = DB_PATH.stat().st_size / 1024
        st.success(f"📂 数据库文件路径: `{DB_PATH}` (文件大小: {size_kb:.2f} KB)")
    else:
        st.warning("⚠️ 数据库文件尚未生成，点击下按钮尝试初始化。")
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

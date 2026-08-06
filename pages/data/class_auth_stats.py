"""
班级授权学员数：筛选 → 查询 → 图表+表格。

布局约定见 AGENTS.md「页面结果展示惯例」：
筛选（横向固定宽）→ 查询按钮（右对齐）→ SQL expander → 结果（tabs）。
期次由 FilterSpec.default_first 默认选中第一项；首次进入自动查询一次。
"""
import streamlit as st
from utils.metabase import extract_params, build_sql, format_display_sql
from utils.filters import render_filters

TEMPLATE = """
SELECT
    `s`.`big_class_id`                        AS `class_id`,
    `c`.`class_name`,
    COUNT(DISTINCT NVL(`s`.`account_main_id`, `s`.`account_id`)) AS `authorized_student_num`
FROM `warehouse`.`ods_lh_teaching_lh_teaching_student` `s`
LEFT JOIN `warehouse`.`dwd_lh_classes` `c`
ON `s`.`big_class_id` = `c`.`id`
WHERE 1=1
AND `s`.`tid` = {{tid}}
AND `s`.`camp_id` = {{camp_id}}
AND `s`.`authorization_status` = 'authorized'
AND `s`.`term_id` = {{term_id}}
[[ AND `s`.`big_class_id` IN ({{class_ids}}) ]]
GROUP BY `s`.`big_class_id`, `c`.`class_name`
ORDER BY `authorized_student_num` DESC
"""

# 冻结上次查询条件；改筛选不自动重查，点「查询」或首次进入才更新
_SS_FILTERS = "class_auth_stats_filters"

st.subheader("班级授权学员数")

if not st.session_state.get("tid") or not st.session_state.get("camp_id"):
    st.warning("请先登录")
    st.stop()

conn = st.connection("mysql", type="sql")

# 筛选区由 render_filters 统一渲染（横向固定宽：多选 400 / 其余 200）
# term_id 在 FILTER_REGISTRY 中 default_first=True，默认第一项营期
filter_values = render_filters(conn, extract_params(TEMPLATE))

# 查询按钮右对齐；点击后冻结当前筛选
with st.container(horizontal_alignment="right"):
    if st.button("查询", type="primary"):
        st.session_state[_SS_FILTERS] = filter_values

# 首次进入：用当前默认筛选自动查一次（之后仅点「查询」才刷新）
if _SS_FILTERS not in st.session_state:
    st.session_state[_SS_FILTERS] = filter_values

saved_filters = st.session_state[_SS_FILTERS]
if not saved_filters.get("term_id"):
    st.warning("请先选择期次")
    st.stop()

sql, sa_params = build_sql(TEMPLATE, saved_filters)

# 先展示 SQL，再 spinner/结果，避免查询中看不到 SQL
with st.expander("执行的 SQL", expanded=False):
    st.code(format_display_sql(sql, sa_params), language="sql")

with st.spinner("查询中..."):
    df = conn.query(sql, params=sa_params, ttl=0)

tab_chart, tab_table = st.tabs(["图表", "表格"])

with tab_chart:
    st.bar_chart(
        df.set_index("class_name")["authorized_student_num"],
        x_label="班级",
        y_label="授权学员数",
    )

with tab_table:
    # 禁止 use_container_width；用 width="stretch"；隐藏默认行号
    st.dataframe(df, width="stretch", hide_index=True)

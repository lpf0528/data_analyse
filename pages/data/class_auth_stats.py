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

st.title("班级授权学员数")

if not st.session_state.get("tid") or not st.session_state.get("camp_id"):
    st.warning("请先登录")
    st.stop()

conn = st.connection("mysql", type="sql")

filter_values = render_filters(conn, extract_params(TEMPLATE))

if st.button("查询", type="primary"):
    if not filter_values.get("term_id"):
        st.warning("请先选择营期")
        st.stop()

    sql, sa_params = build_sql(TEMPLATE, filter_values)

    with st.expander("执行的 SQL", expanded=False):
        st.code(format_display_sql(sql, sa_params), language="sql")

    with st.spinner("查询中..."):
        df = conn.query(sql, params=sa_params, ttl=0)

    st.metric("查询结果", f"{len(df)} 条")

    tab_chart, tab_table = st.tabs(["图表", "表格"])

    with tab_chart:
        st.bar_chart(
            df.set_index("class_name")["authorized_student_num"],
            x_label="班级",
            y_label="授权学员数",
        )

    with tab_table:
        st.dataframe(df, width="stretch")

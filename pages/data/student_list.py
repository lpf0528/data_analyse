import streamlit as st
from utils.metabase import extract_params, build_sql, format_display_sql
from utils.filters import render_filters

TEMPLATE = """
SELECT
  `c`.`class_name`,
  `s`.`account_id`,
  `s`.`wechat_nickname`,
  `s`.`student_status`,
  `s`.`authorization_status`,
  `s`.`add_status`
FROM `ods_lh_teaching_lh_teaching_student` `s`
LEFT JOIN `dwd_lh_classes` `c`
  ON `s`.`big_class_id` = `c`.`id`
WHERE 1=1
  AND `s`.`tid` = {{tid}}
  AND `s`.`camp_id` = {{camp_id}}
  [[ AND `s`.`term_id` IN ({{term_ids}}) ]]
  [[ AND `s`.`big_class_id` IN ({{class_ids}}) ]]
  [[ AND `s`.`wechat_nickname` LIKE CONCAT('%', {{name}}, '%') ]]
LIMIT 1000
"""

st.title("学员列表")

# if not st.session_state.get("tid") or not st.session_state.get("camp_id"):
#     st.warning("请先登录")
#     st.stop()

conn = st.connection("mysql", type="sql")

filter_values = render_filters(
    conn,
    extract_params(TEMPLATE),
    fallbacks={"name": {"label": "昵称搜索", "widget": "text_input"}},
)

if st.button("查询", type="primary"):
    sql, sa_params = build_sql(TEMPLATE, filter_values)

    with st.spinner("查询中..."):
        df = conn.query(sql, params=sa_params, ttl=0)

    st.metric("查询结果", f"{len(df)} 条")
    st.dataframe(df, use_container_width=True)

    with st.expander("执行的 SQL", expanded=True):
        st.code(format_display_sql(sql, sa_params), language="sql")

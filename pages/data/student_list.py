import math
import streamlit as st
from utils.metabase import extract_params, build_sql, format_display_sql
from utils.filters import render_filters

_FROM_WHERE = """
FROM `ods_lh_teaching_lh_teaching_student` `s`
LEFT JOIN `dwd_lh_classes` `c`
  ON `s`.`big_class_id` = `c`.`id`
WHERE 1=1
  AND `s`.`tid` = {{tid}}
  AND `s`.`camp_id` = {{camp_id}}
  [[ AND `s`.`term_id` IN ({{term_ids}}) ]]
  [[ AND `s`.`big_class_id` IN ({{class_ids}}) ]]
  [[ AND `s`.`wechat_nickname` LIKE CONCAT('%', {{name}}, '%') ]]
"""

COUNT_TEMPLATE = "SELECT COUNT(*) AS `total` " + _FROM_WHERE

DATA_TEMPLATE = """
SELECT
  `c`.`class_name`,
  `s`.`account_id`,
  `s`.`wechat_nickname`,
  `s`.`student_status`,
  `s`.`authorization_status`,
  `s`.`add_status`
""" + _FROM_WHERE + """
LIMIT {{limit}} OFFSET {{offset}}
"""

PAGE_SIZE_OPTIONS = [5, 10, 15, 20]
_SS_FILTERS = "student_list_filters"
_SS_PAGE = "student_list_page"
_SS_SIZE = "student_list_page_size"
_SS_SIZE_PREV = "student_list_page_size_prev"

st.subheader("学员列表")

# if not st.session_state.get("tid") or not st.session_state.get("camp_id"):
#     st.warning("请先登录")
#     st.stop()

conn = st.connection("mysql", type="sql")

filter_values = render_filters(
    conn,
    extract_params(COUNT_TEMPLATE),
    fallbacks={"name": {"label": "昵称搜索", "widget": "text_input"}},
)

with st.container(horizontal_alignment="right"):
    if st.button("查询", type="primary"):
        st.session_state[_SS_FILTERS] = filter_values
        st.session_state[_SS_PAGE] = 1

if _SS_FILTERS in st.session_state:
    saved_filters = st.session_state[_SS_FILTERS]
    page_size = st.session_state.get(_SS_SIZE, 20)
    if st.session_state.get(_SS_SIZE_PREV) != page_size:
        st.session_state[_SS_PAGE] = 1
        st.session_state[_SS_SIZE_PREV] = page_size

    count_sql, count_params = build_sql(COUNT_TEMPLATE, saved_filters)
    with st.spinner("查询中..."):
        total = int(conn.query(count_sql, params=count_params, ttl=0).iloc[0]["total"])

    total_pages = max(1, math.ceil(total / page_size) if total else 1)
    if st.session_state.get(_SS_PAGE, 1) > total_pages:
        st.session_state[_SS_PAGE] = total_pages

    # 占位：SQL 在上、表格在中，分页在下（官方 empty + pagination 模式）
    sql_slot = st.empty()
    dataframe_slot = st.empty()

    _, page_col, right_col = st.columns(
        [2, 3, 2], vertical_alignment="center"
    )
    with page_col:
        with st.container(horizontal_alignment="center"):
            page = st.pagination(
                num_pages=total_pages,
                default=1,
                key=_SS_PAGE,
            )
    with right_col:
        with st.container(
            horizontal=True,
            horizontal_alignment="right",
            vertical_alignment="center",
            gap="xsmall",
        ):
            st.caption(f"共 {total} 条", width="content")
            st.selectbox(
                "每页条数",
                PAGE_SIZE_OPTIONS,
                index=PAGE_SIZE_OPTIONS.index(page_size)
                if page_size in PAGE_SIZE_OPTIONS
                else 3,
                key=_SS_SIZE,
                label_visibility="collapsed",
                width=80,
            )

    offset = (page - 1) * page_size
    data_values = {**saved_filters, "limit": page_size, "offset": offset}
    data_sql, data_params = build_sql(DATA_TEMPLATE, data_values)

    with sql_slot.expander("执行的 SQL", expanded=False):
        st.code(format_display_sql(data_sql, data_params), language="sql")

    with st.spinner("查询中..."):
        df = conn.query(data_sql, params=data_params, ttl=0)
    dataframe_slot.dataframe(df, width="stretch", hide_index=True)

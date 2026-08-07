"""
学员列表页：SQL 分页列表示例。

布局约定见 AGENTS.md「列表分页页布局惯例」：
标题+静态说明 → 筛选 → 查询 → 摘要 caption → 结果区（SQL / 表格 / 分页栏）。
期次默认第一项；首次进入自动查询一次。
"""
import math
import streamlit as st
from utils.metabase import extract_params, build_sql, format_display_sql
from utils.filters import render_filters
from utils.page_copy import fill_template, join_labels
from utils.query import get_conn

# COUNT / DATA 共用 FROM+WHERE，保证总数与列表筛选条件一致
# 表名带 warehouse.：经 Metabase 时默认库为 doris，无 schema 会找不到表
_FROM_WHERE = """
FROM `warehouse`.`ods_lh_teaching_lh_teaching_student` `s`
LEFT JOIN `warehouse`.`dwd_lh_classes` `c`
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

# 静态说明 + 查询后摘要（总数来自 COUNT，与底栏「共 N 条」同源）
_INTRO = (
    "按期次 / 班级 / 昵称筛选学员明细。"
    "主要字段：班级、账号、微信昵称、学员状态、授权状态、添加状态。"
)
_SUMMARY_TPL = (
    "当前筛选：期次 {term_scope}；班级 {class_scope}；"
    "昵称关键词「{name_scope}」。共 {total} 人。"
)

PAGE_SIZE_OPTIONS = [5, 10, 15, 20]
# session_state 键：与带 key 的 widget 一一对应；改值时勿再给 widget 传 default/index
_SS_FILTERS = "student_list_filters"       # 上次查询冻结的筛选条件（首次进入也会写入）
_SS_LABELS = "student_list_filter_labels"  # 与筛选一并冻结的可读 label
_SS_PAGE = "student_list_page"             # st.pagination 的 key
_SS_SIZE = "student_list_page_size"        # 每页条数 selectbox 的 key
_SS_SIZE_PREV = "student_list_page_size_prev"  # 用于检测 page_size 变化并重置页码

st.subheader("学员列表")
st.markdown(_INTRO)

# if not st.session_state.get("tid") or not st.session_state.get("camp_id"):
#     st.warning("请先登录")
#     st.stop()

conn = get_conn()

# 筛选区由 render_filters 统一渲染（横向固定宽：多选 400 / 其余 200）
filter_values, filter_labels = render_filters(
    conn,
    extract_params(COUNT_TEMPLATE),
    fallbacks={"name": {"label": "昵称搜索", "widget": "text_input"}},
)


def _freeze_filters() -> None:
    st.session_state[_SS_FILTERS] = filter_values
    st.session_state[_SS_LABELS] = filter_labels


# 查询按钮右对齐；点击后冻结筛选并回到第 1 页
with st.container(horizontal_alignment="right"):
    if st.button("查询", type="primary"):
        _freeze_filters()
        # 仅在 pagination 已存在时写页码（首次进入勿写，否则与 default=1 双设告警）
        if _SS_PAGE in st.session_state:
            st.session_state[_SS_PAGE] = 1

# 首次进入：只冻结筛选，页码交给 st.pagination 的 default=1，勿预写 _SS_PAGE
if _SS_FILTERS not in st.session_state:
    _freeze_filters()

# 已有冻结条件则展示结果（翻页 / 改每页条数不丢条件）
if _SS_FILTERS in st.session_state:
    saved_filters = st.session_state[_SS_FILTERS]
    saved_labels = st.session_state.get(_SS_LABELS, {})
    # 每页条数：只通过 session_state 管值，勿再传 index
    st.session_state.setdefault(_SS_SIZE, 20)
    page_size = st.session_state[_SS_SIZE]
    # 首次记录 prev 不算变更；真正改每页条数时才重置页码
    if _SS_SIZE_PREV not in st.session_state:
        st.session_state[_SS_SIZE_PREV] = page_size
    elif st.session_state[_SS_SIZE_PREV] != page_size:
        if _SS_PAGE in st.session_state:
            st.session_state[_SS_PAGE] = 1
        st.session_state[_SS_SIZE_PREV] = page_size

    count_sql, count_params = build_sql(COUNT_TEMPLATE, saved_filters)
    with st.spinner("查询中..."):
        total = int(conn.query(count_sql, params=count_params, ttl=0).iloc[0]["total"])

    name_raw = (saved_filters.get("name") or "").strip()
    st.caption(
        fill_template(
            _SUMMARY_TPL,
            term_scope=join_labels(saved_labels.get("term_ids")),
            class_scope=join_labels(saved_labels.get("class_ids"), empty="全部"),
            name_scope=name_raw if name_raw else "（未限）",
            total=total,
        )
    )

    total_pages = max(1, math.ceil(total / page_size) if total else 1)
    # 总数变少时避免当前页超出范围（键不存在时视为第 1 页，与 pagination default 一致）
    if st.session_state.get(_SS_PAGE, 1) > total_pages:
        st.session_state[_SS_PAGE] = total_pages

    # 官方 empty + pagination：先占位 SQL/表格，再画底栏拿 page，最后回填
    # （分页在视觉上在表格下方，但 page 值必须先于数据查询拿到）
    sql_slot = st.empty()
    dataframe_slot = st.empty()

    # 底栏三列 [2,3,2]：左空 | 中分页居中 | 右「共 x 条」+ 每页条数
    _, page_col, right_col = st.columns(
        [2, 3, 2], vertical_alignment="center"
    )
    with page_col:
        with st.container(horizontal_alignment="center"):
            page = st.pagination(
                num_pages=total_pages,
                key=_SS_PAGE,  # 勿传 default；也勿在首次渲染前写 session_state[key]
            )
    with right_col:
        with st.container(
            horizontal=True,
            horizontal_alignment="right",
            vertical_alignment="center",
            gap="xsmall",  # 两项间距收紧；默认 small 偏宽
        ):
            # caption 必须 width="content"，否则 stretch 会撑开与选择框的间距
            st.caption(f"共 {total} 条", width="content")
            st.selectbox(
                "每页条数",
                PAGE_SIZE_OPTIONS,
                key=_SS_SIZE,  # 勿传 index，同上
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

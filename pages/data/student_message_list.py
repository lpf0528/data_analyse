"""
学员消息查看面板：SQL 分页列表。

优化说明：
1. 使用 st.form 包裹筛选区域与查询按钮，避免勾选多选框（如班级）时触发频繁页面 rerun 与闪动；
2. 避免使用 st.empty 占位符重新挂载 DOM 节点，改由直接读取 session_state[_SS_PAGE] 顺次渲染，消除表格白屏闪烁。
"""
import math
import streamlit as st
from utils.metabase import extract_params, build_sql, format_display_sql
from utils.filters import render_filters
from utils.query import get_conn

_FROM_WHERE = """
FROM `warehouse`.`ods_lh_efficiency_platform_term_student_chat_message_all` `m`
LEFT JOIN `warehouse`.`dim_lh_teaching_class_term` `ct`
  ON `m`.`term_id` = `ct`.`id`
LEFT JOIN `warehouse`.`ods_lh_teaching_lh_teaching_student` `s`
  ON `m`.`account_id` = `s`.`account_id`
  AND `m`.`term_id` = `s`.`term_id`
LEFT JOIN `warehouse`.`dwd_lh_classes` `c`
  ON `s`.`big_class_id` = `c`.`id`
WHERE 1=1
  AND `m`.`term_id` IN ({{term_ids}})
  [[ AND `s`.`big_class_id` IN ({{class_ids}}) ]]
  [[ AND `m`.`account_id` = {{account_id}} ]]
  [[ AND `m`.`reply_msg_scene` LIKE CONCAT('%', {{reply_msg_scene}}, '%') ]]
  [[ AND `m`.`state` = {{state}} ]]
"""

COUNT_TEMPLATE = "SELECT COUNT(*) AS `total` " + _FROM_WHERE

DATA_TEMPLATE = """
SELECT
  `m`.`id` AS `消息ID`,
  CONCAT('第', IFNULL(`ct`.`rank`, `m`.`term_id`), '期') AS `营期`,
  `c`.`class_name` AS `班级名称`,
  `m`.`account_id` AS `学员ID`,
  `s`.`wechat_nickname` AS `微信昵称`,
  `m`.`msg_time` AS `消息时间`,
  `m`.`msg_content` AS `消息内容`,
  CASE `m`.`msg_type`
    WHEN 10000 THEN '系统消息'
    WHEN 2001 THEN '文字'
    WHEN 2002 THEN '图片'
    WHEN 2003 THEN '语音'
    WHEN 2004 THEN '视频'
    WHEN 2005 THEN '图文链接'
    WHEN 2006 THEN '好友名片'
    WHEN 2010 THEN '文件'
    WHEN 2013 THEN '小程序'
    WHEN 2017 THEN '视频号消息'
    WHEN 2021 THEN '位置消息'
    WHEN 2018 THEN '转发消息'
    ELSE CAST(`m`.`msg_type` AS CHAR)
  END AS `消息类型`,
  CASE `m`.`state`
    WHEN 'success' THEN '发送成功'
    WHEN 'sending' THEN '发送中'
    WHEN 'fail' THEN '发送失败'
    WHEN 'recall' THEN '已撤回'
    ELSE IFNULL(`m`.`state`, '-')
  END AS `发送状态`,
  `m`.`reply_time` AS `回复时间`,
  `m`.`wait_interval` AS `等待时长(s)`,
  IF(`m`.`wait_interval` >= 7200, '是(逾期)', '否') AS `是否逾期`,
  `m`.`reply_content` AS `回复内容`,
  CASE
    WHEN `m`.`reply_msg_scene` LIKE '%chat%' THEN 'chat 聊天'
    WHEN `m`.`reply_msg_scene` LIKE '%web%' THEN 'web 客服工作台发送'
    WHEN `m`.`reply_msg_scene` LIKE '%ai_auto%' THEN 'ai_auto AI消息发送'
    WHEN `m`.`reply_msg_scene` LIKE '%keyword%' THEN 'keyword 关键词回复'
    ELSE IFNULL(`m`.`reply_msg_scene`, '其他/未回复')
  END AS `回复场景`,
  `m`.`label` AS `消息标签`
""" + _FROM_WHERE + """
ORDER BY `m`.`msg_time` DESC
LIMIT {{limit}} OFFSET {{offset}}
"""

CLASS_SUMMARY_TEMPLATE = """
SELECT
  IFNULL(`c`.`class_name`, '未分班/未知') AS `班级名称`,
  COUNT(`m`.`id`) AS `学员消息数`,
  COUNT(DISTINCT NVL(`s`.`account_main_id`, `m`.`account_id`)) AS `学员数`,
  COUNT(CASE WHEN `m`.`reply_time` IS NOT NULL AND `m`.`wait_interval` <= 1800 THEN `m`.`id` END) AS `30分钟内有效回复数`,
  ROUND(
    100.0 * COUNT(CASE WHEN `m`.`reply_time` IS NOT NULL AND `m`.`wait_interval` <= 1800 THEN `m`.`id` END)
    / NULLIF(COUNT(`m`.`id`), 0),
    2
  ) AS `有效回复率(%)`
""" + _FROM_WHERE + """
GROUP BY `s`.`big_class_id`, `c`.`class_name`
ORDER BY `学员消息数` DESC
"""

_INTRO = (
    "按期次、班级、学员ID、回复场景及发送状态查询营期学员的聊天消息跟进明细。"
    "包含消息内容、发送状态、响应时长、是否逾期未回复及回复场景等信息。"
)

PAGE_SIZE_OPTIONS = [10, 20, 50, 100]

_SS_FILTERS = "student_message_list_filters"
_SS_LABELS = "student_message_list_filter_labels"
_SS_PAGE = "student_message_list_page"
_SS_SIZE = "student_message_list_page_size"
_SS_SIZE_PREV = "student_message_list_page_size_prev"

st.subheader("学员消息查看面板")
st.markdown(_INTRO)

conn = get_conn()

# 用 st.form 包裹筛选区与查询按钮，避免勾选多选框时页面闪动
with st.form("student_msg_filter_form", border=False):
    filter_values, filter_labels = render_filters(
        conn,
        extract_params(COUNT_TEMPLATE),
        fallbacks={
            "account_id": {"label": "学员ID", "widget": "number_input"},
            "reply_msg_scene": {
                "label": "回复场景",
                "widget": "selectbox",
                "options": {
                    "chat (聊天)": "chat",
                    "web (客服工作台发送)": "web",
                    "ai_auto (AI消息发送)": "ai_auto",
                    "keyword (关键词回复)": "keyword",
                },
            },
            "state": {
                "label": "发送状态",
                "widget": "selectbox",
                "options": {
                    "发送成功 (success)": "success",
                    "发送中 (sending)": "sending",
                    "发送失败 (fail)": "fail",
                    "已撤回 (recall)": "recall",
                },
            },
        },
    )
    with st.container(horizontal_alignment="right"):
        submitted = st.form_submit_button("查询", type="primary")


def _freeze_filters() -> None:
    st.session_state[_SS_FILTERS] = filter_values
    st.session_state[_SS_LABELS] = filter_labels


if submitted:
    _freeze_filters()
    if _SS_PAGE in st.session_state:
        st.session_state[_SS_PAGE] = 1

if _SS_FILTERS not in st.session_state:
    _freeze_filters()

if _SS_FILTERS in st.session_state:
    saved_filters = st.session_state[_SS_FILTERS]
    saved_labels = st.session_state.get(_SS_LABELS, {})

    st.session_state.setdefault(_SS_SIZE, 20)
    page_size = st.session_state[_SS_SIZE]

    if _SS_SIZE_PREV not in st.session_state:
        st.session_state[_SS_SIZE_PREV] = page_size
    elif st.session_state[_SS_SIZE_PREV] != page_size:
        if _SS_PAGE in st.session_state:
            st.session_state[_SS_PAGE] = 1
        st.session_state[_SS_SIZE_PREV] = page_size

    count_sql, count_params = build_sql(COUNT_TEMPLATE, saved_filters)
    try:
        with st.spinner("查询中..."):
            total = int(
                conn.query(count_sql, params=count_params, ttl=0).iloc[0]["total"]
            )
    except Exception as exc:
        st.error(f"COUNT 查询失败：{exc}")
        st.stop()

    # 1. 班级维度消息汇总区（置顶展示）
    st.subheader("一、班级维度消息汇总")

    summary_sql, summary_params = build_sql(CLASS_SUMMARY_TEMPLATE, saved_filters)
    with st.expander("执行的 SQL（班级汇总）", expanded=False):
        st.code(format_display_sql(summary_sql, summary_params), language="sql")

    try:
        with st.spinner("计算班级汇总中..."):
            summary_df = conn.query(summary_sql, params=summary_params, ttl=0)
    except Exception as exc:
        st.error(f"班级汇总查询失败：{exc}")
        summary_df = None

    if summary_df is not None:
        if summary_df.empty:
            st.info("暂无班级汇总数据")
        else:
            st.dataframe(
                summary_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "有效回复率(%)": st.column_config.NumberColumn(
                        label="有效回复率 (30min内)",
                        format="%.2f %%",
                    ),
                },
            )

    # 2. 学员消息明细列表区（置于下方）
    st.divider()
    st.subheader("二、学员消息明细")

    total_pages = max(1, math.ceil(total / page_size) if total else 1)
    current_page = st.session_state.get(_SS_PAGE, 1)
    if current_page > total_pages:
        current_page = total_pages
        if _SS_PAGE in st.session_state:
            st.session_state[_SS_PAGE] = total_pages

    offset = (current_page - 1) * page_size
    data_values = {**saved_filters, "limit": page_size, "offset": offset}
    data_sql, data_params = build_sql(DATA_TEMPLATE, data_values)

    with st.expander("执行的 SQL（消息明细）", expanded=False):
        st.code(format_display_sql(data_sql, data_params), language="sql")

    try:
        with st.spinner("查询中..."):
            df = conn.query(data_sql, params=data_params, ttl=0)
    except Exception as exc:
        st.error(f"查询失败：{exc}")
        st.stop()

    st.dataframe(df, width="stretch", hide_index=True)

    # 底部分页栏
    _, page_col, right_col = st.columns(
        [2, 3, 2], vertical_alignment="center"
    )
    with page_col:
        with st.container(horizontal_alignment="center"):
            st.pagination(
                num_pages=total_pages,
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
                key=_SS_SIZE,
                label_visibility="collapsed",
                width=80,
            )

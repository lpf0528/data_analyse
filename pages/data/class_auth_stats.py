"""
班级授权学员数：筛选 → 查询 → 简介/KPI/洞察 → 图表+表格。

布局约定见 AGENTS.md「页面结果展示惯例」与「说明 / KPI / 模板洞察」：
标题+静态简介 → 筛选 → 查询 → SQL → metric + 洞察 → tabs。
期次由 FilterSpec.default_first 默认选中第一项；首次进入自动查询一次。
"""
import streamlit as st
from utils.metabase import extract_params, build_sql
from utils.filters import render_filters
from utils.page_copy import fill_template, join_labels
from utils.query import get_conn, show_sql_and_query

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

# 页面简介（静态）；洞察用 str.format，与 Metabase {{param}} 分开
_INTRO = (
    "按班级统计**已授权**学员数（同一主账号去重）。"
    "可用于对比各班授权规模；柱状图按授权数从高到低排列。"
)
_INSIGHT_TPL = (
    "当前期次：{term_label}；班级范围：{class_scope}。"
    "共 {n} 个班，授权学员合计 {total} 人，班均 {avg} 人。"
    "最高为「{top_name}」（{top_num} 人，占合计 {top_pct}%）。"
    "共 {above_avg_n} 个班高于均值。"
)

# 冻结上次查询条件与可读 label；改筛选不自动重查，点「查询」或首次进入才更新
_SS_FILTERS = "class_auth_stats_filters"
_SS_LABELS = "class_auth_stats_filter_labels"

st.subheader("班级授权学员数")
st.markdown(_INTRO)

if not st.session_state.get("tid") or not st.session_state.get("camp_id"):
    st.warning("请先登录")
    st.stop()

conn = get_conn()

# 筛选区由 render_filters 统一渲染；同时取 labels 供文案填充
filter_values, filter_labels = render_filters(conn, extract_params(TEMPLATE))


def _freeze_filters() -> None:
    st.session_state[_SS_FILTERS] = filter_values
    st.session_state[_SS_LABELS] = filter_labels


# 查询按钮右对齐；点击后冻结当前筛选与 labels
with st.container(horizontal_alignment="right"):
    if st.button("查询", type="primary"):
        _freeze_filters()

# 首次进入：用当前默认筛选自动查一次（之后仅点「查询」才刷新）
if _SS_FILTERS not in st.session_state:
    _freeze_filters()

saved_filters = st.session_state[_SS_FILTERS]
saved_labels = st.session_state.get(_SS_LABELS, {})
if not saved_filters.get("term_id"):
    st.warning("请先选择期次")
    st.stop()

sql, sa_params = build_sql(TEMPLATE, saved_filters)

# 先展示 SQL；查询失败时 SQL 仍留在页面上便于排查
df = show_sql_and_query(conn, sql, sa_params, ttl=0)

if df.empty:
    # 空数据不硬填洞察；与 fill_template 分段策略一致
    st.info("暂无数据")
    st.stop()

# KPI + 洞察：数据来自冻结筛选后的 df，与下方图表一致
n = int(len(df))
total = int(df["authorized_student_num"].sum())
avg = total / n if n else 0
top_row = df.iloc[0]
top_name = str(top_row["class_name"] or "（未命名班级）")
top_num = int(top_row["authorized_student_num"])
top_pct = round(100 * top_num / total, 1) if total else 0.0
above_avg_n = int((df["authorized_student_num"] > avg).sum())

m1, m2, m3 = st.columns(3)
m1.metric("班级数", n)
m2.metric("授权合计", total)
m3.metric("最高班级授权数", top_num)

st.markdown(
    fill_template(
        _INSIGHT_TPL,
        term_label=saved_labels.get("term_id") or "—",
        class_scope=join_labels(saved_labels.get("class_ids"), empty="全部班级"),
        n=n,
        total=total,
        avg=round(avg, 1),
        top_name=top_name,
        top_num=top_num,
        top_pct=top_pct,
        above_avg_n=above_avg_n,
    )
)

tab_chart, tab_table = st.tabs(["图表", "表格"])

with tab_chart:
    # 默认 width="stretch" 在 1～2 个班级时会把柱子拉满整行，观感很差；
    # 少类别按柱数给固定像素宽（约 120px/柱），多了再拉满容器。
    chart_width = "stretch" if n > 5 else max(200, n * 120 + 80)
    st.bar_chart(
        df,
        x="class_name",
        y="authorized_student_num",
        x_label="班级",
        y_label="授权学员数",
        width=chart_width,
        sort=False,  # 保持 SQL 已按授权数降序，勿按类名重排
    )

with tab_table:
    # 禁止 use_container_width；用 width="stretch"；隐藏默认行号
    st.dataframe(df, width="stretch", hide_index=True)

"""
班级周数据汇总分析报告：按自然周对比各班级外诉人数、退费人数、作业提交人数的差异。
样式风格：报告文档 (Report Document)
"""
import pandas as pd
import streamlit as st
from utils.metabase import extract_params, build_sql, format_display_sql
from utils.filters import render_filters
from utils.page_copy import fill_template, join_labels
from utils.query import get_conn

TEMPLATE = """
SELECT
  `ct`.`rank`                         AS `term_rank`,
  `c`.`id`                            AS `class_id`,
  `c`.`class_name`,
  SUM(`cw`.`ws_num`)                  AS `ws_num`,
  SUM(`cw`.`external_complain_count`) AS `external_complain_count`,
  SUM(`cw`.`refund_num`)              AS `refund_num`,
  SUM(`cw`.`homework_submit_num`)      AS `homework_submit_num`
FROM `warehouse`.`dws_lh_teaching_term_class_week` `cw`
JOIN `warehouse`.`dim_lh_teaching_class_term` `ct`
  ON `cw`.`term_id` = `ct`.`id`
JOIN `warehouse`.`dwd_lh_classes` `c`
  ON `cw`.`class_id` = `c`.`id`
JOIN `warehouse`.`dim_lh_teaching_weeks_conf` `wc`
  ON `wc`.`year` = `cw`.`year`
  AND `wc`.`month` = `cw`.`month`
  AND `wc`.`week` = `cw`.`week`
  AND `wc`.`tid` = {{tid}}
  AND `wc`.`id` = {{week_id}}
WHERE 1=1
  AND `ct`.`tid` = {{tid}}
  AND `ct`.`camp_id` = {{camp_id}}
  AND `cw`.`term_id` IN ({{term_ids}})
  [[ AND `c`.`id` IN ({{class_ids}}) ]]
GROUP BY
  `ct`.`rank`,
  `c`.`id`,
  `c`.`class_name`
ORDER BY
  `ct`.`rank`,
  `c`.`class_name`
"""

_INTRO = (
    "本报告定格展现指定自然周下各班级的**外诉次数**、**退费人数**与**作业提交人数**等核心服务与学习指标，"
    "覆盖班级规模差异、异常风险聚集情况与学员交业活跃度。\n\n"
    "💡 **分析目的**：通过周度横向数据对比，帮助运营团队快速识别高外诉/高退费风险班级，并评估各班学员的持续学习参与度。"
)

_INSIGHT_TPL = (
    "##### 📌 报告核心观察与结论\n\n"
    "- **统计范围**：自然周 **{week_label}**；期次范围 **{term_scope}**；班级范围 **{class_scope}**。\n"
    "- **整体服务与活跃盘点**：本次共评估 **{n}** 个班级，累计外诉 **{total_ws}** 次（包含 **{total_ext_complain}** 单外诉单），产生退费学员 **{total_refund}** 人，完成作业提交 **{total_hw}** 人。\n"
    "- **外诉风险关注**：外诉次数最多的班级为「**{top_ws_name}**」（累计外诉 **{top_ws_num}** 次），建议重点关注该班服务过程。\n"
    "- **退费人群集中度**：退费人数最多的班级为「**{top_refund_name}**」（退费学员 **{top_refund_num}** 人）。\n"
    "- **学习活跃标杆**：作业提交人数最多的班级为「**{top_hw_name}**」（提交作业 **{top_hw_num}** 人），整体交业活跃度较高。"
)

_SS_FILTERS = "class_week_stats_filters"
_SS_LABELS = "class_week_stats_filter_labels"
_SS_DF = "class_week_stats_df"
_SS_SQL_PARAMS = "class_week_stats_sql_params"

# 1. 报告 Header 区域
st.subheader("📄 班级周数据汇总分析报告")
st.caption(
    f"分析专题：周度班级服务风险与学员活跃度评估  |  "
    f"团队/营期：tid={st.session_state.get('tid', '—')} · camp_id={st.session_state.get('camp_id', '—')}  |  "
    f"文档密级：内部数据报告"
)

# 2. 报告前言与概述 Card
with st.container(border=True):
    st.markdown("##### 📝 报告前言与概述")
    st.markdown(_INTRO)

if not st.session_state.get("tid") or not st.session_state.get("camp_id"):
    st.warning("请先登录")
    st.stop()

conn = get_conn()

# 3. 报告查询参数配置 Card
do_query = False
with st.container(border=True):
    st.markdown("##### 📋 报告查询参数")
    filter_values, filter_labels = render_filters(
        conn,
        extract_params(TEMPLATE),
        spec_overrides={"week_id": {"default_first": True}},
    )
    with st.container(horizontal_alignment="right"):
        if st.button(
            "生成分析报告", type="primary", icon=":material/analytics:"
        ):
            do_query = True

if do_query:
    missing = []
    if not filter_values.get("week_id"):
        missing.append("自然周")
    if not filter_values.get("term_ids"):
        missing.append("期次")
    if missing:
        st.warning(f"请先选择：{'、'.join(missing)}")
        st.stop()

    sql, sa_params = build_sql(TEMPLATE, filter_values)

    with st.spinner("数据查询中，正在生成报告..."):
        try:
            df = conn.query(sql, params=sa_params, ttl=0)
            st.session_state[_SS_FILTERS] = filter_values
            st.session_state[_SS_LABELS] = filter_labels
            st.session_state[_SS_SQL_PARAMS] = (sql, sa_params)
            st.session_state[_SS_DF] = df
        except Exception as exc:
            with st.expander("🔍 附录：数据查询 SQL 语句", expanded=True):
                st.code(format_display_sql(sql, sa_params), language="sql")
            st.error(f"查询失败：{exc}")
            st.stop()

if _SS_DF not in st.session_state:
    st.info("请在上方选择筛选参数后，点击「生成分析报告」查看完整报告内容。")
    st.stop()

df = st.session_state[_SS_DF].copy()
saved_labels = st.session_state[_SS_LABELS]
sql, sa_params = st.session_state[_SS_SQL_PARAMS]

if df.empty:
    st.info("暂无满足条件的数据")
    st.stop()

# 填充数值列的 None / NaN，防止转换为 int 时触发 TypeError
num_cols = ["ws_num", "external_complain_count", "refund_num", "homework_submit_num"]
for col in num_cols:
    if col in df.columns:
        df[col] = df[col].fillna(0).astype(int)


def _safe_int(val) -> int:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


n = int(len(df))
total_ws = _safe_int(df["ws_num"].sum())
total_ext_complain = _safe_int(df["external_complain_count"].sum())
total_refund = _safe_int(df["refund_num"].sum())
total_hw = _safe_int(df["homework_submit_num"].sum())

top_ws_row = df.sort_values(by="ws_num", ascending=False).iloc[0]
top_ws_name = str(top_ws_row["class_name"] or "—")
top_ws_num = _safe_int(top_ws_row["ws_num"])

top_refund_row = df.sort_values(by="refund_num", ascending=False).iloc[0]
top_refund_name = str(top_refund_row["class_name"] or "—")
top_refund_num = _safe_int(top_refund_row["refund_num"])

top_hw_row = df.sort_values(by="homework_submit_num", ascending=False).iloc[0]
top_hw_name = str(top_hw_row["class_name"] or "—")
top_hw_num = _safe_int(top_hw_row["homework_submit_num"])

# 4. 第一章：核心指标概览
st.markdown("### 一、 核心指标概览")
with st.container(border=True):
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("评估班级总数", f"{n} 个")
    m2.metric("外诉总次数", f"{total_ws} 次")
    m3.metric("退费总人数", f"{total_refund} 人")
    m4.metric("作业提交总人数", f"{total_hw} 人")

# 5. 第二章：核心结论与风险洞察
st.markdown("### 二、 核心结论与风险洞察")
with st.container(border=True):
    st.markdown(
        fill_template(
            _INSIGHT_TPL,
            week_label=saved_labels.get("week_id") or "—",
            term_scope=join_labels(saved_labels.get("term_ids"), empty="全部期次"),
            class_scope=join_labels(
                saved_labels.get("class_ids"), empty="全部班级"
            ),
            n=n,
            total_ws=total_ws,
            total_ext_complain=total_ext_complain,
            total_refund=total_refund,
            total_hw=total_hw,
            top_ws_name=top_ws_name,
            top_ws_num=top_ws_num,
            top_refund_name=top_refund_name,
            top_refund_num=top_refund_num,
            top_hw_name=top_hw_name,
            top_hw_num=top_hw_num,
        )
    )

# 6. 第三章：周度对比与明细数据
st.markdown("### 三、 班级周度对比与明细数据")

tab_chart, tab_table = st.tabs(["📈 风险与活跃分布图", "📋 完整明细表"])

with tab_chart:
    chart_width = "stretch" if n > 5 else max(200, n * 120 + 80)

    col1, col2 = st.columns(2)
    with col1:
        st.caption("各班级外诉与退费指标对比")
        st.bar_chart(
            df,
            x="class_name",
            y=["ws_num", "refund_num"],
            x_label="班级",
            y_label="次数 / 人数",
            width=chart_width,
        )
    with col2:
        st.caption("各班级作业提交人数对比")
        st.bar_chart(
            df,
            x="class_name",
            y="homework_submit_num",
            x_label="班级",
            y_label="交业人数",
            width=chart_width,
        )

with tab_table:
    display_df = df.rename(
        columns={
            "term_rank": "期数",
            "class_id": "班级 ID",
            "class_name": "班级名称",
            "ws_num": "外诉次数",
            "external_complain_count": "外诉单数",
            "refund_num": "退费人数",
            "homework_submit_num": "作业提交人数",
        }
    )
    st.dataframe(display_df, width="stretch", hide_index=True)

    with st.expander("🔍 附录：数据查询 SQL 语句", expanded=False):
        st.code(format_display_sql(sql, sa_params), language="sql")

st.divider()
st.caption("— 报告生成完毕 · 数据来源：Warehouse DW · 仅供内部决策参阅 —")

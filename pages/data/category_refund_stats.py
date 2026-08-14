"""
品类退款分析：按品类汇总已支付/已退款订单的退款单数、金额与退款率。

布局约定见 AGENTS.md「页面结果展示惯例」与「说明 / KPI / 模板洞察」：
标题+静态简介 → 筛选 → 查询 → SQL → metric + 洞察 → tabs。
必填：下单起止日期（筛选项最前）；期次可选（不默认选中）；首次进入自动查询。
"""
from datetime import date, timedelta

import streamlit as st
from utils.metabase import extract_params, build_sql
from utils.filters import render_filters
from utils.page_copy import fill_template, join_labels
from utils.query import get_conn, show_sql_and_query

# Metabase 原样模板（去掉 use warehouse;：连接已指向 warehouse）
TEMPLATE = """
WITH repurchase_term AS (
    SELECT
        t1.tid, t1.camp_id, t2.id AS term_id, t2.rank, t3.camp_name
    FROM warehouse.dim_lh_teaching_repurchase_camp t1
    JOIN [shuffle] warehouse.dim_lh_class_term t2
        ON t1.camp_id = t2.camp_id
    JOIN [shuffle] warehouse.dim_lh_class_camp t3
        ON t1.camp_id = t3.id
    WHERE t1.`status` = 1
        AND t1.tid = {{tid}}
),
authorize_account AS (
    SELECT DISTINCT
        t1.term_id,
        t1.grant_class_id AS class_id,
        t1.student_status,
        t1.grant_time,
        nvl(ar2.origin_account_id,t1.account_id) as account_id,
        NVL(ar.account_main_id, t1.account_id) AS account_main_id,
        t2.tid,
        t2.rank,
        t3.class_name,
        RANK() OVER(partition by t1.camp_id, NVL(ar.account_main_id, t1.account_id) ORDER BY t1.grant_time DESC) r
    FROM warehouse.dim_lh_term_student_metrics t1
    JOIN [shuffle] warehouse.dim_lh_teaching_class_term t2
        ON t1.term_id = t2.id AND t2.tid = {{tid}}
    JOIN [shuffle] warehouse.dwd_lh_classes t3
        ON t1.grant_class_id = t3.id
    LEFT JOIN warehouse.dim_origin_account_relation ar
        ON t1.account_id = ar.origin_account_id
    LEFT JOIN warehouse.dim_origin_account_relation ar2
        ON ar2.account_main_id = ar.account_main_id
    WHERE t1.student_status NOT IN ('abandon')
),
account_repurchase_order AS (
    SELECT
        IF(t2.order_source = 'loan_plan', t2.order_id, t2.id) as order_id,
        t2.account_id,
        IF(t2.source = 0, 'high', 'physical') AS `source`,
        t2.pay_fee,
        IF(t2.source = 0,t2.pay_channel_id,t2.pay_product_id) AS pay_product_id,
        IF(t2.source = 0,t3.name,t8.name) as product_name,
        IF(t2.source = 0,t3.category_id,t8.first_class) as category_id,
        IF(t2.source = 0,t7.name,t9.name) AS category_name,
        t2.pay_status,
        t2.pay_scene AS order_pay_scene,
        t2.pay_order_time,
        IFNULL(t6.pay_time, t2.pay_time) AS pay_time,
        t2.pay_amount,
        t2.pay_refund_time as refund_time,
        t2.coach_name as order_coach_name,
        t4.rank AS repurchase_rank,
        t4.term_id AS repurchase_term_id,
        t4.camp_id AS repurchase_camp_id,
        t4.camp_name AS repurchase_camp_name,
        IF(t2.account_id IS null, 0, 1) AS order_account_flag,
        IFNULL(t6.channel_no, '0') AS deposit_plan_id,
        IF(t2.pay_status = 1, 0, IF(t2.order_source != 'loan_plan', 0, IF(t2.pay_amount = t2.pay_fee or (t2.pay_status = 2 and t2.is_deposit = 0), 1,2)))AS deposit_plan_status,
        IF(t2.pay_status = 1, -1, IF(t2.order_source != 'loan_plan', t2.is_deposit, IF((t2.pay_amount = t2.pay_fee or (t2.pay_status = 2 and t2.is_deposit = 0)) AND t2.max_pay_time = IFNULL(t6.pay_time, t2.pay_time) , 3, 2)))  AS deposit_status
    FROM warehouse.dwd_class_term_student_order t2
    JOIN [shuffle] repurchase_term t4
        ON t4.term_id = t2.term_id
    LEFT JOIN   warehouse.dim_mdb_liveroom_channel t3
        ON t2.pay_channel_id = t3.id AND t2.source = 0
    LEFT JOIN warehouse.dim_mdb_product_category t7
        ON t3.category_id = t7.id AND t2.source = 0
    LEFT JOIN warehouse.ods_miniprogram_product t8
        ON t2.pay_product_id = t8.id AND t2.source = 1
    LEFT JOIN   warehouse.dim_mdb_product_category t9
        ON t8.first_class = t9.id AND t2.source = 1
    LEFT JOIN [shuffle] warehouse.ods_miniprogram_platform_transaction t6
        ON t2.order_source = 'loan_plan'
        AND t2.order_id = t6.order_id
        AND t6.pay_state = 1
    WHERE t2.create_time >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
        AND t2.pay_order_time BETWEEN {{start_date}} AND DATE_ADD({{end_date}}, INTERVAL 1 DAY)
        [[ AND IF(t2.source = 0,t3.category_id,t8.first_class) in ({{category_ids}}) ]]
),
authorize_account_order AS (
SELECT
    t1.term_id,
    t1.rank,
    t1.class_id,
    t1.class_name,
    t1.account_main_id,
    t1.student_status,
    t2.*
FROM authorize_account t1
JOIN account_repurchase_order t2  ON t1.account_id = t2.account_id
AND IF(t2.pay_status = 3, t2.pay_order_time >= t1.grant_time, true)
WHERE t1.r = 1
[[ AND t1.class_id IN ({{class_ids}}) ]]
[[ AND t1.term_id IN ({{term_ids}}) ]]
[[ AND t1.account_id IN ({{account_ids}}) ]]
[[ AND t1.account_main_id IN ({{account_main_ids}}) ]]
)
SELECT
  `aao`.`category_id`,
  `aao`.`category_name`,
  COUNT(DISTINCT `aao`.`order_id`) AS `order_count`,
  COUNT(DISTINCT CASE WHEN `aao`.`pay_status` = 3 THEN `aao`.`order_id` END) AS `refund_order_count`,
  COUNT(DISTINCT `aao`.`account_main_id`) AS `buyer_count`,
  COUNT(DISTINCT CASE WHEN `aao`.`pay_status` = 3 THEN `aao`.`account_main_id` END) AS `refund_buyer_count`,
  SUM(`aao`.`pay_fee`) AS `total_pay_fee`,
  SUM(CASE WHEN `aao`.`pay_status` = 3 THEN `aao`.`pay_fee` ELSE 0 END) AS `refund_pay_fee`,
  ROUND(
    COUNT(DISTINCT CASE WHEN `aao`.`pay_status` = 3 THEN `aao`.`order_id` END)
    * 1.0
    / NULLIF(COUNT(DISTINCT `aao`.`order_id`), 0)
    * 100
  , 2) AS `refund_order_rate`,
  ROUND(
    SUM(CASE WHEN `aao`.`pay_status` = 3 THEN `aao`.`pay_fee` ELSE 0 END)
    * 1.0
    / NULLIF(SUM(`aao`.`pay_fee`), 0)
    * 100
  , 2) AS `refund_fee_rate`
FROM `authorize_account_order` `aao`
WHERE 1=1
  AND `aao`.`pay_status` IN (2, 3)
GROUP BY
  `aao`.`category_id`,
  `aao`.`category_name`
ORDER BY `refund_pay_fee` DESC
"""

_INTRO = (
    "按**品类**统计授权学员复购订单中「未退款 + 已退款」的退款表现："
    "订单数、退款单数、支付/退款金额及退款率。"
    "可用于对比各品类退款风险；柱状图默认按退款金额从高到低排列。"
)
_INSIGHT_TPL = (
    "下单区间：{start_date} ~ {end_date}；期次：{term_scope}；"
    "班级：{class_scope}；品类：{category_scope}。"
    "共 {n} 个品类，订单合计 {order_count} 单，退款 {refund_order_count} 单"
    "（订单退款率 {refund_order_rate}%）；"
    "支付金额合计 {total_pay_fee}，退款金额 {refund_pay_fee}"
    "（金额退款率 {refund_fee_rate}%）。"
    "退款金额最高为「{top_name}」（{top_refund_fee}，占退款合计 {top_pct}%）。"
)

# 冻结上次查询条件与可读 label；改筛选不自动重查，点「查询」或首次进入才更新
_SS_FILTERS = "category_refund_stats_filters"
_SS_LABELS = "category_refund_stats_filter_labels"

st.subheader("品类退款分析")
st.markdown(_INTRO)

if not st.session_state.get("tid") or not st.session_state.get("camp_id"):
    st.warning("请先登录")
    st.stop()

conn = get_conn()

# 日期最前且必填（默认最近 15 天）；期次本页可空选（不 default_first）
_end = date.today()
_start = _end - timedelta(days=14)
filter_values, filter_labels = render_filters(
    conn,
    extract_params(TEMPLATE),
    fallbacks={
        "start_date": {
            "label": "开始日期 (YYYY-MM-DD)",
            "widget": "text_input",
            "default": _start.isoformat(),
        },
        "end_date": {
            "label": "结束日期 (YYYY-MM-DD)",
            "widget": "text_input",
            "default": _end.isoformat(),
        },
    },
    fallbacks_first=True,
    spec_overrides={"term_ids": {"default_first": False}},
)


def _freeze_filters() -> None:
    st.session_state[_SS_FILTERS] = filter_values
    st.session_state[_SS_LABELS] = filter_labels


with st.container(horizontal_alignment="right"):
    if st.button("查询", type="primary"):
        _freeze_filters()

# 首次进入：用当前默认筛选自动查一次（之后仅点「查询」才刷新）
if _SS_FILTERS not in st.session_state:
    _freeze_filters()

saved_filters = st.session_state[_SS_FILTERS]
saved_labels = st.session_state.get(_SS_LABELS, {})

# 必填：下单起止日期（CTE 内无 [[]]，不可为空）
missing = []
if not saved_filters.get("start_date"):
    missing.append("开始日期")
if not saved_filters.get("end_date"):
    missing.append("结束日期")
if missing:
    st.warning(f"请先填写：{'、'.join(missing)}")
    st.stop()

sql, sa_params = build_sql(TEMPLATE, saved_filters)

# 先展示 SQL；查询失败时 SQL 仍留在页面上便于排查
df = show_sql_and_query(conn, sql, sa_params, ttl=0)

if df.empty:
    st.info("暂无数据")
    st.stop()

n = int(len(df))
order_count = int(df["order_count"].sum())
refund_order_count = int(df["refund_order_count"].sum())
total_pay_fee = int(df["total_pay_fee"].sum())
refund_pay_fee = int(df["refund_pay_fee"].sum())
refund_order_rate = (
    round(100.0 * refund_order_count / order_count, 2) if order_count else 0.0
)
refund_fee_rate = (
    round(100.0 * refund_pay_fee / total_pay_fee, 2) if total_pay_fee else 0.0
)
top_row = df.iloc[0]
top_name = str(top_row["category_name"] or "（未命名品类）")
top_refund_fee = int(top_row["refund_pay_fee"])
top_pct = (
    round(100 * top_refund_fee / refund_pay_fee, 1) if refund_pay_fee else 0.0
)

with st.container(horizontal=True):
    st.metric("品类数", n, border=True)
    st.metric("订单合计", order_count, border=True)
    st.metric("退款单数", refund_order_count, border=True)
    st.metric("订单退款率(%)", refund_order_rate, border=True)
    st.metric("退款金额", refund_pay_fee, border=True)
    st.metric("金额退款率(%)", refund_fee_rate, border=True)

st.markdown(
    fill_template(
        _INSIGHT_TPL,
        start_date=saved_labels.get("start_date") or "—",
        end_date=saved_labels.get("end_date") or "—",
        term_scope=join_labels(saved_labels.get("term_ids"), empty="全部期次"),
        class_scope=join_labels(saved_labels.get("class_ids"), empty="全部班级"),
        category_scope=join_labels(
            saved_labels.get("category_ids"), empty="全部品类"
        ),
        n=n,
        order_count=order_count,
        refund_order_count=refund_order_count,
        refund_order_rate=refund_order_rate,
        total_pay_fee=total_pay_fee,
        refund_pay_fee=refund_pay_fee,
        refund_fee_rate=refund_fee_rate,
        top_name=top_name,
        top_refund_fee=top_refund_fee,
        top_pct=top_pct,
    )
)

tab_chart, tab_table = st.tabs(["图表", "表格"])

with tab_chart:
    # 少类别时固定像素宽，避免 1～2 根柱被拉满整行
    chart_width = "stretch" if n > 5 else max(200, n * 120 + 80)
    st.caption("退款金额（按品类）")
    st.bar_chart(
        df,
        x="category_name",
        y="refund_pay_fee",
        x_label="品类",
        y_label="退款金额",
        width=chart_width,
        sort=False,  # 保持 SQL 按退款金额降序
    )
    st.caption("订单退款率 %（按品类）")
    st.bar_chart(
        df,
        x="category_name",
        y="refund_order_rate",
        x_label="品类",
        y_label="订单退款率(%)",
        width=chart_width,
        sort=False,
    )

with tab_table:
    st.dataframe(df, width="stretch", hide_index=True)

"""SQL 模板渲染与数据库执行校验工具页面。

输入带 %(param)s 的 SQL 模板及 Python 字典 / JSON 参数，
渲染出完整可执行的 SQL，并测试其能否在数据库（StarRocks / Metabase）中成功执行。
"""

import time
import pandas as pd
import streamlit as st

import utils.metabase
try:
    from utils.metabase import parse_params, render_sql
except ImportError:
    import importlib
    importlib.reload(utils.metabase)
    from utils.metabase import parse_params, render_sql

import utils.query
importlib.reload(utils.query)
from utils.query import get_conn, get_registered_databases




# 默认 SQL 模板示例（提取自用户需求）
DEFAULT_SQL_TEMPLATE = """-- lh-teaching
WITH repurchase_term AS (
    SELECT t1.tid,
           t1.camp_id,
           t2.id AS term_id,
           t2.rank,
           t3.camp_name
    FROM warehouse.dim_lh_teaching_repurchase_camp t1
    JOIN [shuffle] warehouse.dim_lh_class_term t2
      ON t1.camp_id = t2.camp_id
    JOIN [shuffle] warehouse.dim_lh_class_camp t3
      ON t1.camp_id = t3.id
    WHERE t1.`status` = 1
      AND t1.tid = 279
)
, authorize_account AS (
    SELECT *
    FROM (
        SELECT DISTINCT
            t1.term_id, t1.grant_class_id AS class_id, t1.student_status, t1.grant_time,
            nvl(ar2.origin_account_id, t1.account_id) as account_id,
            NVL(ar.account_main_id, t1.account_id) AS account_main_id,
            t2.tid, t2.rank, t3.class_name,
            RANK() OVER(partition by t1.camp_id, NVL(ar.account_main_id, t1.account_id) ORDER BY t1.grant_time DESC) r
        FROM warehouse.dim_lh_term_student_metrics t1
        JOIN [shuffle] warehouse.dim_lh_teaching_class_term t2
          ON t1.term_id = t2.id AND t2.tid = 279
        JOIN [shuffle] warehouse.dwd_lh_classes t3
          ON t1.grant_class_id = t3.id
        LEFT JOIN dim_origin_account_relation ar
          ON t1.account_id = ar.origin_account_id
        LEFT JOIN dim_origin_account_relation ar2
          ON ar2.account_main_id = ar.account_main_id
        WHERE t1.student_status NOT IN ('abandon')
    ) res
    WHERE r = 1
)
, pay_authorize_account AS (
    SELECT
        IF(t2.order_source = 'loan_plan', t2.order_id, t2.id) as id,
        IF(t2.source = 0, 'high', 'physical') AS `source`,
        IF(t2.refund_fee > 0 AND t2.pay_fee > t2.pay_amount, t2.pay_fee - t2.refund_fee, t2.pay_fee) As pay_fee,
        IF(t2.source = 0, t2.pay_channel_id, t2.pay_product_id) AS pay_product_id,
        IF(t2.source = 0, t3.name, t8.name) as product_name,
        IF(t2.source = 0, t3.category_id, t8.first_class) as category_id,
        IF(t2.source = 0, t7.name, t9.name) AS category_name,
        IF(t2.source = 1, IF(IF(t2.refund_fee > 0 AND t2.pay_fee > t2.pay_amount, t2.pay_fee - t2.refund_fee, t2.pay_fee) = t2.pay_amount, 0, 1), t2.is_deposit) AS is_deposit,
        t2.pay_status,
        t2.pay_scene AS order_pay_scene,
        IF(t2.order_source = 'loan_plan' AND t6.src_prod_id > 0, 'live_v', IF(t2.order_source = 'loan_plan' AND nvl(t6.src_prod_id, 0) = 0, 'no_live', IF(t2.source = 1 AND t2.lecture_id > 0, 'live_v', t2.pay_scene))) AS pay_scene,
        t2.pay_order_time,
        IFNULL(t6.pay_time, t2.pay_time) AS pay_time,
        IFNULL(t6.pay_time, t2.pay_time) AS order_pay_time,
        t2.order_source,
        t2.pay_amount,
        t1.term_id, t1.rank, t1.class_id, t1.class_name, t2.account_id, t1.account_main_id, t1.student_status,
        t2.lecture_id, t6.channel_no, t6.fee, t2.pay_refund_time, t2.id AS trid,
        t2.min_pay_time AS first_loan_pay_time, t2.max_pay_time AS last_loan_pay_time,
        t2.pay_nums as transaction_cnt, t2.coach_name,
        t4.rank AS repurchase_rank, t4.term_id AS repurchase_term_id, t4.camp_id AS repurchase_camp_id, t4.camp_name AS repurchase_camp_name,
        IF(t1.account_id IS NOT null AND t2.pay_status > 1 AND IF(t2.pay_status = 3, t2.pay_order_time >= t1.grant_time, true), 1, 0) AS fee_flag,
        IF(t2.account_id IS null, 0, 1) AS order_account_flag
    FROM dwd_class_term_student_order t2
    JOIN [shuffle] repurchase_term t4
      ON t4.term_id = t2.term_id
     AND t2.create_time >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
    LEFT JOIN [shuffle] authorize_account t1
      ON t1.account_id = t2.account_id
     AND t1.tid = t4.tid
    LEFT JOIN warehouse.dim_mdb_liveroom_channel t3
      ON t2.pay_channel_id = t3.id AND t2.source = 0
    LEFT JOIN warehouse.dim_mdb_product_category t7
      ON t3.category_id = t7.id AND t2.source = 0
    LEFT JOIN warehouse.ods_miniprogram_product t8
      ON t2.pay_product_id = t8.id AND t2.source = 1
    LEFT JOIN warehouse.dim_mdb_product_category t9
      ON t8.first_class = t9.id AND t2.source = 1
    LEFT JOIN [shuffle] ods_miniprogram_platform_transaction t6
      ON t2.order_source = 'loan_plan'
     AND t2.order_id = t6.order_id
     AND t6.pay_state = 1
    WHERE 1=1
      AND t2.pay_order_time >= %(start_date)s
      AND t2.pay_order_time < DATE_ADD(%(end_date)s, INTERVAL 1 DAY)
)
, repurchase_stage_conf AS (
    SELECT *, ROW_NUMBER() OVER(PARTITION BY term_id, class_id, repurchase_term_id, category_id ORDER BY dt) AS r
    FROM (
        SELECT t1.*
        FROM warehouse.dim_term_repurchase_stage_conf t1
        JOIN [shuffle] warehouse.dim_lh_teaching_class_term t2
          ON t1.term_id = t2.id AND t2.tid = %(tid)s
        WHERE t1.`status` = 1
    ) res LATERAL VIEW EXPLODE(split_by_string(repurchase_date_array, ',')) x AS dt
)
, repurchase_orders AS (
    SELECT
        t1.*,
        IF(t1.order_source = 'loan_plan', t1.order_pay_time, t1.pay_time) as final_pay_time,
        ARRAY_POSITION(SPLIT_BY_STRING(t2.repurchase_date_array, ','), to_date(if( t1.order_source = 'loan_plan', t1.order_pay_time, t1.pay_time ))) AS transform_day,
        t1.coach_name AS order_coach_name,
        t1.pay_refund_time AS refund_time,
        t1.pay_order_time AS order_time,
        IFNULL(t1.channel_no, '0') AS deposit_plan_id,
        IF(t1.pay_status = 1, 0, IF(t1.order_source != 'loan_plan', 0, IF(t1.pay_amount = t1.pay_fee or (t1.pay_status = 2 and t1.is_deposit = 0), 1, 2))) AS deposit_plan_status,
        IF(t1.pay_status = 1, -1, IF(t1.order_source != 'loan_plan', t1.is_deposit, IF((t1.pay_amount = t1.pay_fee or (t1.pay_status = 2 and t1.is_deposit = 0)) AND t1.last_loan_pay_time = t1.order_pay_time, 3, 2))) AS deposit_status,
        IFNULL(t1.fee, 0)/100 AS child_fee,
        IF(t1.pay_status = 1, 0, IF(IF(t1.pay_status = 1, 0, IF(t1.order_source != 'loan_plan', 0, IF(t1.pay_amount = t1.pay_fee or (t1.pay_status = 2 and t1.is_deposit = 0), 1, 2))) != 0, IFNULL(t1.fee, 0)/100, t1.pay_fee / 100)) as paid_fee
    FROM pay_authorize_account t1
    LEFT JOIN [shuffle] repurchase_stage_conf t2
      ON t1.term_id = t2.term_id
     AND t1.class_id = t2.class_id
     AND t1.category_id = t2.category_id
     AND t1.repurchase_term_id = t2.repurchase_term_id
     AND TO_DATE(pay_time) = t2.dt
    WHERE 1 = 1
      AND t1.id = %(id)s
)
SELECT *
FROM repurchase_orders
WHERE 1 = 1
ORDER BY pay_time DESC
LIMIT %(offset)s, %(limit)s"""

DEFAULT_PARAMS_STR = """OrderedDict([('tid', 279), ('camp_id', 106251), ('date_type', 'pay_order_time'), ('start_date', datetime.date(2026, 1, 1)),
     ('end_date', datetime.date(2026, 8, 31)), ('id', 3905121), ('page', 1), ('limit', 20),
     ('order_by', 'pay_time DESC'), ('offset', 0)])"""

st.title("SQL 渲染与执行校验")
st.caption(
    "输入带 `%(param)s` 占位符的 SQL 模板及 Python 字典 / JSON 参数，自动渲染为最终 SQL 语句，并可检验 SQL 能否正常在 StarRocks / Metabase 执行。"
)

# 两个输入区域：SQL 模板与参数字典
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("SQL 模板")
    sql_input = st.text_area(
        "SQL Template",
        value=DEFAULT_SQL_TEMPLATE,
        height=320,
        label_visibility="collapsed",
        help="支持带 %(param_name)s 的 SQL 模板",
    )

with col_right:
    st.subheader("参数 (Python Dict / JSON)")
    params_input = st.text_area(
        "Parameters",
        value=DEFAULT_PARAMS_STR,
        height=320,
        label_visibility="collapsed",
        help="支持 Python OrderedDict(...) / dict 或 JSON 格式",
    )

# 操作按钮列
col_btn1, col_btn2, col_db, _ = st.columns([1.5, 2, 2.5, 2], vertical_alignment="center")
with col_btn1:
    btn_render = st.button("渲染 SQL", type="primary", key="btn_render", icon=":material/code:")
with col_btn2:
    btn_test_exec = st.button("渲染并验证执行", key="btn_test_exec", icon=":material/play_arrow:")
with col_db:
    target_db = st.selectbox("目标数据库", options=get_registered_databases(), index=0, key="sql_render_target_db")

# 解析与渲染逻辑
parse_error = None
parsed_params = {}
rendered_sql = ""
missing_params = []

if sql_input:
    try:
        parsed_params = parse_params(params_input)
    except Exception as exc:
        parse_error = str(exc)

    if not parse_error:
        rendered_sql, missing_params = render_sql(sql_input, parsed_params)

# 展示渲染结果
st.divider()

if parse_error:
    st.error(f"❌ 参数解析失败: {parse_error}")
else:
    if missing_params:
        st.warning(f"⚠️ SQL 中存在未在参数字典中赋值的占位符: `{'`, `'.join(missing_params)}`")

    with st.expander("渲染后的 SQL (可执行 SQL)", expanded=False):
        st.code(rendered_sql, language="sql")

    # 点击验证执行
    if btn_test_exec:
        st.subheader("执行结果校验")
        conn = get_conn(db_name=target_db)

        try:
            with st.spinner("正在发送至数据库执行校验..."):
                start_time = time.time()
                df = conn.query(rendered_sql, ttl=0)
                elapsed = time.time() - start_time

            st.success(f"✅ **SQL 正常可执行！** 查询成功返回 {len(df)} 行数据，耗时 {elapsed:.2f} 秒。")
            if not df.empty:
                st.dataframe(df, width="stretch", hide_index=True)
            else:
                st.info("查询成功，但返回结果集为空 (0 行)。")
        except Exception as exc:
            st.error(f"❌ **SQL 无法成功执行！数据库抛出错误：**\n\n```text\n{exc}\n```")

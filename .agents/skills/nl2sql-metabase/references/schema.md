# Schema Reference — warehouse 数据库

## 表元数据协议说明

每张表用以下结构声明约束，SKILL.md 中的规则引擎会读取并应用这些元数据：

```
- **alias**: 推荐别名
- **use_for**: 适合回答哪类问题（用于表选择决策）
- **required_filters**: 使用此表必须注入的强制条件（无 [[]]），CTE 型表则为固定 WITH 写法
- **optional_filters**: 可选条件（有则加 [[]]）；未列出时按业务需要自行添加
- **examples**: 该表的典型 SQL 用法（1-2 个）
```

---

## 基础维度表

### dim_lh_basic_team（团队表）

- **alias**: `t`
- **use_for**: 定义不同的团队/训练营，其余数据表都使用 `camp_id` 或 `tid`（对应本表 `id`）实现数据隔离，且二者在查询时均为必填参数。
- **required_filters**:
  ```sql
  AND `t`.`id` = {{tid}}
  AND `t`.`camp_id` = {{camp_id}}
  ```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 团队id（PK），其他表对应 tid 字段 |
| name | varchar | 团队名称 |
| camp_id | int | 训练营id(唯一键) |

---

### dim_lh_teaching_class_term（营期表）

- **alias**: `ct`
- **use_for**: 每个团队/训练营下定义不同的营期，实现不同营期之间的数据隔离
- **required_filters**:
  ```sql
  AND `ct`.`tid` = {{tid}}
  AND `ct`.`camp_id` = {{camp_id}}
  ```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 营期id（PK），其他表对应 term_id/camp_term_id 字段 |
| tid | int | 团队id（外键） → dim_lh_basic_team.id |
| camp_id | int | 训练营id |
| rank | int | 第N期（同个团队/训练营下rank从1开始递增） |
| op_start_time | datetime | 开营时间 |
| op_end_time | datetime | 结营时间 |

**示例 1：查询某团队所有营期列表**
```sql
SELECT
  `ct`.`id`   AS `term_id`,
  `ct`.`rank` AS `term_rank`,
  `ct`.`op_start_time`,
  `ct`.`op_end_time`
FROM `warehouse`.`dim_lh_teaching_class_term` `ct`
WHERE 1=1
  AND `ct`.`camp_id` = {{camp_id}}
  AND `ct`.`tid` = {{tid}}
  [[ AND `ct`.`id` IN ({{term_ids}}) ]]
ORDER BY `ct`.`rank`
```

---

### dwd_lh_classes（班级表）

- **alias**: `c`
- **use_for**: 每个营期下定义不同的班级，实现不同班级之间的数据隔离。
- **required_filters**:
  ```sql
  AND `c`.`camp_id` = {{camp_id}}
  ```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 班级id（PK） |
| camp_id | int | 训练营id |
| camp_term_id | int | 营期id（外键） → dim_lh_teaching_class_term.id |
| class_name | varchar | 班级名称 |
| monitor_user_id | int | 教练id |
| monitor_name | varchar | 教练名称 |
| state | varchar | 枚举：normal=正常, invalid=无效, deleted=已删除 |

**示例 1：查询某营期下所有有效班级**
```sql
SELECT
  `c`.`id`         AS `class_id`,
  `c`.`class_name`
FROM `warehouse`.`dwd_lh_classes` `c`
WHERE 1=1
  AND `c`.`camp_id` = {{camp_id}}
  AND `c`.`state` = 'normal'
  [[ AND `c`.`camp_term_id` IN ({{term_ids}}) ]]
ORDER BY `c`.`class_name`
```

---

### ods_lh_teaching_lh_teaching_student（学员明细表）

- **alias**: `s`
- **use_for**: 班级下所有学员。

  1. 一般使用 `account_id`（荔课ID）代表一个学员，其余数据表通过 `account_id` 关联到该学员。
  2. 用户可能通过不同主体注册，存在多个 `account_id`（荔课ID）记录。为标识多个 `account_id` 属于同一学员，需通过 `account_main_id`（学员主账号ID）关联。
  
  ⚠️ **统计人数时，必须用 `NVL(s.account_main_id, s.account_id)` 作为去重键**，避免同一学员因多荔课ID被重复计算。此处直接使用 `s.account_main_id` 字段（学员表自带，无需额外 JOIN `ods_mdb_account_main_relation`）。

- **required_filters**:
  ```sql
  AND `s`.`tid` = {{tid}}
  AND `s`.`camp_id` = {{camp_id}}
  ```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | PK |
| tid | int | 团队id |
| camp_id | int | 训练营id |
| term_id | int | 营期id（外键） → dim_lh_teaching_class_term.id |
| big_class_id | int | 班级id(外键) → dwd_lh_classes.id |
| account_id | int | 荔课ID（用户学习的ID,同一个学员ID可能存在多个荔课ID） |
| account_main_id | int | 学员ID（标识唯一的用户）|
| wechat_nickname | varchar | 学员昵称 |
| add_status | varchar | 添加状态：added=已添加, to_add=未添加, 默认 null |
| authorization_status | varchar | 授权状态：unauthorized=未授权, authorized=已授权 |
| student_status | varchar | 学员状态枚举：to_start=待开营, reading=在读, postpone=延期, refunding=退费受理, refunded=退费, relearning=重学, graduate=毕业, abandon=废弃，默认 to_start |
| add_robot_id | int | 添加机器人id |
| is_teacher | tinyint | 是否导师：1=是, 0=不是，默认 0 |
| grant_time | datetime | 授权时间 |

**示例 2：查询学员列表**
```sql
SELECT
  `c`.`class_name`,
  `s`.`account_id`,
  `s`.`wechat_nickname`,
  `s`.`student_status`,
  `s`.`authorization_status`,
  `s`.`add_status`
FROM `warehouse`.`ods_lh_teaching_lh_teaching_student` `s`
LEFT JOIN `warehouse`.`dwd_lh_classes` `c`
  ON `s`.`big_class_id` = `c`.`id`
WHERE 1=1
  AND `s`.`tid` = {{tid}}
  AND `s`.`camp_id` = {{camp_id}}
  AND `s`.`term_id` IN ({{term_ids}})
  [[ AND `s`.`big_class_id` IN ({{class_ids}}) ]]
  [[ AND `s`.`wechat_nickname` LIKE CONCAT('%', {{name}}, '%') ]]
```

---

## 业务配置表

### dim_lh_teaching_weeks_conf（自然周数据配置表）

- **alias**: `wc`
- **use_for**: 记录自定义的自然周（某年、某月、某周）配置的开始时间和结束时间，因为需要根据周维度来查看班级/营期下学员相关数据的变化，例如：添加人数、授权人数、退费人数等，这些数据都以周维度的方式记录在`dws_lh_teaching_term_class_week`表中，经常用来作为筛选列表。
- **required_filters**:
  ```sql
  AND `wc`.`tid` = {{tid}}
  ```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | PK，自然周配置唯一ID，可作为 `{{week_id}}` 入参 |
| tid | int | 团队id |
| year | int | 年，eg:2026 |
| month | int | 月，eg:2 |
| week | int | 周，eg:1、2、3 |
| week_days | int | 每周的天数，eg:7 |
| start_time | date | 该自然周开始日期 |
| end_time | date | 该自然周结束日期 |

---

## 汇总统计表

### dws_lh_teaching_term_class_week（定格某个自然周下班级学员指标汇总表）

- **alias**: `cw`
- **use_for**: 记录某个自然周结束时，班级下学员指标定格的汇总快照。通常用来：
  1. 对比某自然周不同班级学员指标的差异
  2. 对比某个班级在连续自然周学员指标的变化
  3. 对比某自然周不同营期学员指标的差异（需按营期分组聚合，因一个营期下存在多个班级）

- **required_filters**:
  ```sql
  AND `cw`.`term_id` IN ({{term_ids}})
  ```

- **optional_filters**（可选，加 `[[]]`）:
  ```sql
  [[ AND `cw`.`class_id` IN ({{class_ids}}) ]]
  ```

| 字段 | 类型 | 说明 |
|------|------|------|
| term_id | int | 营期id（外键） → dim_lh_teaching_class_term.id |
| class_id | int | 班级id（外键） → dwd_lh_classes.id |
| year | int | 年，year、month、week对应`dim_lh_teaching_weeks_conf`表中的一行自然周记录 |
| month | int | 月 |
| week | int | 周 |
| abs_week | int | 绝对周数：根据term_id对应营期的开营时间（dim_lh_teaching_class_term.op_start_time）计算经历过多少个自然周（dim_lh_teaching_weeks_conf）|
| authorize_num | int | 授权人数：自然周（year、month、week）结束时，该班级学员授权状态（authorization_status=authorized）的学员数 |
| original_num | int | 原始人数|
| add_robot_num | int | 添加（机器人）人数 |
| reading_num | int | 在读人数 |
| raise_refund_num | int | 提出退费人数 |
| refund_num | int | 退费人数 |
| homework_submit_num | int | 作业提交人数 |
| high_interact_num_day | int | 当天高互动学员人数 |
| high_interact_num_week | int | 当周高互动学员人数 |
| high_interact_num_yesterday | int | 昨日高互动学员人数 |
| external_complain_count | int | 外诉单数 |
| combine_raise_refund_num | int | 预提退费人数 |
| ws_num | int | 外诉次数 |
| high_interact_intention_num | int | 高意向人数 |
| app_login_num | int | APP登录人数 |

**示例 1：查询某个班级在连续多个自然周（start_week_id ~ end_week_id）内各指标的变化趋势**

```sql
SELECT
  `cw`.`year`,
  `cw`.`month`,
  `cw`.`week`,
  `cw`.`authorize_num`,
  `cw`.`original_num`,
  `cw`.`ws_num`,
  `cw`.`raise_refund_num`,
  `cw`.`add_robot_num`
FROM `warehouse`.`dws_lh_teaching_term_class_week` `cw`
JOIN `warehouse`.`dim_lh_teaching_weeks_conf` `wc`
  ON `wc`.`year` = `cw`.`year`
  AND `wc`.`month` = `cw`.`month`
  AND `wc`.`week` = `cw`.`week`
  AND `wc`.`tid` = {{tid}}
  AND `wc`.`id` BETWEEN {{start_week_id}} AND {{end_week_id}}
WHERE 1=1
  AND `cw`.`term_id` = {{term_id}}
  AND `cw`.`class_id` = {{class_id}}
```

**示例 2：对比营期内某个自然周下不同班级学员指标**

因维度键包含 `class_id`，单周单班只有一条记录，无需 SUM。

```sql
SELECT
  `ct`.`rank`          AS `term_rank`,
  `c`.`class_name`,
  `c`.`id`             AS `class_id`,
  `cw`.`authorize_num`,
  `cw`.`original_num`,
  `cw`.`ws_num`,
  `cw`.`raise_refund_num`,
  `cw`.`add_robot_num`
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
```


**示例 3：对比不同营期某自然周下学员指标（需要根据营期进行分组聚合，因为某个营期下存在多个班级）**

```sql
SELECT
  `ct`.`id`                    AS `term_id`,
  `ct`.`rank`,
  SUM(`cw`.`authorize_num`)    AS `authorize_num`,
  SUM(`cw`.`original_num`)     AS `original_num`,
  SUM(`cw`.`ws_num`)           AS `ws_num`,
  SUM(`cw`.`raise_refund_num`) AS `raise_refund_num`,
  SUM(`cw`.`add_robot_num`)    AS `add_robot_num`
FROM `warehouse`.`dws_lh_teaching_term_class_week` `cw`
JOIN `warehouse`.`dim_lh_teaching_class_term` `ct`
  ON `cw`.`term_id` = `ct`.`id`
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
GROUP BY `ct`.`id`, `ct`.`rank`
ORDER BY `ct`.`rank`
```


---

## 复购订单表

### authorize_account_order（授权学员订单视图，CTE 型）

- **alias**: `aao`
- **use_for**: 查询学员的复购订单数据。同一荔课 ID 可能存在于多个营期/班级，订单关联复杂，已封装为固定 CTE，无需关注内部表结构与 JOIN。使用时：
  > 1. 将下方 **完整 CTE 块**原样粘贴到 SQL 最前面，业务查询从 CTE `authorize_account_order` 取数（别名 `aao`）
  > 2. 3 个必填参数已写入 CTE：`{{tid}}`、`{{start_date}}`、`{{end_date}}`（日期格式 `'YYYY-MM-DD'`）；其余可选参数按用户问题增减

- **CTE 块**：
```sql

use warehouse;
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
    LEFT JOIN dim_origin_account_relation ar
        ON t1.account_id = ar.origin_account_id
    LEFT JOIN dim_origin_account_relation ar2
        ON ar2.account_main_id = ar.account_main_id
    WHERE t1.student_status NOT IN ('abandon')
),
account_repurchase_order AS (
    SELECT 
        IF(t2.order_source = 'loan_plan', t2.order_id, t2.id) as order_id, -- 订单ID
        t2.account_id,                                               -- 荔课ID
        IF(t2.source = 0, 'high', 'physical') AS `source`, -- 商品类型：'physical': '实体商品','high': '课程商品'
        t2.pay_fee,  -- 支付金额
        IF(t2.source = 0,t2.pay_channel_id,t2.pay_product_id) AS pay_product_id, -- 商品ID
        IF(t2.source = 0,t3.name,t8.name) as product_name, -- 商品名称
        IF(t2.source = 0,t3.category_id,t8.first_class) as category_id,  -- 品类ID
        IF(t2.source = 0,t7.name,t9.name) AS category_name,  -- 品类名称
        t2.pay_status,  -- 订单状态：1: '待支付',2: '未退款',3: '已退款'
        t2.pay_scene AS order_pay_scene,  -- 出单方式: live_v:直播间， 其他：私聊
        t2.pay_order_time,  -- 下单时间
        IFNULL(t6.pay_time, t2.pay_time) AS pay_time,  -- 支付时间
        -- t2.order_source,
        t2.pay_amount,  -- 应付金额
        -- t6.channel_no,
        t2.pay_refund_time as refund_time,  -- 退费时间
        t2.coach_name as order_coach_name,  -- 出单教练
        t4.rank AS repurchase_rank,  -- 复购训练营期数
        t4.term_id AS repurchase_term_id,  -- 复购训练营期ID
        t4.camp_id AS repurchase_camp_id,  -- 复购训练营ID
        t4.camp_name AS repurchase_camp_name,  -- 复购训练营名称
        IF(t2.account_id IS null, 0, 1) AS order_account_flag,  -- 订单用户识别：1：正常，其他：未识别
        IFNULL(t6.channel_no, '0') AS deposit_plan_id,  -- 交易订单号
        IF(t2.pay_status = 1, 0, IF(t2.order_source != 'loan_plan', 0, IF(t2.pay_amount = t2.pay_fee or (t2.pay_status = 2 and t2.is_deposit = 0), 1,2)))AS deposit_plan_status,  -- 定金计划状态：0: '-',1: '已结清',2: '未结清'
        IF(t2.pay_status = 1, -1, IF(t2.order_source != 'loan_plan', t2.is_deposit, IF((t2.pay_amount = t2.pay_fee or (t2.pay_status = 2 and t2.is_deposit = 0)) AND t2.max_pay_time = IFNULL(t6.pay_time, t2.pay_time) , 3, 2)))  AS deposit_status -- 出单类型：-1: '-', 0: '专栏尾款',1: '专栏定金',2: '定金计划-定金',3: '定金计划-尾款'
    FROM dwd_class_term_student_order t2
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
    LEFT JOIN [shuffle] ods_miniprogram_platform_transaction t6
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
    t1.student_status,  -- 学员状态:"to_start": "待开营","reading": "在读","postpone": "改期","refunding": "退费受理","refunded": "退费","change_num": "换号","relearning": "重学","graduate": "毕业","abandon": "废弃"
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
-- ↑ CTE 结束，在此之后写业务查询 ↓
```

| 字段 | 类型 | 说明 |
|------|------|------|
| order_id | int | 订单 id |
| account_id | int | 荔课 id |
| source | varchar | 商品类型：'physical': '实体商品','high': '课程商品' |
| pay_fee | int | 支付金额 |
| pay_product_id | int | 商品ID |
| product_name | varchar | 商品名称 |
| category_id | int | 品类 id |
| category_name | varchar | 品类名称 |
| pay_status | tinyint | 订单支付状态：1: '待支付',2: '未退款',3: '已退款' |
| order_pay_scene | int | 出单方式: live_v:直播间， 其他：私聊 |
| pay_order_time | datetime | 下单时间 |
| pay_time | datetime | 支付时间 |
| pay_amount | int | 应付金额 |
| refund_time | datetime | 退费时间 |
| order_coach_name | varchar | 出单教练名 |
| repurchase_rank | varchar | 复购训练营期数 |
| repurchase_term_id | varchar | 复购训练营期ID |
| repurchase_camp_id | varchar | 复购训练营ID |
| repurchase_camp_name | varchar | 复购训练营名称 |
| deposit_plan_id | int | 交易订单号 |
| deposit_plan_status | int | 定金计划状态：0: '-',1: '已结清',2: '未结清' |
| deposit_status | int | 出单类型：-1: '-', 0: '专栏尾款',1: '专栏定金',2: '定金计划-定金',3: '定金计划-尾款' |
| term_id | int | 学员下单时授权营期 id |
| rank | int | 学员下单时授权营期对应的第 N 期 |
| class_id | int | 学员下单时授权班级 id |
| class_name | varchar | 学员下单时授权班级名称 |
| student_status | varchar | 学员下单时学员状态 |
| account_main_id | int | 学员主账号 |

**示例 1：统计指定时间段内各班级的已支付订单金额**
```sql
-- （在 WITH 块末尾追加）
SELECT
  `aao`.`class_id`,
  `aao`.`class_name`,
  COUNT(DISTINCT `aao`.`order_id`) AS `order_count`,
  SUM(`aao`.`pay_fee`)             AS `total_pay_fee`
FROM `authorize_account_order` `aao`
WHERE `aao`.`pay_status` = 2
GROUP BY `aao`.`class_id`, `aao`.`class_name`
ORDER BY `total_pay_fee` DESC
```
